"""Tests for dusage — directory usage analyzer."""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dusage  # noqa: E402


def write_file(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)


@pytest.fixture
def tree(tmp_path):
    """A small tree with known sizes:
    root/a.txt (100), root/b.py (200),
    root/sub/c.txt (300), root/sub/deep/d.log (400),
    root/empty/ (no files).
    """
    write_file(str(tmp_path / "a.txt"), 100)
    write_file(str(tmp_path / "b.py"), 200)
    write_file(str(tmp_path / "sub" / "c.txt"), 300)
    write_file(str(tmp_path / "sub" / "deep" / "d.log"), 400)
    os.makedirs(tmp_path / "empty", exist_ok=True)
    return tmp_path


# --- parse_size ---

def test_parse_size_plain_bytes():
    assert dusage.parse_size("100") == 100
    assert dusage.parse_size("0") == 0


def test_parse_size_suffixes():
    assert dusage.parse_size("1KB") == 1024
    assert dusage.parse_size("2MB") == 2 * 1024 ** 2
    assert dusage.parse_size("1GB") == 1024 ** 3
    assert dusage.parse_size("512B") == 512


def test_parse_size_case_insensitive_and_float():
    assert dusage.parse_size("1.5kb") == 1536
    assert dusage.parse_size(" 10MB ") == 10 * 1024 ** 2


def test_parse_size_invalid():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        dusage.parse_size("ten")
    with pytest.raises(argparse.ArgumentTypeError):
        dusage.parse_size("10XB")


# --- human_size ---

def test_human_size_units():
    assert dusage.human_size(0) == "0 B"
    assert dusage.human_size(512) == "512 B"
    assert dusage.human_size(1024) == "1.0 KB"
    assert dusage.human_size(1536) == "1.5 KB"
    assert dusage.human_size(1024 ** 2) == "1.0 MB"
    assert dusage.human_size(3 * 1024 ** 3) == "3.0 GB"


# --- scan ---

def test_scan_totals(tree):
    stats = dusage.scan(str(tree))
    assert stats["total_bytes"] == 1000
    assert stats["file_count"] == 4
    # root + sub + sub/deep + empty = 4 directories
    assert stats["dir_count"] == 4


def test_scan_by_extension(tree):
    stats = dusage.scan(str(tree))
    assert stats["by_extension"][".txt"] == 400
    assert stats["by_extension"][".py"] == 200
    assert stats["by_extension"][".log"] == 400


def test_scan_by_subdir(tree):
    stats = dusage.scan(str(tree))
    # Files at the root land under "."; sub's files total 700.
    assert stats["by_subdir"]["."] == 300
    assert stats["by_subdir"]["sub"] == 700


def test_scan_exclude_pattern(tree):
    stats = dusage.scan(str(tree), exclude=["*.txt"])
    assert stats["total_bytes"] == 600
    assert stats["file_count"] == 2


def test_scan_exclude_directory(tree):
    stats = dusage.scan(str(tree), exclude=["sub"])
    assert stats["total_bytes"] == 300
    assert stats["file_count"] == 2


def test_scan_empty_directory(tmp_path):
    stats = dusage.scan(str(tmp_path))
    assert stats["total_bytes"] == 0
    assert stats["file_count"] == 0
    assert stats["dir_count"] == 1
    assert stats["files"] == []


def test_scan_no_extension_file(tmp_path):
    write_file(str(tmp_path / "README"), 50)
    stats = dusage.scan(str(tmp_path))
    assert stats["by_extension"]["(no extension)"] == 50


def test_scan_symlinked_dir_not_followed_by_default(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    write_file(str(target / "big.bin"), 500)
    os.symlink(str(target), str(tmp_path / "link"))
    stats = dusage.scan(str(tmp_path))
    # Only the real dir's file counts once; the symlink dir is not walked.
    assert stats["total_bytes"] == 500
    assert stats["file_count"] == 1


# --- summarize ---

def test_summarize_largest_files_order(tree):
    stats = dusage.scan(str(tree))
    report = dusage.summarize(stats, top=2)
    assert [f["size_bytes"] for f in report["largest_files"]] == [400, 300]
    assert report["largest_files"][0]["path"].endswith("d.log")


def test_summarize_min_size_filters(tree):
    stats = dusage.scan(str(tree))
    report = dusage.summarize(stats, min_size=250)
    assert [f["size_bytes"] for f in report["largest_files"]] == [400, 300]


def test_summarize_depth_zero_hides_subdirs(tree):
    stats = dusage.scan(str(tree))
    report = dusage.summarize(stats, depth=0)
    assert report["largest_subdirs"] == []


def test_summarize_extensions_sorted(tree):
    stats = dusage.scan(str(tree))
    report = dusage.summarize(stats)
    exts = [(e["extension"], e["size_bytes"]) for e in report["by_extension"]]
    assert exts[0][1] == 400  # .txt and .log tie at 400; either may lead
    assert exts[-1] == (".py", 200)


# --- format_text ---

def test_format_text_contains_totals(tree):
    stats = dusage.scan(str(tree))
    report = dusage.summarize(stats)
    text = dusage.format_text(report)
    assert "1000 bytes" in text
    assert "Files: 4" in text
    assert "Largest files:" in text
    assert "d.log" in text


def test_format_text_empty_dir(tmp_path):
    stats = dusage.scan(str(tmp_path))
    report = dusage.summarize(stats)
    text = dusage.format_text(report)
    assert "(none)" in text


# --- CLI (main) ---

def run_cli(*args):
    result = subprocess.run(
        [sys.executable, dusage.__file__, *args],
        capture_output=True, text=True,
    )
    return result


def test_cli_missing_path_returns_2():
    result = run_cli("/definitely/not/a/real/path")
    assert result.returncode == 2
    assert "not a directory" in result.stderr


def test_cli_text_output(tree):
    result = run_cli(str(tree))
    assert result.returncode == 0
    assert "Total:" in result.stdout
    assert "1000 bytes" in result.stdout


def test_cli_json_output(tree):
    result = run_cli(str(tree), "--json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["total_bytes"] == 1000
    assert report["file_count"] == 4
    assert report["largest_files"][0]["size_bytes"] == 400


def test_cli_top_and_min_size(tree):
    result = run_cli(str(tree), "--json", "--top", "1", "--min-size", "250")
    report = json.loads(result.stdout)
    assert len(report["largest_files"]) == 1
    assert report["largest_files"][0]["size_bytes"] == 400


def test_cli_exclude(tree):
    result = run_cli(str(tree), "--json", "--exclude", "*.log")
    report = json.loads(result.stdout)
    assert report["total_bytes"] == 600


def test_cli_default_path_is_cwd(tmp_path, monkeypatch):
    write_file(str(tmp_path / "only.txt"), 42)
    monkeypatch.chdir(tmp_path)
    result = run_cli()
    assert result.returncode == 0
    assert "42 bytes" in result.stdout
