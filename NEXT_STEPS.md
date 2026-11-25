# Next Steps

**Coming back to the project?** Run `col-status.bat`, then read the first unchecked step below.

```powershell
col-status.bat
```

(Or `col status`. After new bank files or workbook changes, run `col-update.bat`. See the README for the `.bat` shortcuts.)

`status` is read-only. It reports what has been imported, loaded and exported, flags anything
out of date, and prints the command to run next. This file holds the planned work that `status`
can't know about.

## Working rules

- One step at a time. Finish and check a step before starting the next.
- Each step has a **Done when** check. If you can't tell whether a step was done, run its check.
- When a step is finished, tick it here and commit this file with the work.
- Never commit bank data, the database, Parquet files, the reference workbook or populated Power BI reports.
- After each step Claude gives a one-line description of the next step.

## Part 1: Excel reference data (nearly finished)

- [x] Commit the DuckDB, categorisation and Power BI starter work.
- [x] Load categories, manual mappings and rules from the Excel workbook (`load-mappings`).
      *Done when:* `load-mappings` prints 118 categories, 4 manual mappings, 422 rules (or your current counts).
- [ ] Export and check the Parquet file.
      *Done when:* `export-actuals` succeeds, `show --limit 25` has sensible categories and groups, and `status` shows the export up to date.
- [ ] Commit the Excel and schema change, including `status` and this file.
      *Done when:* `git status` is clean (`status` shows Git OK).
- [ ] Update the older docs that still describe the CSV loader: `Project Handover.md`, `Cost_of_Living_Status.md`, `CLI Usage.md`.
      *Done when:* none of them mention the three reference CSVs or `categorization.py`.

## Deploy to Live (first real data)

Dev: `C:\Dev\2026 Cost of Living`. Live: `C:\App\2026 Cost of Living`. Live data is never touched by the deploy script.

- [ ] Dry run: `powershell -ExecutionPolicy Bypass -File ".\scripts\deploy-to-live.ps1" -DryRun`
- [ ] First deploy: the same command with `-SetupVenv` instead of `-DryRun`.
      *Done when:* Live has `src`, the `.bat` files, `doc\CLI Usage.md`, `pyproject.toml` and a `.venv`.
- [ ] Put the real bank CSVs in Live `data\1. extract` and the real workbook in Live `data\9. reference`, then run `import`, `load-mappings`, `export-actuals` and `status` from the Live folder.
- [ ] Point the Live Power BI report at the Live `transactions.parquet`.

Redeploy after later code changes with the same script (no `-SetupVenv` unless `pyproject.toml` changed).

## Part 2: Importer clean-up

- [x] Fix the bank CSV adapter order so a standard-layout file (Bank, Account, Date, Description, Debit, Credit) isn't treated as St George.
- [x] Account names now come from the filename (`<dates> <bank> - <account no> - <account name>.csv`). Check they match the Account values used in your manual mappings.
- [ ] Decide how to handle overlapping bank exports (currently not de-duplicated).

## Data loading rules

- Never exclude a row. Blank or bad values load as NULL (or the `(blank)` placeholder for categories) and are described in the `Data Status` column; fix them in the source (Excel or the bank file).
- Completely blank rows are ignored.
- Only an unreadable file, a missing sheet or column header, or a filename that doesn't give the account stops the load.
- Power BI: a table of rows where `Data Status` is not `OK` lists everything to fix.

## Part 3: Power BI

- [ ] Refresh the Parquet source in Power BI Desktop and confirm all 19 columns load (including `Data Status`).
      *Done when:* a few rows match `show` output, and uncategorised rows have blank category fields.
- [ ] Cost of Living page, yearly matrix: Cash Flow = Regular; rows Category Group, Payment Category, Account, Description; columns Year; values Debit.
- [ ] Cost of Living page, monthly matrix for the chosen year.
- [ ] Income page, yearly and monthly matrices (values Credit).
- [ ] Decide on the mapping diagnostic fields (Times Used in Mapping/Rules, comparison fields): small separate tables exported from DuckDB, or leave out for now.
      *Note:* Power BI needs DAX only where a calculation depends on filters (budget variance, % of budget). The totals above need none.

## Part 4: Budget and wrap-up

- [ ] Supply monthly budget amounts and decide how they are stored (a sheet in the workbook is the likely home).
- [ ] Budget-versus-actual measures and visuals.
- [ ] Check the Git remote is private, then push.
- [ ] Back up the `data` folder to a secure location and test a restore.
