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
from cost_of_living.database import load_reference_workbook, open_database, record_export
from cost_of_living.status import print_status

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FOLDER = PROJECT_ROOT / "data"
DEFAULT_DATABASE = DATA_FOLDER / "2. transform" / "cost_of_living.duckdb"
DEFAULT_IMPORT_FOLDER = DATA_FOLDER / "1. extract"
DEFAULT_REFERENCE_FOLDER = DATA_FOLDER / "9. reference"
DEFAULT_REPORT_FOLDER = DATA_FOLDER / "3. load"
DEFAULT_REFERENCE_WORKBOOK = DEFAULT_REFERENCE_FOLDER / "2026 Cost of Living - Reference.xlsx"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_money(value: str | None, column: str, issues: list[str]) -> Decimal | None:
    """Parse an optional Excel-style amount. A blank gives None; an unreadable value gives None
    and adds a note to `issues`, so the row is still loaded."""
    text = (value or "").strip().replace("\u2212", "-")
    if not text or text in {"-", "\u2014"}:
        return None

    text = text.replace(",", "").replace("$", "").replace("\u00a3", "").replace("\u20ac", "")
    text = re.sub(r"\s+", "", text)
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        issues.append(f"{column} unreadable: {(value or '').strip()[:30]!r}")
        return None


def read_date(value: str | None, issues: list[str]) -> date | None:
    """Parse a day/month/year or ISO date. A blank or unreadable date gives None (loaded as NULL)
    and adds a note to `issues`."""
    text = (value or "").strip()
    if not text:
        issues.append("Date blank")
        return None
    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            pass
    issues.append(f"Date unreadable: {text[:30]!r}")
    return None


