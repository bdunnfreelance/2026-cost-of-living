# Cost of Living Project — Status

For the requirement-by-requirement Power BI handover and recommended work sequence, see [Project Handover.md](Project%20Handover.md).

## Goal

Build a simple, local-first household cost-of-living and financial analysis project from bank transaction CSV files. The end goal is a dashboard that shows how the household is tracking against its budget and lets us drill down into where expenses are occurring.

## Decisions

- Prioritise a working version on Windows; Linux/Kubuntu portability can be revisited later.
- Use Python for CSV import and cleanup, DuckDB for a local file-based database, and Power BI Desktop for budget summaries and charts.
- Keep financial data local. Do not publish reports to Power BI Service or commit bank exports, databases, or reports containing transaction data.
- Keep project code and data in separate locations where practical. The current `data/` folder is inside the project but is excluded from Git.

## First-version specification

The current Excel prototype is documented in [Excel Prototype.md](Excel%20Prototype.md) and is the starting specification for the app. It describes:

- A normalized transaction ledger with bank/account, date, description, debit/credit, optional balance, and bank-provided categories.
- Budget categories grouped into higher-level category groups, with cash-flow types: Regular, One-off, Transfer, and Unused.
- Manual category mappings for exceptions and text-search mapping rules for recurring descriptions.
- Mapping diagnostics, including rule matches, uncategorized transactions, mapping usage, and category totals.
- Yearly and monthly income and expense summaries, drillable by category group, category, account, and description.
- A dashboard outcome: show progress against budget and allow drill-down into expense detail.

Prototype reference data is now stored in the ignored `data/9. reference/` folder: `Prototype - Budget Categories.csv`, `Prototype - Mapping Rules.csv`, and `Prototype - Description Mapping (sample).csv`. These provide the category/group/cash-flow list, matching rules, and examples of account-specific manual mappings. The budget categories file contains usage counts and historical amounts, but it does not contain planned budget amounts.

The category list and mapping rules are now supplied. The manual mapping sample uses an account-plus-description key (`DescId`), so use that for manual overrides. Mapping rules apply in this order: specific Payee rules first, then generic Vendor Type rules; within each type, use row order. Planned budget amounts and their period (for example, monthly category amounts or annual amounts distributed monthly) are not yet supplied. The sample manual mapping file is only a sample, not the full mapping table. The user is deciding how much personal mapping data Codex may see and whether development and live data should be separated.

## Current status

- Project folder: `C:\Dev\2026 CostOfLiving`.
- Git repository initialized; there are no commits yet.
- Python 3.13 environment is set up in `.venv/`; DuckDB is declared in `pyproject.toml`.
- The admin CLI imports CSVs into `data/2. transform/cost_of_living.duckdb`, normalizes transactions, preserves source rows, and skips an identical source file by fingerprint. It does not deduplicate overlapping exports because the source data currently has no unique transaction ID.
- Bank import adapters now cover the supplied Westpac, St George Visa, St George Work, and headerless Bendigo samples. Bendigo's account is `Savings`; negative amounts map to Debit and positive amounts to Credit.
- Reference CSVs are stored in `data/9. reference/`; bank exports are kept in `data/1. extract/` and only the latter is scanned by the import command.
- `transactions_enriched` is a DuckDB view that calculates manual category, rule-based category, effective payment category, match explanation, category group, and cash-flow type.
- `monthly_actuals` and `yearly_actuals` views summarize debit, credit, net amount, and transaction count by period, category group, category, cash-flow type, and account. Budget targets are still pending.
- The CLI exports one enriched Parquet dataset under `data/3. load/` with 18 transaction and category fields, including mapping diagnostics and category metadata. Power BI handles date grouping and calculates monthly and yearly totals from transactions.
- The database stores `source_sha256` as a content fingerprint to skip reimporting identical files and identify rows from a source file; the original filename is stored separately in `source_name`. The hash is not exported to Power BI.
- A first-report guide in `doc/Power BI Actuals Dashboard.md` gives the Power BI Parquet import steps, actuals measures, and suggested visuals.
- Power Query and DAX starter assets are in `powerbi/`: a query for the transaction Parquet file, actuals measures, and a setup guide. The user confirmed Power BI refreshed the current single-table export.
- The four supplied bank samples were imported into a temporary database during verification: 21 rows normalized successfully. Synthetic and sample checks also confirmed the enriched view fields.
- `.gitignore` excludes `.venv/`, `data/`, DuckDB files, Power BI files, generated exports, and local environment files.
- Budget-versus-actual analysis remains deferred until monthly budget amounts are supplied.
- The working tree currently contains uncommitted code and documentation changes. Review them before creating the first commit or connecting a remote repository.

## Next steps

1. Confirm the single enriched Parquet export loads in Power BI and inspect actuals totals and category fields.
2. Review and refine the actuals dashboard in Power BI before starting budget work.
3. Add monthly budget amounts when ready, then build budget-versus-actual summaries by category group, category, account, and description.
4. Review Git status and staged changes before a first commit; financial data and reports remain excluded.

Mapping category names that differ from the category list only by capitalization are now normalized to the category-list spelling when reference files load. Truly unknown category names remain allowed and produce warnings.

Continue one step at a time and review each outcome before moving on.

## Security and backup

- Never commit bank CSVs, the `.duckdb` database, Power BI reports with imported transactions, or exports containing transaction data.
- `data/` is currently inside the Git project, but `.gitignore` excludes it. Check Git status and staged changes before every commit or push.
- Keep sensitive data outside OneDrive/Dropbox or other synced folders if the goal is to avoid cloud copies.
- Keep the Power BI report local; do not publish it to Power BI Service.
- Back up the local database separately to a secure offline location. Cloud backup should contain only code and non-sensitive documentation.
