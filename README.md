# 2026 Cost of Living

A local-first household transaction analysis project. Bank exports and the DuckDB
database stay on this computer; only source code and non-sensitive documentation
belong in Git.

## First stage: raw CSV import

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
`--limit 100` to display more rows).