def clean_optional(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


FILENAME_PATTERN = re.compile(r"^\d{8}-\d{8} (?P<bank>.+?) - (?P<description>.+)$")
ACCOUNT_WITH_NUMBER = re.compile(r"^\d[\d\- ]*\d - (?P<name>.+)$")


def account_from_filename(path: Path) -> str | None:
    """Get the account name from a file named '<yyyymmdd-yyyymmdd> <bank> - <account description>.csv'.

    The account description is '<account no> - <account name>' or just '<account name>'.
    'All' means the file holds several accounts and the name comes from the file's contents.
    Returns None when the filename doesn't give a name.
    """
    match = FILENAME_PATTERN.match(path.stem.strip())
    if not match:
        return None
    description = match.group("description").strip()
    numbered = ACCOUNT_WITH_NUMBER.match(description)
    name = (numbered.group("name") if numbered else description).strip()
    return None if not name or name.casefold() == "all" else name


def read_transactions(path: Path, fingerprint: str) -> tuple[list[tuple], list[tuple]]:
    """Normalize supported bank CSV exports.

    Every row that has any content is loaded. Blank or unreadable values become NULL and are
    described in the row's data_issue text (shown as Data Status in the export). Completely blank
    rows are ignored. Only a file that can't be understood at all raises an error.
    """
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
        elif required.issubset(headers):
            adapter = "standard"
        elif {"date", "description", "debit", "credit"}.issubset(headers):
            adapter = "st george"
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
                continue  # completely blank row: nothing to load
            issues: list[str] = []

            if adapter == "westpac":
                normalized.update({
                    "bank": "Westpac",
                    "account": normalized.get("bank account") or account_from_filename(path),
                    "description": normalized.get("narrative"),
                    "debit": normalized.get("debit amount"), "credit": normalized.get("credit amount"),
                    "category": normalized.get("categories"),
                })
            elif adapter == "st george":
                name = path.name.casefold()
                account_name = account_from_filename(path) or (
                    "Visa" if "visa" in name else "Work" if "work" in name else None)
                if account_name is None:
                    raise ValueError(
                        f"{path.name}: cannot determine the St George account name from the filename. "
                        "Name the file '<yyyymmdd-yyyymmdd> St George - <account no> - <account name>.csv'."
                    )
                normalized["bank"] = "St George"
                normalized["account"] = account_name
            elif adapter == "bendigo":
                normalized["bank"] = "Bendigo"
                normalized["account"] = account_from_filename(path) or "Savings"
                normalized["date"] = normalized.get("transaction_date")
                normalized["debit"] = normalized["credit"] = ""
                signed_amount = read_money(normalized.get("amount"), "Amount", issues)
                if signed_amount is None:
                    if not (normalized.get("amount") or "").strip():
                        issues.append("Amount blank")
                elif signed_amount == 0:
                    # Bendigo gives only a signed amount, so a zero has no sign to go by. Decide from the
                    # description: fees are a Debit, interest is a Credit, anything else defaults to Debit.
                    text = (normalized.get("description") or "").casefold()
                    if "fee" not in text and "interest" in text:
                        normalized["credit"] = "0.00"
                    else:
                        normalized["debit"] = "0.00"
                elif signed_amount < 0:
                    normalized["debit"] = str(abs(signed_amount))
                else:
                    normalized["credit"] = str(signed_amount)

            bank = clean_optional(normalized.get("bank"))
            account = clean_optional(normalized.get("account"))
            description = clean_optional(normalized.get("description"))
            for label, value in (("Bank", bank), ("Account", account), ("Description", description)):
                if not value:
                    issues.append(f"{label} blank")

            transaction_date = read_date(normalized.get("date"), issues)
            debit = read_money(normalized.get("debit"), "Debit", issues)
            if debit is not None:
                debit = abs(debit)
            credit = read_money(normalized.get("credit"), "Credit", issues)
            balance = read_money(normalized.get("balance"), "Balance", issues)
            if debit is None and credit is None and not any(
                    i.startswith(("Amount", "Debit", "Credit")) for i in issues):
                issues.append("Debit and Credit both blank")

            # Expenses are positive in the source Debit column; credits are
            # positive in Credit. Subtraction also treats negative debits as refunds.
            amount = None if debit is None and credit is None else (
                (credit or Decimal("0.00")) - (debit or Decimal("0.00")))
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
                "; ".join(issues) or None,
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

    connection = open_database(database)  # creates schemas, tables and views if needed

    added = 0
    try:
        for path in files:
            fingerprint = file_sha256(path)
            exists = connection.execute(
                "SELECT 1 FROM extract.imported_files WHERE sha256 = ?", [fingerprint]
            ).fetchone()
            if exists:
                print(f"Skipped (already imported): {path.name}")
                continue

            raw_rows, clean_rows = read_transactions(path, fingerprint)
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.executemany("INSERT INTO extract.transactions_raw VALUES (?, ?, ?, ?)", raw_rows)
                connection.executemany(
                    "INSERT INTO transform.transactions (source_sha256, source_name, row_number, bank, account, "
                    "transaction_date, description, debit, credit, amount, balance, category, subcategory, data_issue) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    clean_rows,
                )
                connection.execute(
                    "INSERT INTO extract.imported_files (sha256, source_name, row_count) VALUES (?, ?, ?)",
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


def export_actuals(database: Path, output_folder: Path) -> list[Path]:
    """Export the Power BI transaction and category fields as one Parquet table."""
    if not database.is_file():
        raise FileNotFoundError(f"Database not found: {database}")
    output_folder.mkdir(parents=True, exist_ok=True)
    connection = open_database(database)  # also refreshes the views
    try:
        transactions_path = output_folder / "transactions.parquet"
        connection.sql("SELECT * FROM present.transactions").write_parquet(
            str(transactions_path), compression="zstd", overwrite=True
        )
        record_export(connection, transactions_path)
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


def run() -> None:
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
                f"Reference workbook: {DEFAULT_REFERENCE_WORKBOOK}\n"
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
        "load-mappings", help="Replace category and mapping tables from the Excel reference workbook.",
        description="Read the Categories, Description Mapping and Mapping Rules sheets from the "
                    "reference workbook. Existing reference table contents in the selected database are replaced.",
    )
    mappings.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_WORKBOOK, help=f"Reference workbook (default: {DEFAULT_REFERENCE_WORKBOOK})")
    mappings.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to update (default: {DEFAULT_DATABASE})")
    status = subparsers.add_parser(
        "status", help="Show what has been done, what is out of date, and what to run next (read-only).",
        description="Report on imports, the reference workbook, the Power BI export and Git, without changing anything.",
    )
    status.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to read (default: {DEFAULT_DATABASE})")
    status.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_WORKBOOK, help=f"Reference workbook (default: {DEFAULT_REFERENCE_WORKBOOK})")
    status.add_argument("--output", type=Path, default=DEFAULT_REPORT_FOLDER, help=f"Folder holding the Parquet export (default: {DEFAULT_REPORT_FOLDER})")
    exports = subparsers.add_parser(
        "export-actuals", help="Export enriched transactions to Parquet for Power BI.",
        description="Export one enriched transaction table to a Parquet file.",
    )
    exports.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help=f"DuckDB file to read (default: {DEFAULT_DATABASE})")
    exports.add_argument("--output", type=Path, default=DEFAULT_REPORT_FOLDER, help=f"Folder for generated Parquet files (default: {DEFAULT_REPORT_FOLDER})")
    parser.add_argument("--debug", action="store_true", help="Show the full Python traceback on errors.")
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
                "FROM transform.transactions_enriched "
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
        connection = open_database(args.database)
        try:
            counts = load_reference_workbook(connection, args.reference)
            print(f"Loaded reference data from {args.reference.name}: "
                  f"{counts['budget_categories']} categories, "
                  f"{counts['manual_category_mappings']} manual mappings, "
                  f"{counts['mapping_rules']} rules.")
        finally:
            connection.close()
    elif args.command == "status":
        print_status(args.database, args.reference, args.output / "transactions.parquet", PROJECT_ROOT)
    elif args.command == "export-actuals":
        for path in export_actuals(args.database, args.output):
            print(f"Exported: {path}")


def main() -> None:
    """Run the CLI, printing a short error message instead of a Python traceback."""
    try:
        run()
    except (ValueError, RuntimeError, FileNotFoundError, duckdb.Error) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        if "--debug" in sys.argv:
            raise
        print("(For the full traceback, put --debug before the command name, e.g. admin_cli --debug load-mappings.)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
