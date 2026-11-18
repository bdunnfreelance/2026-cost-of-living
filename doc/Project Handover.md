# Project Handover — Cost of Living

**Prepared:** 16 November 2026  
**Project:** `C:\Dev\2026 CostOfLiving`  
**Purpose:** Continue building the Power BI version of the Excel prototype. Treat `Excel Prototype.md` as the functional specification and this handover as the current implementation snapshot.

## Goal and decisions

Build a local-first household finance tool that imports bank CSVs, categorizes transactions, and reproduces the useful analysis in the Excel prototype in Power BI. The first dashboard milestone is actual income and expenses; budget-versus-actual work comes later, after actuals are reviewed. Budget targets will be monthly.

- Python admin CLI imports and normalizes transactions into DuckDB.
- DuckDB remains the local in-process database and holds transaction, reference, and mapping data.
- Power BI Desktop reads local Parquet exports. Do not publish the report or transaction data to Power BI Service.
- Do not commit bank data, the database, Parquet exports, or reports containing transaction details.
- The user asked that after each completed step, the response include a one-line description of the next step.

## Implemented

### Import, database, and categorization

- Import adapters exist for Westpac, St George Visa, St George Work, and the supplied headerless Bendigo format. Bendigo is labeled `Savings`; negative amount becomes Debit and positive amount becomes Credit.
- Normalized transactions and original raw CSV rows are stored in DuckDB. Reference category, manual mapping, and mapping-rule tables are in DuckDB.
- Manual mapping uses account plus full description and takes precedence over rules.
- Rule matching checks specific Payee rules first, then generic Vendor Type rules; row order is retained within each type.
- `transactions_enriched` computes the effective Payment Category and the Manual Category, Rule Based Category, Matching Rule, Category Group, and Cash Flow fields.
- Unknown categories are allowed; loading reference data warns when mappings use a category absent from the category table.
- The importer uses a SHA-256 hash of the **file contents** to skip already imported identical files. It stores the actual file name separately in `source_name`. The hash is not a hash of the file name.
- The importer does not deduplicate overlapping bank exports because there is no stable bank transaction ID.

### Current Power BI exports

`admin_cli.py export-actuals` writes one file, `data/3. load/transactions.parquet`, with 18 fields: `Bank`, `Account`, `Date`, `Description`, `Debit`, `Credit`, `Balance`, `Category`, `SubCategory`, `TranId`, `DescId`, `Matching Rule`, `Payment Category`, `Manual Category`, `Rule Based Category`, `Category Group`, `Cash Flow`, and `Comment`. `Mth/Yr` is omitted because Power BI can group the `Date` field. The view performs the joins and calculates mapping diagnostics; Power BI loads a single table with no relationship.

Monthly and yearly aggregate views still exist in DuckDB, but their Parquet files are no longer exported. The single transaction export contains 18 fields. Obsolete monthly/yearly/enriched CSV and Parquet export files are removed from `data/3. load/`.

Starter assets:

- `powerbi/Transactions.m`
- `powerbi/Actuals Measures.dax`
- `powerbi/README.md`
- `doc/Power BI Actuals Dashboard.md`

The DAX starter measures calculate spending, income, net cash flow, transaction count, uncategorized count, and Regular cash flow totals. The flattened Power BI table needs no relationship.

## Excel prototype requirements: completion review

### Satisfied or implemented in the database

- Normalize supported bank exports into a common transaction ledger.
- Store bank/account/date/description/debit/credit and optional balance/bank category/subcategory in DuckDB.
- Categorize with manual account-plus-description overrides before ordered description rules.
- Use the required Payee-before-Vendor-Type and row-order rule priority.
- Store category group and cash-flow labels (`Regular`, `One-off`, `Transfer`, `Unused`) in the category table.
- Calculate effective Payment Category and mapping diagnostics (manual category, rule-based category, and matching-rule explanation) in a DuckDB view.
- Allow unmapped/unknown categories and warn about category names referenced by mappings but absent from the category table.
- Calculate monthly/yearly debit and credit totals in DuckDB views; Power BI can calculate these directly from individual transactions instead.

### Partially satisfied

