#!/usr/bin/env python3
"""dusage — summarize disk usage of a directory tree.

Reports the total size, file and directory counts, the largest files,
the largest immediate subdirectories, and a breakdown by file extension.

Usage:
    dusage [PATH] [--top N] [--depth N] [--min-size SIZE] [--json]
           [--exclude PATTERN ...] [--follow-symlinks]

Sizes accept suffixes: B, KB, MB, GB (e.g. --min-size 10MB).
Exit codes: 0 = ok, 2 = path missing or not a directory.
Pure Python standard library, no dependencies.
"""

import argparse
import fnmatch
import json
import os
import sys

SIZE_SUFFIXES = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}


def parse_size(text):
    """Parse a human size like '10MB', '512KB', '100' (bytes) into bytes."""
    text = text.strip().upper()
    for suffix in ("GB", "MB", "KB", "B"):
        if text.endswith(suffix):
            number = text[: -len(suffix)].strip()
            try:
                return int(float(number) * SIZE_SUFFIXES[suffix])
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"invalid size: {text!r} (expected e.g. 10MB, 512KB, 100)"
                )
    try:
        return int(float(text))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid size: {text!r} (expected e.g. 10MB, 512KB, 100)"
        )


def human_size(num_bytes):
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            if unit == "B":
                return f"{num_bytes} B"
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"  # pragma: no cover


def _is_excluded(name, patterns):
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def scan(root, exclude=(), follow_symlinks=False):
    """Walk root and collect usage stats.

    Returns a dict with total bytes, file/dir counts, a list of
    (size, path) for every file found, per-extension totals, and
    per-top-level-subdirectory totals. Unreadable files/dirs are
    skipped silently; symlinked dirs are not followed unless asked.
    """
    root = os.path.abspath(root)
    total_bytes = 0
    file_count = 0
    dir_count = 0
    files = []  # (size, path)
    by_extension = {}
    by_subdir = {}

    for dirpath, dirnames, filenames in os.walk(
        root, followlinks=follow_symlinks
    ):
        dir_count += 1
        # Prune excluded directories in place so os.walk skips them.
        dirnames[:] = [
            d for d in dirnames if not _is_excluded(d, exclude)
        ]
        rel = os.path.relpath(dirpath, root)
        top = rel.split(os.sep)[0] if rel != "." else "."
        for name in filenames:
            if _is_excluded(name, exclude):
                continue
            path = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            total_bytes += size
            file_count += 1
            files.append((size, path))
            ext = os.path.splitext(name)[1].lower() or "(no extension)"
            by_extension[ext] = by_extension.get(ext, 0) + size
            by_subdir[top] = by_subdir.get(top, 0) + size

    return {
        "root": root,
        "total_bytes": total_bytes,
        "file_count": file_count,
        "dir_count": dir_count,
        "files": files,
        "by_extension": by_extension,
        "by_subdir": by_subdir,
    }


def summarize(stats, top=10, depth=1, min_size=0):
    """Reduce raw scan stats into the report dict."""
    files = [f for f in stats["files"] if f[0] >= min_size]
    files.sort(key=lambda item: (-item[0], item[1]))
    largest_files = [
        {"path": path, "size_bytes": size} for size, path in files[:top]
    ]
    subdirs = sorted(
        stats["by_subdir"].items(), key=lambda item: (-item[1], item[0])
    )
    if depth <= 0:
        subdirs = []
    elif depth == 1:
        # Only immediate subdirectories (plus "." for files at the root).
        subdirs = [
            {"path": name, "size_bytes": size}
            for name, size in subdirs[:top]
        ]
    extensions = sorted(
        stats["by_extension"].items(), key=lambda item: (-item[1], item[0])
    )
    return {
        "root": stats["root"],
        "total_bytes": stats["total_bytes"],
        "file_count": stats["file_count"],
        "dir_count": stats["dir_count"],
        "largest_files": largest_files,
        "largest_subdirs": subdirs,
        "by_extension": [
            {"extension": ext, "size_bytes": size}
            for ext, size in extensions
        ],
    }


def format_text(report):
    """Render the report as human-readable text."""
    lines = [
        f"Root:  {report['root']}",
        f"Total: {human_size(report['total_bytes'])} "
        f"({report['total_bytes']} bytes)",
        f"Files: {report['file_count']} in "
        f"{report['dir_count']} directories",
        "",
        "Largest files:",
    ]
    if report["largest_files"]:
        for entry in report["largest_files"]:
            lines.append(
                f"  {human_size(entry['size_bytes']):>10}  {entry['path']}"
            )
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Largest subdirectories:")
    if report["largest_subdirs"]:
        for entry in report["largest_subdirs"]:
            lines.append(
                f"  {human_size(entry['size_bytes']):>10}  {entry['path']}"
            )
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("By extension:")
    if report["by_extension"]:
        for entry in report["by_extension"]:
            lines.append(
                f"  {human_size(entry['size_bytes']):>10}  "
                f"{entry['extension']}"
            )
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize disk usage of a directory tree."
    )
    parser.add_argument(
        "path", nargs="?", default=".",
        help="directory to analyze (default: current directory)",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="how many largest files/subdirs to list (default: 10)",
    )
    parser.add_argument(
        "--depth", type=int, default=1,
        help="subdirectory depth to report; 0 hides subdirs (default: 1)",
    )
    parser.add_argument(
        "--min-size", type=parse_size, default=0,
        help="ignore files smaller than SIZE, e.g. 10MB (default: 0)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="print the report as JSON instead of text",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=[],
        metavar="PATTERN",
        help="skip files/dirs matching a glob, e.g. '*.pyc' '__pycache__'",
    )
    parser.add_argument(
        "--follow-symlinks", action="store_true",
        help="follow symlinked directories (off by default)",
    )
    args = parser.parse_args(argv)

    if not os.path.isdir(args.path):
        print(
            f"dusage: {args.path!r} is not a directory",
            file=sys.stderr,
        )
        return 2

    stats = scan(
        args.path,
        exclude=args.exclude,
        follow_symlinks=args.follow_symlinks,
    )
    report = summarize(
        stats, top=args.top, depth=args.depth, min_size=args.min_size
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
