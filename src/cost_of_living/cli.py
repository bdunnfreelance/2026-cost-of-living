"""Command-line entry point for the transaction import workflow."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import threading
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb


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
    """Return raw JSON rows and normalized columns from one bank CSV."""
    required = {"bank", "account", "date", "description", "debit", "credit"}
    raw_rows: list[tuple] = []
    clean_rows: list[tuple] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"{path.name}: CSV has no header row")
        missing = required - {header.strip().casefold() for header in reader.fieldnames if header}
        if missing:
            raise ValueError(f"{path.name}: missing required column(s): {', '.join(sorted(missing))}")

        for row_number, original in enumerate(reader, start=2):
            normalized = {
                (key or "").strip().casefold(): (value or "").strip()
                for key, value in original.items()
                if key is not None
            }
            if not any(normalized.values()):
                continue

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


def import_csvs(source: Path, database: Path) -> int:
    """Import CSV files as raw and normalized rows, skipping identical content."""
    files = sorted(source.glob("*.csv")) if source.is_dir() else [source]
    files = [path for path in files if path.is_file() and path.suffix.lower() == ".csv"]
    if not files:
        raise FileNotFoundError(f"No CSV files found at {source}")

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
                connection.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", clean_rows)
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
    finally:
        connection.close()
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Import bank CSVs into a local DuckDB file.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    importer = subparsers.add_parser("import", help="Import CSV files")
    importer.add_argument("source", type=Path, help="CSV file or folder containing CSV files")
    importer.add_argument("--database", type=Path, default=Path("data/transactions.duckdb"))
    viewer = subparsers.add_parser("show", help="Display normalized transactions in the terminal")
    viewer.add_argument("--database", type=Path, default=Path("data/transactions.duckdb"))
    viewer.add_argument("--limit", type=int, default=50, help="Maximum number of rows to display (default: 50)")
    browser = subparsers.add_parser("browse", help="Open DuckDB's local browser interface")
    browser.add_argument("--database", type=Path, default=Path("data/transactions.duckdb"))
    args = parser.parse_args()

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
            relation = connection.sql(
                "SELECT bank, account, transaction_date, description, debit, credit, amount, "
                "balance, category, subcategory FROM transactions "
                f"ORDER BY transaction_date, row_number LIMIT {args.limit}"
            )
            relation.show(max_rows=args.limit)
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


if __name__ == "__main__":
    main()
