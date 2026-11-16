# dusage

Summarize disk usage of a directory tree: total size, file and directory
counts, the largest files, the largest subdirectories, and a breakdown by
file extension. Pure Python standard library — no dependencies.

## Usage

```bash
python3 dusage.py [PATH] [--top N] [--depth N] [--min-size SIZE] [--json]
                  [--exclude PATTERN ...] [--follow-symlinks]
```

```bash
# Summarize the current directory
python3 dusage.py

# Top 5 largest files in ~/projects, ignoring anything over 1 MB only
python3 dusage.py ~/projects --top 5 --min-size 1MB

# Machine-readable output, skipping caches
python3 dusage.py . --json --exclude '__pycache__' '*.pyc'
```

Sizes accept suffixes: `B`, `KB`, `MB`, `GB` (e.g. `--min-size 10MB`).

## Exit codes

- `0` — report printed
- `2` — path missing or not a directory

## Example output

```
Root:  /home/ujjwal/projects
Total: 48.2 MB (50542592 bytes)
Files: 312 in 41 directories

Largest files:
    12.4 MB  /home/ujjwal/projects/app/data.db
     3.1 MB  /home/ujjwal/projects/app/logo.png

Largest subdirectories:
    20.1 MB  app
     5.6 MB  docs

By extension:
    15.2 MB  .db
     9.8 MB  .py
```

## Tests

```bash
python3 -m pytest tests/ -q
```

## Author

Ujjwal Bhatia — MIT License.
