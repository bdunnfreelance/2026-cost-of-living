# 2026 Cost of Living

A local-first household transaction analysis project. Bank exports and the DuckDB
database stay on this computer; only source code and non-sensitive documentation
belong in Git.

## Project layout

```text
2026 CostOfLiving/
  src/cost_of_living/
    __init__.py           # Python package marker
    cli.py                # CSV importer and database commands
  data/                   # Local CSV files and DuckDB database; ignored by Git
  doc/                    # Project handover and notes
  .venv/                  # Local Python environment; ignored by Git
  pyproject.toml          # Package metadata and dependencies
  .gitignore              # Keeps data and generated files out of Git
  README.md
```

In VS Code, expand `src`, then `cost_of_living` in the Explorer to see the
Python source. The main code is in `src/cost_of_living/cli.py`.

## CSV import and database browsing

The first supported CSV layout uses `Bank`, `Account`, `Date`, `Description`,
`Debit`, and `Credit`; `Balance`, `Category`, and `SubCategory` are optional.
Headers are matched without case or surrounding whitespace, and dates accept
Australian day/month/year or ISO format. Each source row is kept as JSON in
`transactions_raw` and also mapped to typed columns in `transactions`. `amount`
is calculated as Credit minus the absolute Debit, so expenses are negative and
credits or refunds are positive. The normalized `debit` column is always
nonnegative; the original source values remain unchanged in `transactions_raw`.

The importer records a SHA-256 fingerprint for each source file and skips an
identical file on later runs. It keeps rows from different files even when they
look identical: the current spreadsheet has no unique transaction ID, so
overlapping exports need a later review before they can be safely deduplicated.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\cost-of-living.exe import .\data
```

By default the local database is `data/transactions.duckdb`. The `data` folder
is excluded from Git. Review `git status` before every commit or push. The
provided sample is loaded locally; it contains 14 normalized rows. To view the
normalized table in the terminal, run `cost-of-living show` (or add
`--limit 100` to display more rows). To browse the database in DuckDB's local
web interface, run `cost-of-living browse`; the interface is at
`http://localhost:4213` while the command remains running. Press Ctrl+C in the
terminal to stop it. DuckDB may download its official UI extension the first
time this command runs.
