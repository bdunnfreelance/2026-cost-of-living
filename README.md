# 2026 Cost of Living

A local-first household transaction analysis project. Bank exports and the DuckDB
database stay on this computer; only source code and non-sensitive documentation
belong in Git.

## First stage: raw CSV import

The importer stores each row as JSON so different bank CSV layouts can be loaded
before choosing a common transaction schema. It records a SHA-256 fingerprint
for each source file and skips identical files on later runs.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\cost-of-living.exe import .\data
```

By default the local database is `data/transactions.duckdb`. The `data` folder
is excluded from Git. Review `git status` before every commit or push.
