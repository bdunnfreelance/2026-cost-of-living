-- Land the three reference sheets from the Excel workbook as-is (all text).
-- Needs the DuckDB excel extension. The admin CLI replaces {workbook} and the
-- {sheet_...} placeholders (sheet names are set at the top of database.py);
-- to run this by hand in the DuckDB UI, replace them yourself.
-- Only the raw columns are read, by header name; formula/debug columns are ignored.
-- sheet_row is the data row number on the sheet (first row under the header = 1).

CREATE OR REPLACE TABLE extract.ref_categories AS
SELECT row_number() OVER () AS sheet_row,
       "Payment Category", "Category Group", "Cash Flow", "Comment"
FROM read_xlsx('{workbook}', sheet = '{sheet_categories}', all_varchar = true);

CREATE OR REPLACE TABLE extract.ref_manual_map AS
SELECT row_number() OVER () AS sheet_row,
       "Account", "Description", "Manual Category"
FROM read_xlsx('{workbook}', sheet = '{sheet_manual_map}', all_varchar = true);

CREATE OR REPLACE TABLE extract.ref_rules AS
SELECT row_number() OVER () AS sheet_row,
       "Rule Type", "MatchText", "Payment Category", "Comment"
FROM read_xlsx('{workbook}', sheet = '{sheet_rules}', all_varchar = true);
