"""Apply manual description mappings and ordered text rules to transactions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class MappingRule:
    rule_type: str
    match_text: str
    category: str


@dataclass(frozen=True)
class CategoryResult:
    category: str | None
    matched_by: str
    match_text: str | None = None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [
            {(key or "").strip().casefold(): (value or "").strip()
             for key, value in row.items() if key is not None}
            for row in csv.DictReader(stream)
        ]


def load_categories(path: Path) -> set[str]:
    """Load the valid Payment Category names from the prototype CSV format."""
    categories = {row.get("payment category", "") for row in _read_csv(path)}
    categories.discard("")
    if not categories:
        raise ValueError(f"No Payment Category values found in {path}")
    return categories


def load_manual_mappings(path: Path, categories: set[str]) -> dict[tuple[str, str], str]:
    """Load account-plus-description overrides from a mapping CSV."""
    mappings: dict[tuple[str, str], str] = {}
    for row in _read_csv(path):
        account = row.get("account", "")
        description = row.get("description", "")
        category = row.get("manual category", "")
        if not account and not description and not category:
            continue
        if not account or not description or not category:
            raise ValueError(f"Incomplete manual mapping row in {path}")
        key = (account.casefold(), description.casefold())
        if key in mappings:
            raise ValueError(f"Duplicate manual mapping for account/description in {path}")
        mappings[key] = category
    return mappings


def load_rules(path: Path, categories: set[str]) -> list[MappingRule]:
    """Load Payee and Vendor Type rules, preserving their row order."""
    groups: dict[str, list[MappingRule]] = {"payee": [], "vendor type": []}
    for row in _read_csv(path):
        raw_type = row.get("rule type", "").casefold()
        rule_type = "payee" if "payee" in raw_type or "payer" in raw_type else (
            "vendor type" if "vendor type" in raw_type else ""
        )
        match_text = row.get("matchtext", "")
        category = row.get("payment category", "")
        if not rule_type and not match_text and not category:
            continue
        if not rule_type:
            raise ValueError(f"Unsupported Rule Type {row.get('rule type')!r} in {path}")
        if not match_text or not category:
            raise ValueError(f"Incomplete mapping rule in {path}")
        groups[rule_type].append(MappingRule(rule_type, match_text, category))
    return groups["payee"] + groups["vendor type"]


def initialize_mapping_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """Create reference tables; category names on mappings intentionally aren't foreign keys."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS budget_categories (
            payment_category VARCHAR PRIMARY KEY,
            category_group VARCHAR NOT NULL,
            cash_flow VARCHAR NOT NULL,
            comment VARCHAR
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS manual_category_mappings (
            account VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            payment_category VARCHAR NOT NULL,
            PRIMARY KEY (account, description)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS mapping_rules (
            rule_id BIGINT PRIMARY KEY,
            rule_type VARCHAR NOT NULL,
            match_text VARCHAR NOT NULL,
            payment_category VARCHAR NOT NULL,
            comment VARCHAR
        )
    """)


def load_reference_csvs(
    connection: duckdb.DuckDBPyConnection,
    categories_path: Path,
    rules_path: Path,
    manual_path: Path | None = None,
) -> list[str]:
    """Replace reference tables from CSVs and return warnings for missing categories."""
    categories = _read_csv(categories_path)
    rules = load_rules(rules_path, set())
    manual = load_manual_mappings(manual_path, set()) if manual_path else {}
    initialize_mapping_tables(connection)
    category_names = {row.get("payment category", "") for row in categories} - {""}
    if not category_names:
        raise ValueError(f"No Payment Category values found in {categories_path}")
    canonical_category = {name.casefold(): name for name in category_names}
    rules = [
        MappingRule(rule.rule_type, rule.match_text, canonical_category.get(rule.category.casefold(), rule.category))
        for rule in rules
    ]
    manual = {
        key: canonical_category.get(category.casefold(), category)
        for key, category in manual.items()
    }

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DELETE FROM budget_categories")
        connection.execute("DELETE FROM manual_category_mappings")
        connection.execute("DELETE FROM mapping_rules")
        connection.executemany(
            "INSERT INTO budget_categories VALUES (?, ?, ?, ?)",
            [(r["payment category"], r.get("category group", ""), r.get("cash flow", ""), r.get("comment") or None)
             for r in categories if r.get("payment category")],
        )
        connection.executemany(
            "INSERT INTO mapping_rules VALUES (?, ?, ?, ?, ?)",
            [(i, r.rule_type, r.match_text, r.category, None) for i, r in enumerate(rules, 1)],
        )
        connection.executemany(
            "INSERT INTO manual_category_mappings VALUES (?, ?, ?)",
            [(account, description, category) for (account, description), category in manual.items()],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    unmapped = sorted({r.category for r in rules} | set(manual.values()) - category_names)
    # Parenthesize the union so categories are checked across both mapping sources.
    unmapped = sorted(({r.category for r in rules} | set(manual.values())) - category_names)
    return [f"Warning: mapping references category {name!r}, which is not in budget_categories; add it there." for name in unmapped]


def categorize(
    account: str,
    description: str,
    *,
    manual_mappings: dict[tuple[str, str], str],
    rules: list[MappingRule],
) -> CategoryResult:
    """Return the effective category: manual override, then ordered rules."""
    key = (account.strip().casefold(), description.strip().casefold())
    manual = manual_mappings.get(key)
    if manual:
        return CategoryResult(manual, "manual", description)
    folded_description = description.casefold()
    for rule in rules:
        if rule.match_text.casefold() in folded_description:
            return CategoryResult(rule.category, rule.rule_type, rule.match_text)
    return CategoryResult(None, "uncategorized")


def categorize_database_transactions(connection: duckdb.DuckDBPyConnection) -> int:
    """Create a view that calculates the four mapping/category fields on demand."""
    initialize_mapping_tables(connection)
    tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    if "transactions" not in tables:
        return 0
    columns = {row[1] for row in connection.execute("PRAGMA table_info('transactions')").fetchall()}
    for legacy_column in ("payment_category", "category_matched_by", "category_match_text"):
        if legacy_column in columns:
            connection.execute(f'ALTER TABLE transactions DROP COLUMN "{legacy_column}"')
    connection.execute("""
        CREATE OR REPLACE VIEW transactions_enriched AS
        SELECT
            t.*,
            manual.payment_category AS manual_category,
            matched.payment_category AS rule_based_category,
            COALESCE(manual.payment_category, matched.payment_category) AS payment_category,
            CASE
                WHEN manual.payment_category IS NOT NULL THEN 'Exact Match'
                WHEN matched.match_text IS NOT NULL THEN 'Rule: ' || matched.match_text
                ELSE '(Uncategorised)'
            END AS matching_rule,
            category.category_group,
            category.cash_flow,
            category.comment AS category_comment
        FROM transactions AS t
        LEFT JOIN manual_category_mappings AS manual
          ON lower(trim(t.account)) = lower(trim(manual.account))
         AND lower(trim(t.description)) = lower(trim(manual.description))
        LEFT JOIN LATERAL (
            SELECT rule.match_text, rule.payment_category
            FROM mapping_rules AS rule
            WHERE contains(lower(t.description), lower(rule.match_text))
            ORDER BY CASE
                WHEN lower(rule.rule_type) IN ('payee', 'payer', '1. payee', '1. payer') THEN 0
                ELSE 1
            END, rule.rule_id
            LIMIT 1
        ) AS matched ON TRUE
        LEFT JOIN budget_categories AS category
          ON category.payment_category = COALESCE(manual.payment_category, matched.payment_category)
    """)
    connection.execute("""
        CREATE OR REPLACE VIEW monthly_actuals AS
        SELECT
            date_trunc('month', transaction_date)::DATE AS period_start,
            category_group,
            payment_category,
            cash_flow,
            account,
            COALESCE(SUM(debit), 0)::DECIMAL(18, 2) AS debit_total,
            COALESCE(SUM(credit), 0)::DECIMAL(18, 2) AS credit_total,
            COALESCE(SUM(amount), 0)::DECIMAL(18, 2) AS net_amount,
            COUNT(*) AS transaction_count
        FROM transactions_enriched
        GROUP BY ALL
    """)
    connection.execute("""
        CREATE OR REPLACE VIEW yearly_actuals AS
        SELECT
            date_trunc('year', transaction_date)::DATE AS period_start,
            category_group,
            payment_category,
            cash_flow,
            account,
            COALESCE(SUM(debit), 0)::DECIMAL(18, 2) AS debit_total,
            COALESCE(SUM(credit), 0)::DECIMAL(18, 2) AS credit_total,
            COALESCE(SUM(amount), 0)::DECIMAL(18, 2) AS net_amount,
            COUNT(*) AS transaction_count
        FROM transactions_enriched
        GROUP BY ALL
    """)
    return connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
