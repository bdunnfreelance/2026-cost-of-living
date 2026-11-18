# Power BI starter assets

These files support the local actuals report. They contain no transaction data.

## Connect the report

1. In Power BI Desktop, open the existing `Cost of Living.pbix` or create a new report.
2. Create a blank query for `transactions` using `Transactions.m` in Advanced Editor.
3. If the project is not at `C:\Dev\2026 CostOfLiving`, update the `ProjectRoot` value in the query.
4. Load the single query; no model relationship is required because category group and cash flow are joined into each transaction row.
6. Add the measures from `Actuals Measures.dax` to the `transactions` table.

`Payment Category` is the effective category assigned by the current manual/rule mappings. `Category Group`, `Cash Flow`, and `Comment` are looked up from that category on each transaction. These fields are blank when no category matched. The export contains the 18 required transaction and category fields; Power BI handles date grouping from `Date`. Internal source hashes and import metadata are not included.

After bank data or mapping changes, run the project's `export-actuals` command, then refresh the report.

## First actuals page

- Cards: Actual Spending, Actual Income, Net Cash Flow, Uncategorised Transactions.
- Monthly line chart: `Date` on the axis, Actual Spending and Actual Income as values.
- Bar chart: `Category Group` or `Payment Category` by Actual Spending.
- Slicers: date, account, Category Group, and Cash Flow.
- Detail table: Date, Account, Description, Debit, Credit, and Payment Category.

Budget targets are intentionally omitted until the actuals view has been reviewed. Keep the report local; do not publish it to Power BI Service.
