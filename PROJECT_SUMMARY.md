# Cost of Living Project Summary

## Purpose

Build a local-first household finance tool that imports bank CSVs, categorizes transactions, and ultimately provides a dashboard for tracking actual spending against budget with drill-down into expenses.

## Project location and privacy

- Project: `C:\Dev\2026 CostOfLiving`
- Local database: `data\2. transform\cost_of_living.duckdb`
- Bank exports: `data\1. extract\`
- Transform database: `data\2. transform\cost_of_living.duckdb`
- Power BI export: `data\3. load\transactions.parquet`
- Reference workbook: `data\9. reference\2026 Cost of Living - Reference.xlsx`
- Keep live financial data and databases local; do not commit them or publish reports containing them.
- Develop using synthetic or redacted data where practical. The `data/` directory and DuckDB files are excluded from Git.

## Current design

- Python CLI for administration and CSV import.
- DuckDB stores transactions, budget categories, manual mappings, and text mapping rules in three schemas: `extract` (raw), `transform` (cleaned + enriched view), `present` (Power BI and reporting views).
- Reference data is read from the Excel workbook with DuckDB's `excel` extension (sheets `Categories`, `Description Mapping`, `Mapping Rules`); the SQL is in `src/cost_of_living/sql/`.
- The CLI exports one enriched transaction table to Parquet for Power BI's native Parquet connector.
- Power BI Desktop is used locally; the report is not to be published to Power BI Service.
- CSV imports require `Bank`, `Account`, `Date`, `Description`, `Debit`, and `Credit`; `Balance`, `Category`, and `SubCategory` are optional.
- Re-importing the exact same CSV content is skipped. Overlapping exports with different contents are not yet deduplicated at transaction level.
- Categorization precedence: manual account-plus-description mapping, then specific Payee/Payer rules in row order, then generic Vendor Type rules in row order.
- A mapping can reference a category not yet in the category table; the loader retains it and reports a warning to add the category.
- Planned budget amounts and their period have not been supplied yet.

## Key files

- `src\cost_of_living\admin_cli.py` — project administration CLI and bank CSV import.
- `src\cost_of_living\database.py` — schema setup, Excel reference loading and checks.
- `src\cost_of_living\sql\` — schema, reference-load and view SQL.
- `doc\Excel Prototype.md` — first-version functional specification based on the Excel prototype.
- `doc\CLI Usage.md` — commands, default paths, and effects.
- `doc\Cost_of_Living_Status.md` — detailed progress and next steps.
- `data\9. reference\2026 Cost of Living - Reference.xlsx` — categories, manual mappings and mapping rules.

## CLI commands

Run from the project virtual environment:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py
```

With no command, the CLI displays command summaries and its resolved default file locations.

Import bank CSV files from `data\1. extract\`:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py import
```

Load the Excel reference workbook into DuckDB:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py load-mappings
```

Export the enriched transaction dataset to Parquet for Power BI:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py export-actuals
```

The single file `data\3. load\transactions.parquet` contains 19 transaction, mapping diagnostic, and category fields, including `Data Status` ('OK' or what needs fixing in the source data). Power BI calculates monthly and yearly totals from transaction detail; no separate category relationship is needed.

The mapping load replaces existing category and mapping table contents in the selected database. `show` reads and displays transaction rows; `browse` starts DuckDB's local browser interface.

## Next steps

1. Review actuals totals and refine the local Power BI dashboard.
2. Decide how to avoid or review overlapping bank exports before routine imports.
3. Add planned budget amounts and a budget period when available.
4. Back up live data and references to a secure destination, then verify a restore.
