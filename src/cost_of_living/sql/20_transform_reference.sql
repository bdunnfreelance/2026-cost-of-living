-- Build the cleaned reference tables from the extract.ref_* tables.
-- Every row is loaded; nothing here fails on blank or duplicate values. Run inside a transaction
-- (the admin CLI does this). Order matters: categories first.
--
-- '(blank)' is a placeholder meaning "no category given yet". The views treat it as no category and
-- flag it in the Data Status column. Duplicate keys keep the first row (as Excel's XLOOKUP does).

DELETE FROM transform.mapping_rules;
DELETE FROM transform.manual_category_mappings;
DELETE FROM transform.budget_categories;

INSERT INTO transform.budget_categories
SELECT trim("Payment Category"),
       nullif(trim("Category Group"), ''),
       nullif(trim("Cash Flow"), ''),
       nullif(trim("Comment"), '')
FROM extract.ref_categories
WHERE nullif(trim("Payment Category"), '') IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY lower(trim("Payment Category")) ORDER BY sheet_row) = 1
ORDER BY sheet_row;

-- Manual category spelling is normalised to the category list's spelling. Manual mappings are matched
-- on Description only (the Account column is kept for information but is not used to match), so only
-- the first row for each Description is kept. A row with no Description is kept (as an empty string)
-- but can never match a transaction.
INSERT INTO transform.manual_category_mappings
SELECT coalesce(trim(m."Account"), ''),
       coalesce(trim(m."Description"), ''),
       coalesce(c.payment_category, nullif(trim(m."Manual Category"), ''), '(blank)')
FROM extract.ref_manual_map AS m
LEFT JOIN transform.budget_categories AS c
  ON lower(c.payment_category) = lower(trim(m."Manual Category"))
WHERE NOT (nullif(trim(m."Account"), '') IS NULL
       AND nullif(trim(m."Description"), '') IS NULL
       AND nullif(trim(m."Manual Category"), '') IS NULL)
QUALIFY row_number() OVER (
            PARTITION BY lower(coalesce(trim(m."Description"), ''))
            ORDER BY m.sheet_row) = 1
ORDER BY m.sheet_row;

-- Priority: Payee/Payer rules (1), then Vendor Type rules (2), then rules with a missing or unknown
-- Rule Type (3); within each, sheet row order. A rule with no MatchText has nothing to match on
-- (an empty text would match every transaction), so it is left out.
INSERT INTO transform.mapping_rules
WITH cleaned AS (
    SELECT r.sheet_row,
           coalesce(trim(r."Rule Type"), '') AS rule_type,
           CASE
               WHEN lower(r."Rule Type") LIKE '%payee%' OR lower(r."Rule Type") LIKE '%payer%' THEN 1
               WHEN lower(r."Rule Type") LIKE '%vendor type%' THEN 2
               ELSE 3
           END AS rule_priority,
           trim(r."MatchText") AS match_text,
           coalesce(c.payment_category, nullif(trim(r."Payment Category"), ''), '(blank)') AS payment_category,
           nullif(trim(r."Comment"), '') AS comment
    FROM extract.ref_rules AS r
    LEFT JOIN transform.budget_categories AS c
      ON lower(c.payment_category) = lower(trim(r."Payment Category"))
    WHERE nullif(trim(r."MatchText"), '') IS NOT NULL
)
SELECT row_number() OVER (ORDER BY rule_priority, sheet_row),
       rule_priority, rule_type, match_text, payment_category, comment
FROM cleaned;
