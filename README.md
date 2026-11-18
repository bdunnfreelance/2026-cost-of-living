# 2026 Cost of Living

A local-first household transaction analysis project. Bank exports and the DuckDB
database stay on this computer; only source code and non-sensitive documentation
belong in Git.

## Project layout

```text
2026 CostOfLiving/
  src/cost_of_living/
    __init__.py           # Python package marker
    admin_cli.py          # Import, mapping administration, and database commands
    categorization.py     # Manual mappings and ordered category rules
  data/
    1. extract/           # Raw bank exports; ignored by Git
    2. transform/         # DuckDB database and local tools; ignored by Git
    3. load/              # Power BI Parquet input; ignored by Git
    9. reference/          # Categories and mapping files; ignored by Git
  doc/                    # Project handover and notes
  .venv/                  # Local Python environment; ignored by Git
  pyproject.toml          # Package metadata and dependencies
  .gitignore              # Keeps data and generated files out of Git
  README.md
```

In VS Code, expand `src`, then `cost_of_living` in the Explorer to see the
Python source. The command-line tool is `src/cost_of_living/admin_cli.py`.

## Transaction categorization

`cost_of_living.categorization` loads the reference CSVs into DuckDB tables.
The `transactions_enriched` view calculates the manual category, rule category,
effective payment category, and matching-rule explanation. Manual
account-plus-description mappings take precedence, followed by Payee/Payer
rules in row order, then Vendor Type rules in row order. Keep complete personal
mapping files outside Git.

## CSV import and database browsing

See [CLI Usage](doc/CLI%20Usage.md) for command examples and database options.

The importer supports the standard `Bank`, `Account`, `Date`, `Description`,
`Debit`, and `Credit` layout, the supplied Westpac and St George layouts, and
the headerless Bendigo sample layout. Bendigo uses `Savings` as the account and
maps negative signed amounts to Debit and positive amounts to Credit. For
St George samples, account labels (`Visa` or `Work`) are taken from the filename.
`Balance`, `Category`, and `SubCategory` are optional where provided. Headers
are matched without case or surrounding whitespace, and dates accept
Australian day/month/year or ISO format. Each source row is kept as JSON in
`transactions_raw` and also mapped to typed columns in `transactions`. `amount`
is calculated as Credit minus the absolute Debit, so expenses are negative and
credits or refunds are positive. The normalized `debit` column is always
nonnegative; the original source values remain unchanged in `transactions_raw`.

The importer records each source filename and a SHA-256 fingerprint of the
file's contents. The fingerprint is not derived from the filename; it lets the
importer skip identical file contents even if a file is renamed. It keeps rows
from distinct files even when they look identical: the current exports have no
unique transaction ID, so overlapping exports need a later review before they
can be safely deduplicated.

The `transactions_enriched` view adds the effective payment category, manual
and rule-based categories, match explanation, category group, and cash-flow
type. These values are calculated from the current reference tables whenever
the view is queried.

`monthly_actuals` and `yearly_actuals` remain available as DuckDB views.
`export-actuals` writes one enriched Power BI dataset to
`data/3. load/transactions.parquet`. It contains the normalized transaction
fields, transaction identifiers, mapping diagnostics, and category metadata.
Power BI calculates monthly and yearly totals from transaction detail. The
database fingerprint and other import metadata remain internal and are excluded
from the Parquet output. Budget comparisons require planned monthly amounts,
which have not yet been provided.

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli import ".\data\1. extract"
```

By default the local database is `data/2. transform/cost_of_living.duckdb`. The `data` folder
is excluded from Git. Review `git status` before every commit or push. The
sample transaction files are in `data/1. extract/`; the current database is a development sample and should not be treated as a complete household history.

To view normalized rows in the terminal:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli show --limit 100
```

To browse in DuckDB's local web interface:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli browse
```

The interface is at `http://localhost:4213` while the command remains running.
Press Ctrl+C in the terminal to stop it. DuckDB may download its official UI
extension the first time this command runs. You can also use the DuckDB CLI
copied into `data`:

```powershell
& ".\data\2. transform\duckdb.exe" ".\data\2. transform\cost_of_living.duckdb"
```

This opens the local database in an interactive SQL prompt. The accompanying
`data/2. transform/duckdb_cheatsheet.md` has the commands you collected for browsing it.