- **Transactions sheet:** the 18 required transaction and category fields are in the Power BI export; Power BI handles date grouping. Internal importer fields and the raw amount field remain excluded.
- **TranId:** exported using Account + Date + Description as in Excel. It may collide for same-day purchases with the same description, so do not use it as a guaranteed unique key without collision handling.
- **DescId:** exported as Account + Description; the manual mapping join compares these components case-insensitively.
- **Category Mapping:** the manual mappings work in DuckDB, but the supplied manual mapping CSV is a sample, not the full personal mapping table. The full table and development/live privacy boundary remain undecided.
- **Power BI model:** the user has refreshed the single Parquet query and confirmed the new columns appear. Visuals and totals still need review; no relationships are required for the flattened table.

### Outstanding compared with the Excel prototype

- **Budget Categories debug fields:** `Times Used in Mapping`, `Amount in Category`, and `Times Used in Rules` are not implemented as Power BI calculations or visuals.
- **Category Mapping debug fields:** transaction-level matching rule and rule-based category are exported. Mapping-level occurrences, first date, total debits/credits, and `Blank Rule`/`Same`/`Manual Blank`/`Different` comparison are not implemented in Power BI.
- **Mapping Rules diagnostics:** category-group check and times-used counts are not shown in Power BI. The missing-category warning is available when reference files are loaded in DuckDB, not as a report page.
- **Cost of Living and Income pages:** the Excel yearly and monthly matrices have not been built and verified in Power BI. They need the Regular Cash Flow filter, year/month pivots, category group > payment category > account > description drill-down, and Debit or Credit values respectively.
- **Date and transaction helper fields:** `Date`, `TranId`, and `DescId` are exported; Power BI can group Date by month/year without an `Mth/Yr` field.
- **Budget dashboard:** planned amounts have not been provided. Once actuals are reviewed, add monthly budget input and budget-versus-actual visuals.

## Important design question to resolve

The updated Excel specification now makes the mapping joins explicit:

- Manual mapping (`m`) matches a transaction (`t`) on `DescId`, defined as `Account|Description`.
- A mapping rule (`r`) matches when `MatchText` is found in the transaction description. Apply Payee rules before Vendor Type rules, retaining row order within each type.
- Category Group (`c`) associates with manual mappings through `c.Payment Category = m.Manual Category` and with rules through `c.Payment Category = r.Payment Category`.
- For transaction reporting, use the effective Payment Category (manual mapping first, then the highest-priority matching rule) to resolve Category Group and Cash Flow. Keep the manual and rule paths available separately for mapping diagnostics.

The requirement is one flattened transaction table. Every mapping is many-to-one at transaction grain: manual mapping by account plus description, the selected highest-priority matching rule, and category metadata by effective Payment Category. The export includes transaction helper and mapping diagnostic fields as well as the category metadata.

For diagnostics and extra detail, decide whether to:

1. Add the required debug/detail columns to the single transaction export; or
2. Create separate diagnostic datasets while keeping the actuals model as one transaction table.

Keep `Payment Category` as the effective mapped category field. `Matching Rule` carries the explanation text.

## Recommended remaining steps

1. Open the local `Cost of Living.pbix` in Power BI Desktop and load the single `transactions.parquet` source using `powerbi/Transactions.m`.
2. Confirm all 18 exported columns load and that the effective category and category metadata are blank for uncategorized rows. Verify a few manually mapped and rule-mapped rows against DuckDB; manual mapping by account plus description wins, then rules use Payee priority and row order.
3. Build the Excel-equivalent **Cost of Living** and **Income** monthly/yearly matrix pages with Regular cash-flow filtering and hierarchy drill-down. Validate totals against DuckDB views or the Excel prototype.
4. Review the remaining mapping/category debug requirements, then add the required columns to the single transaction export or create separate diagnostic datasets.
5. Review actuals with the user and refine the dashboard before adding budgets.
6. Obtain monthly budget amounts and confirm category/period semantics, then add budget-versus-actual measures and visuals.
7. Review Git changes and privacy boundaries before any first commit; keep all financial data and populated Power BI reports out of Git.

## Current project state and commands

- Main status: `doc/Cost_of_Living_Status.md`.
- Prototype specification: `doc/Excel Prototype.md`.
- Power BI guide: `doc/Power BI Actuals Dashboard.md`.
- Export command, from project root:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py export-actuals
```

- Import bank CSVs from `data/1. extract/` with `admin_cli.py import`.
- Load categories/rules/manual mapping sample with `admin_cli.py load-mappings`.
- The project has uncommitted changes and no first commit yet. The local PBIX file exists, but its current report content/refresh has not been verified in Power BI Desktop.
