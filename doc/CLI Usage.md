# Command-line tool usage

This is the admin tool for the Cost of Living project. It finds the project root automatically, so you can run it from another working folder without entering project paths.

Project files used by default:

- Database: `data/2. transform/cost_of_living.duckdb`
- Bank CSVs: `data/1. extract/`
- Reference CSVs: `data/9. reference/` (separate from the bank CSV landing zone)
- Categories: `data/9. reference/Prototype - Budget Categories.csv`
- Mapping rules: `data/9. reference/Prototype - Mapping Rules.csv`
- Manual mapping sample: `data/9. reference/Prototype - Description Mapping (sample).csv`

The database, extract folder, and reference files are resolved relative to the project installation. The paths are shown in CLI help. The importer scans only `data/1. extract/`, so reference files are not considered transaction imports.

## First-time setup

Install the project into its virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

**Effect:** installs or updates this project in `.venv`; it does not read or change transaction data.

## Import bank transactions

Import all bank transaction CSV files placed in the project's `data/1. extract/` folder:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli import
```

You can also select a different source folder or a single CSV if needed:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli import "D:\\Bank Exports"
```

**Effect:** writes transaction rows and source-file records to the selected DuckDB database. Identical files are skipped. Review the source folder and database path first; use only local/private data locations.

Westpac and St George exports are recognized from their column headers; St George account labels come from `Visa` or `Work` in the filename. The headerless Bendigo sample layout is read as `transaction_date`, signed `amount`, and `description`, using account `Savings`; negative amounts become Debit and positive amounts become Credit. Standard bank CSVs use `Bank`, `Account`, `Date`, `Description`, `Debit`, and `Credit`; `Balance`, `Category`, and `SubCategory` are optional. The importer scans only the landing zone. Identical file contents are skipped on later imports. Exports that overlap but differ as files are retained; transaction-level deduplication is not implemented.

Choose a different database with `--database`:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli import ".\data\incoming" --database ".\data\dev.duckdb"
```

## Load categories and mapping tables

Load the project's categories, mapping rules, and description-mapping sample into the default DuckDB database:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli load-mappings `
```

Pass `--categories`, `--rules`, or `--database` only when you want to use a different file:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli load-mappings `
  --categories ".\data\9. reference\Prototype - Budget Categories.csv" `
  --rules ".\data\9. reference\Prototype - Mapping Rules.csv" `
  --manual ".\data\9. reference\Prototype - Description Mapping (sample).csv" `
  --database ".\data\dev.duckdb"
```

**Effect:** replaces the category, rule, and manual-mapping table contents in the selected database, then refreshes the `transactions_enriched` view. The view calculates `manual_category`, `rule_based_category`, `payment_category`, and `matching_rule` when queried. Close any DuckDB CLI session using the database before running this command.

The supplied description-mapping sample is loaded by default. To use another manual mapping file:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli load-mappings `
  --categories ".\data\9. reference\Prototype - Budget Categories.csv" `
  --rules ".\data\9. reference\Prototype - Mapping Rules.csv" `
  --manual ".\path\to\description-mappings.csv"
```

Each load replaces the current category, rule, and manual mapping table contents in the selected database. A mapping can reference a category absent from the category list; it is retained and the command warns that the category should be added.

## View transactions

Show up to 50 transactions (the default):

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli show
```

**Effect:** reads and displays transaction rows; it does not modify the database. The descriptions may contain personal information.

Change the row limit or database:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli show --limit 100 --database ".\data\dev.duckdb"
```

## Export actuals for Power BI

Generate the single enriched transaction Parquet file from DuckDB:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py export-actuals
```

The default output folder is `data/3. load/`. It contains `transactions.parquet` with 18 transaction and category fields, including the effective Payment Category, mapping diagnostics, and category metadata. `Mth/Yr` is omitted because Power BI can group the Date field. The command overwrites this export and removes obsolete exports. In Power BI Desktop, use **Get Data > Parquet** to import the single file. After importing new transactions or refreshing mappings, run `export-actuals` again and refresh the file in Power BI.

## Browse the DuckDB database

Start the local DuckDB browser interface:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli browse
```

**Effect:** opens a local database browser and reads the selected database. Stop it with Ctrl+C. The browser may download its DuckDB extension on first use.

Open `http://localhost:4213` while the command is running. Press Ctrl+C in the terminal to stop it. The DuckDB interface may download its extension the first time it runs.

## General help

See available commands or command-specific options:

```powershell
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli --help
.\.venv\Scripts\python.exe -m cost_of_living.admin_cli load-mappings --help
```

**Effect:** displays command and option descriptions; it does not access the database.

## Data handling

The default `data/` folder and DuckDB files are excluded from Git. Keep live transaction exports, the live database, and complete personal mapping files in a local-only location. Use synthetic or redacted data while developing.
