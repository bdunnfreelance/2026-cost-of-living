-- Views. Safe to run repeatedly; they always reflect the current tables.
-- '(blank)' in a mapping or rule means "no category given yet": it is not a real category, so it is
-- ignored when working out the effective category, and flagged in Data Status.
-- A transaction with no manual mapping and no matching rule gets the default category
-- '(Not Categorised)'. Add that name to the Categories sheet (with a Category Group and Cash Flow)
-- so these transactions roll up into a Category Group in Power BI.

CREATE OR REPLACE VIEW transform.transactions_enriched AS
WITH base AS (
    SELECT
        t.*,
        manual.payment_category AS manual_category,   -- '(blank)' = mapped description with no category yet
        matched.payment_category AS rule_based_category,
        matched.match_text AS matched_text,
        COALESCE(NULLIF(manual.payment_category, '(blank)'),
                 NULLIF(matched.payment_category, '(blank)'),
                 '(Not Categorised)') AS payment_category,
        CASE
            WHEN manual.payment_category IS NOT NULL AND manual.payment_category <> '(blank)' THEN 'Exact Match'
            WHEN matched.match_text IS NOT NULL THEN 'Rule: ' || matched.match_text
            ELSE '(Uncategorised)'
        END AS matching_rule
    FROM transform.transactions AS t
    -- Manual mappings match on Description only (the Account column is not used for matching).
    -- The cleaning step keeps one row per description, so this join cannot duplicate transactions.
    LEFT JOIN transform.manual_category_mappings AS manual
      ON lower(trim(t.description)) = lower(trim(manual.description))
    LEFT JOIN LATERAL (
        SELECT rule.match_text, rule.payment_category
        FROM transform.mapping_rules AS rule
        WHERE contains(lower(t.description), lower(rule.match_text))
        ORDER BY rule.rule_id
        LIMIT 1
    ) AS matched ON TRUE
)
SELECT
    base.* EXCLUDE (matched_text),
    category.payment_category IS NOT NULL AS category_known,
    category.category_group,
    category.cash_flow,
    category.comment AS category_comment
FROM base
LEFT JOIN transform.budget_categories AS category
  ON category.payment_category = base.payment_category;

-- The single flattened table that Power BI loads (via Parquet).
-- "Data Status" is 'OK' or a '; '-separated list of what needs fixing in the source data.
CREATE OR REPLACE VIEW present.transactions AS
SELECT
    bank AS "Bank",
    account AS "Account",
    transaction_date AS "Date",
    description AS "Description",
    debit AS "Debit",
    credit AS "Credit",
    balance AS "Balance",
    category AS "Category",
    subcategory AS "SubCategory",
    concat(account, '|', strftime(transaction_date, '%Y%m%d'), '|', description) AS "TranId",
    concat(account, '|', description) AS "DescId",
    matching_rule AS "Matching Rule",
    payment_category AS "Payment Category",
    manual_category AS "Manual Category",
    rule_based_category AS "Rule Based Category",
    category_group AS "Category Group",
    cash_flow AS "Cash Flow",
    category_comment AS "Comment",
    coalesce(nullif(concat_ws('; ',   -- concat_ws skips NULLs
        data_issue,
        CASE WHEN manual_category = '(blank)' THEN 'Manual Category blank' END,
        CASE WHEN rule_based_category = '(blank)'
              AND coalesce(manual_category, '(blank)') = '(blank)' THEN 'Rule category blank' END,
        CASE WHEN payment_category = '(Not Categorised)' THEN 'Uncategorised' END,
        CASE WHEN NOT category_known THEN 'Category not on Categories sheet'
             WHEN category_group IS NULL THEN 'Category Group blank'
             WHEN cash_flow IS NULL THEN 'Cash Flow blank' END
    ), ''), 'OK') AS "Data Status"
FROM transform.transactions_enriched
ORDER BY transaction_date, source_name, row_number;
