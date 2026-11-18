"""Command-line entry point for the transaction import workflow."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import threading
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb
from cost_of_living.categorization import categorize_database_transactions, load_reference_csvs

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FOLDER = PROJECT_ROOT / "data"
DEFAULT_DATABASE = DATA_FOLDER / "2. transform" / "cost_of_living.duckdb"
DEFAULT_IMPORT_FOLDER = DATA_FOLDER / "1. extract"
DEFAULT_REFERENCE_FOLDER = DATA_FOLDER / "9. reference"
DEFAULT_REPORT_FOLDER = DATA_FOLDER / "3. load"
DEFAULT_CATEGORIES = DEFAULT_REFERENCE_FOLDER / "Prototype - Budget Categories.csv"
DEFAULT_RULES = DEFAULT_REFERENCE_FOLDER / "Prototype - Mapping Rules.csv"
DEFAULT_MANUAL_MAPPINGS = DEFAULT_REFERENCE_FOLDER / "Prototype - Description Mapping (sample).csv"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_money(value: str | None, *, path: Path, row_number: int, column: str) -> Decimal | None:
    """Parse an optional Excel-style amount without silently accepting bad data."""
    text = (value or "").strip().replace("−", "-")
    if not text or text in {"-", "—"}:
        return None

    text = text.replace(",", "").replace("$", "").replace("£", "").replace("€", "")
    text = re.sub(r"\s+", "", text)
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(
            f"{path.name}, row {row_number}: invalid amount in {column!r}"
        ) from exc


def parse_date(value: str | None, *, path: Path, row_number: int) -> date:
    text = (value or "").strip()
    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            pass
    raise ValueError(
        f"{path.name}, row {row_number}: date must use day/month/year or ISO format"
    )


def clean_optional(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def read_transactions(path: Path, fingerprint: str) -> tuple[list[tuple], list[tuple]]:
    """Normalize supported Westpac and St George bank CSV exports."""
    required = {"bank", "account", "date", "description", "debit", "credit"}
    raw_rows: list[tuple] = []
    clean_rows: list[tuple] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        is_bendigo = "bendigo" in path.name.casefold()
        reader = csv.DictReader(
            stream,
            fieldnames=["transaction_date", "amount", "description"] if is_bendigo else None,
        )
        if not reader.fieldnames:
            raise ValueError(f"{path.name}: CSV has no header row")
        headers = {(header or "").strip().casefold() for header in reader.fieldnames}
        if {"bank account", "narrative", "debit amount", "credit amount"}.issubset(headers):
            adapter = "westpac"
        elif {"date", "description", "debit", "credit"}.issubset(headers):
            adapter = "st george"
        elif required.issubset(headers):
            adapter = "standard"
        elif is_bendigo:
            adapter = "bendigo"
        else:
            missing = required - headers
            raise ValueError(f"{path.name}: unsupported bank CSV layout; missing standard fields: {', '.join(sorted(missing))}")

        for row_number, original in enumerate(reader, start=2):
            normalized = {
                (key or "").strip().casefold(): (value or "").strip()
                for key, value in original.items()
                if key is not None
            }
            if not any(normalized.values()):
                continue

            if adapter == "westpac":
                normalized.update({
                    "bank": "Westpac", "account": normalized.get("bank account"),
                    "description": normalized.get("narrative"),
                    "debit": normalized.get("debit amount"), "credit": normalized.get("credit amount"),
                    "category": normalized.get("categories"),
                })
            elif adapter == "st george":
                name = path.name.casefold()
                account_name = "Visa" if "visa" in name else "Work" if "work" in name else None
                if account_name is None:
                    raise ValueError(f"{path.name}: cannot determine St George account from filename; include Visa or Work")
                normalized["bank"] = "St George"
                normalized["account"] = account_name
            elif adapter == "bendigo":
                normalized["bank"] = "Bendigo"
                normalized["account"] = "Savings"
                normalized["date"] = normalized.get("transaction_date")
                signed_amount = parse_money(
                    normalized.get("amount"), path=path, row_number=row_number, column="Amount"
                )
                if signed_amount is None:
                    raise ValueError(f"{path.name}, row {row_number}: Amount cannot be blank")
                normalized["debit"] = str(abs(signed_amount)) if signed_amount < 0 else ""
                normalized["credit"] = str(signed_amount) if signed_amount > 0 else ""

            bank = clean_optional(normalized.get("bank"))
            account = clean_optional(normalized.get("account"))
            description = clean_optional(normalized.get("description"))
            if not bank or not account or not description:
                raise ValueError(f"{path.name}, row {row_number}: Bank, Account and Description cannot be blank")

            transaction_date = parse_date(normalized.get("date"), path=path, row_number=row_number)
            debit = parse_money(normalized.get("debit"), path=path, row_number=row_number, column="Debit")
            if debit is not None:
                debit = abs(debit)
            credit = parse_money(normalized.get("credit"), path=path, row_number=row_number, column="Credit")
            balance = parse_money(normalized.get("balance"), path=path, row_number=row_number, column="Balance")
            if debit is None and credit is None:
                raise ValueError(f"{path.name}, row {row_number}: both Debit and Credit are blank")

            # Expenses are positive in the source Debit column; credits are
            # positive in Credit. Subtraction also treats negative debits as refunds.
            amount = (credit or Decimal("0.00")) - (debit or Decimal("0.00"))
            raw_rows.append((fingerprint, path.name, row_number - 1, json.dumps(original, ensure_ascii=False)))
            clean_rows.append((
                fingerprint,
                path.name,
                row_number - 1,
                bank,
                account,
                transaction_date,
                description,
                debit,
                credit,
                amount,
                balance,
                clean_optional(normalized.get("category")),
                clean_optional(normalized.get("subcategory")),
            ))
    return raw_rows, clean_rows


def is_transaction_csv(path: Path) -> bool:
    """Identify bank exports by their required header columns."""
    required = {"bank", "account", "date", "description", "debit", "credit"}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        headers = next(reader, [])
    normalized = {header.strip().casefold() for header in headers if header}
    return (
        required.issubset(normalized)
        or {"bank account", "date", "narrative", "debit amount", "credit amount"}.issubset(normalized)
        or {"date", "description", "debit", "credit"}.issubset(normalized)
        or "bendigo" in path.name.casefold()
    )


def import_csvs(source: Path, database: Path) -> int:
    """Import CSV files as raw and normalized rows, skipping identical content."""
    files = sorted(source.glob("*.csv")) if source.is_dir() else [source]
    files = [path for path in files if path.is_file() and path.suffix.lower() == ".csv"]
    if not files:
        raise FileNotFoundError(f"No CSV files found at {source}")
    if source.is_dir():
        bank_files = []
        for path in files:
            if is_transaction_csv(path):
                bank_files.append(path)
            else:
                print(f"Skipped (not a bank transaction export): {path.name}")
        files = bank_files
        if not files:
            print(f"No bank transaction CSVs found in {source}. Reference files were left untouched.")
            return 0

    database.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database))
    connection.execute("""
        CREATE TABLE IF NOT EXISTS imported_files (
            sha256 VARCHAR PRIMARY KEY,
            source_name VARCHAR NOT NULL,
            imported_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            row_count BIGINT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS transactions_raw (
            source_sha256 VARCHAR NOT NULL,
            source_name VARCHAR NOT NULL,
            row_number BIGINT NOT NULL,
            record JSON NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            source_sha256 VARCHAR NOT NULL,
            source_name VARCHAR NOT NULL,
            row_number BIGINT NOT NULL,
            bank VARCHAR NOT NULL,
            account VARCHAR NOT NULL,
            transaction_date DATE NOT NULL,
            description VARCHAR NOT NULL,
            debit DECIMAL(18, 2),
            credit DECIMAL(18, 2),
            amount DECIMAL(18, 2) NOT NULL,
            balance DECIMAL(18, 2),
            category VARCHAR,
            subcategory VARCHAR,
            PRIMARY KEY (source_sha256, row_number)
        )
    """)

    added = 0
    try:
        for path in files:
            fingerprint = file_sha256(path)
            exists = connection.execute(
                "SELECT 1 FROM imported_files WHERE sha256 = ?", [fingerprint]
            ).fetchone()
            if exists:
                print(f"Skipped (already imported): {path.name}")
                continue

            raw_rows, clean_rows = read_transactions(path, fingerprint)
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.executemany("INSERT INTO transactions_raw VALUES (?, ?, ?, ?)", raw_rows)
                connection.executemany(
                    "INSERT INTO transactions (source_sha256, source_name, row_number, bank, account, "
                    "transaction_date, description, debit, credit, amount, balance, category, subcategory) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    clean_rows,
                )
                connection.execute(
                    "INSERT INTO imported_files (sha256, source_name, row_count) VALUES (?, ?, ?)",
                    [fingerprint, path.name, len(clean_rows)],
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            print(f"Imported {len(clean_rows)} rows: {path.name}")
            added += 1
        categorize_database_transactions(connection)
    finally:
        connection.close()
    return added


def export_actuals(database: Path, output_folder: Path) -> list[Path]:
    """Export the Power BI transaction and category fields as one Parquet table."""
    if not database.is_file():
        raise FileNotFoundError(f"Database not found: {database}")
    output_folder.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database))
    try:
        categorize_database_transactions(connection)
        transactions_path = output_folder / "transactions.parquet"
        connection.sql("""
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
                category_comment AS "Comment"
            FROM transactions_enriched
            ORDER BY transaction_date, row_number
        """).write_parquet(
            str(transactions_path), compression="zstd", overwrite=True
        )
        # Remove the former dimension export so the folder contains one model file.
        (output_folder / "category_group.parquet").unlink(missing_ok=True)

        # Remove only the obsolete exports produced by earlier versions.
        for obsolete_name in (
            "monthly_actuals.csv",
            "monthly_actuals.parquet",
            "yearly_actuals.csv",
            "yearly_actuals.parquet",
            "transactions_enriched.csv",
            "transactions_enriched.parquet",
        ):
            (output_folder / obsolete_name).unlink(missing_ok=True)
        return [transactions_path]
    finally:
        connection.close()


def main() -> None:
    # DuckDB's relation display uses box-drawing characters that some Windows
    # PowerShell code pages cannot encode. Replace unsupported display glyphs
    # rather than failing after a successful database read.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        description="Local household transaction database administration.",
        epilog=(f"Project: {PROJECT_ROOT}\n"
                f"Database: {DEFAULT_DATABASE}\n"
                f"Transaction import folder: {DEFAULT_IMPORT_FOLDER}\n"
                f"Categories: {DEFAULT_CATEGORIES}\n"
                f"Mapping rules: {DEFAULT_RULES}\n"
                f"Manual mappings: {DEFAULT_MANUAL_MAPPINGS}\n"
                "Run 'admin_cli.py <command> --help' for command details."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")
    importer = subparsers.add_parser(
        "import", help="Add bank CSV transactions to DuckDB (writes transaction data).",
        description="Import one CSV or all CSV files in a folder. Identical files are skipped.",
    )
    importer.add_argument("source", type=Path, nargs="?", default=DEFAULT_IMPORT_FOLDER, help=f"CSV file or folder (default: {DEFAULT_IMPORT_FOLDER})")
    importer.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to update (default: {DEFAULT_DATABASE})")
    viewer = subparsers.add_parser(
        "show", help="Display transactions (read-only; descriptions may be personal).",
        description="Read and display normalized transaction rows without changing the database.",
    )
    viewer.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to read (default: {DEFAULT_DATABASE})")
    viewer.add_argument("--limit", type=int, default=50, help="Maximum number of rows to display (default: 50)")
    browser = subparsers.add_parser(
        "browse", help="Open DuckDB's local browser (may download its extension).",
        description="Start the local DuckDB browser interface; press Ctrl+C to stop it.",
    )
    browser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to open (default: {DEFAULT_DATABASE})")
    mappings = subparsers.add_parser(
        "load-mappings", help="Replace category and mapping tables in DuckDB.",
        description="Load categories, rules, and optional manual mappings. Existing reference table contents in the selected database are replaced.",
    )
    mappings.add_argument("--categories", type=Path, default=DEFAULT_CATEGORIES, help=f"Category CSV (default: {DEFAULT_CATEGORIES})")
    mappings.add_argument("--rules", type=Path, default=DEFAULT_RULES, help=f"Ordered mapping rules CSV (default: {DEFAULT_RULES})")
    mappings.add_argument("--manual", type=Path, default=DEFAULT_MANUAL_MAPPINGS, help=f"Manual mapping CSV (default: {DEFAULT_MANUAL_MAPPINGS})")
    mappings.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to update (default: {DEFAULT_DATABASE})")
    exports = subparsers.add_parser(
        "export-actuals", help="Export enriched transactions to Parquet for Power BI.",
        description="Export one enriched transaction table to a Parquet file.",
    )
    exports.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to read (default: {DEFAULT_DATABASE})")
    exports.add_argument("--output", type=Path, default=DEFAULT_REPORT_FOLDER, help=f"Folder for generated Parquet files (default: {DEFAULT_REPORT_FOLDER})")
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "import":
        count = import_csvs(args.source, args.database)
        print(f"Finished: {count} new file(s) imported into {args.database}")
    elif args.command == "show":
        if args.limit < 1:
            parser.error("--limit must be at least 1")
        if not args.database.is_file():
            parser.error(f"Database not found: {args.database}")
        connection = duckdb.connect(str(args.database), read_only=True)
        try:
            result = connection.execute(
                "SELECT bank, account, transaction_date, description, debit, credit, amount, "
                "balance, matching_rule, payment_category, manual_category, rule_based_category, "
                "category_group, cash_flow "
                "FROM transactions_enriched "
                "ORDER BY transaction_date, row_number LIMIT ?", [args.limit]
            )
            columns = [description[0] for description in result.description]
            print(" | ".join(columns))
            for row in result.fetchall():
                print(" | ".join("" if value is None else str(value) for value in row))
            print(f"{result.rowcount if result.rowcount >= 0 else 'Displayed'} row(s)")
        finally:
            connection.close()
    elif args.command == "browse":
        if not args.database.is_file():
            parser.error(f"Database not found: {args.database}")
        connection = duckdb.connect(str(args.database.resolve()))
        try:
            connection.execute("CALL start_ui()")
            print("DuckDB UI is running at http://localhost:4213. Press Ctrl+C to stop it.")
            threading.Event().wait()
        except KeyboardInterrupt:
            print("Stopping DuckDB UI.")
        finally:
            try:
                connection.execute("CALL stop_ui_server()")
            except duckdb.Error:
                pass
            connection.close()
    elif args.command == "load-mappings":
        args.database.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(args.database))
        try:
            warnings = load_reference_csvs(connection, args.categories, args.rules, args.manual)
            count = categorize_database_transactions(connection)
            print("Loaded category and mapping tables into DuckDB.")
            print(f"Categorized or refreshed {count} transaction(s).")
            for warning in warnings:
                print(warning)
        finally:
            connection.close()
    elif args.command == "export-actuals":
        for path in export_actuals(args.database, args.output):
            print(f"Exported: {path}")


if __name__ == "__main__":
    main()
