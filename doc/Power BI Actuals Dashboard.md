# Power BI Actuals Dashboard

This guide builds the first local Power BI report from the current Parquet actuals exports. Budget targets are intentionally out of scope for this version.

## Refresh the project export

From the project folder, run:

```powershell
.\.venv\Scripts\python.exe src\cost_of_living\admin_cli.py export-actuals
```

The export produces one Parquet dataset: `data/3. load/transactions.parquet`, with these 18 fields: `Bank`, `Account`, `Date`, `Description`, `Debit`, `Credit`, `Balance`, `Category`, `SubCategory`, `TranId`, `DescId`, `Matching Rule`, `Payment Category`, `Manual Category`, `Rule Based Category`, `Category Group`, `Cash Flow`, and `Comment`. `Mth/Yr` is omitted because Power BI can group the `Date` field. Category Group, Cash Flow, and Comment are joined into each transaction row using its effective Payment Category, so Power BI needs no separate dimension table or relationship.

## Load the data

Reusable Power Query and DAX starter files are in the project-level `powerbi/` folder. `powerbi/Transactions.m` loads the single dataset and applies expected types; change its `ProjectRoot` value if the project lives elsewhere. Measures are in `powerbi/Actuals Measures.dax`.

In Power BI Desktop:

1. Open the existing local `Cost of Living.pbix` or create a new report.
2. Create one blank query by pasting `powerbi/Transactions.m` into its Advanced Editor. Name it `transactions`.
3. Update `ProjectRoot` if needed and load the data. No relationship is needed.
4. Add the measures from `powerbi/Actuals Measures.dax`.
5. Save the report in the project folder. Power BI reports are excluded from Git.

## Measures

The provided DAX file contains these measures on the imported table `transactions`. Net Cash Flow is income minus spending because the requested export omits the database's pre-calculated `amount` field.

```DAX
Actual Spending = SUM(transactions[Debit])

Actual Income = SUM(transactions[Credit])

Net Cash Flow = [Actual Income] - [Actual Spending]

Transaction Count = COUNTROWS(transactions)

Uncategorised Transactions =
    CALCULATE(
        [Transaction Count],
        FILTER(transactions, ISBLANK(transactions[Payment Category]))
    )
```

Debit values are positive source amounts, so `Actual Spending` is a positive total. `Net Cash Flow` is income minus spending, so outflows are negative.

## Suggested first page

- Cards: Actual Spending, Actual Income, Net Cash Flow, Uncategorised Transactions.
- Line chart: `Date` by month on the axis; Actual Spending and Actual Income as values.
- Bar chart: `transactions[Category Group]` or `transactions[Payment Category]` by Actual Spending.
- Slicers: year/date, `transactions[Cash Flow]`, account, and category group.
- Detail table: Date, Account, Description, Debit, Credit, and Payment Category.

Set the category chart or slicer to focus on `Regular` cash flow when matching the Excel prototype's regular income and expense views. Keep `One Off`, `Transfer`, and `Unused` available for review.

## Refresh

After importing new bank files or changing mappings, regenerate the Parquet file with `export-actuals`, then use **Refresh** in Power BI Desktop. The report reads local files and should remain saved locally; do not publish it to Power BI Service.
