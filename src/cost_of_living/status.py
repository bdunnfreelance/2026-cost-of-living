"""`status` command: a short, scannable report of what is done, what is out of date, and what to run.

Read-only. Works from the run log tables (extract.reference_loads, extract.export_log)
plus the database, the reference workbook and the Parquet file.

Each line is: marker, label, short text.
    OK    nothing to do
    TODO  out of date; run the command shown at the bottom
    info  worth knowing, no action required by the tool
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb

OK, TODO, INFO = "OK", "TODO", "info"
MARKER_WIDTH = 6
LABEL_WIDTH = 17


def _query(connection: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    """Run a query; a missing table or view (older database) counts as no data."""
    try:
        return connection.execute(sql).fetchall()
    except duckdb.CatalogException:
        return []


def _short(moment: datetime) -> str:
    return moment.strftime("%d %b %H:%M").lstrip("0")


def print_status(database: Path, workbook: Path, parquet: Path, project_root: Path) -> None:
    lines: list[tuple[str, str, str]] = []   # (marker, label, text)
    todo: list[str] = []                     # commands to run

    def add(marker: str, label: str, text: str, command: str | None = None) -> None:
        lines.append((marker, label, text))
        if marker == TODO and command:
            todo.append(command)

    connection = duckdb.connect(str(database), read_only=True) if database.is_file() else None
    try:
        # 1. Bank files
        files = _query(connection, "SELECT count(*), coalesce(sum(row_count), 0) FROM extract.imported_files") if connection else []
        n_files, n_rows = files[0] if files else (0, 0)
        if not connection or n_files == 0:
            add(TODO, "Bank files", "none imported yet", "import")
        else:
            span = _query(connection, "SELECT min(transaction_date), max(transaction_date) FROM transform.transactions")
            first, last = span[0] if span else (None, None)
            add(OK, "Bank files", f"{n_files} files, {n_rows:,} transactions ({first} to {last})")

        # 2. Reference workbook
        load = _query(connection, "SELECT load_id, loaded_at, workbook_mtime, categories, manual_mappings, rules "
                                  "FROM extract.reference_loads ORDER BY load_id DESC LIMIT 1") if connection else []
        load_id = None
        if not workbook.is_file():
            add(TODO, "Reference data", f"workbook not found: {workbook.name}")
        elif not load:
            add(TODO, "Reference data", "not loaded", "load-mappings")
        else:
            load_id, loaded_at, loaded_mtime, cats, manual, rules = load[0]
            if workbook.stat().st_mtime - loaded_mtime > 1:
                add(TODO, "Reference data", "workbook changed since last load", "load-mappings")
            else:
                add(OK, "Reference data", f"{cats:,} categories, {manual:,} mappings, {rules:,} rules (loaded {_short(loaded_at)})")

        # 3. Categorisation (information only). Unmapped transactions get the default
        # category '(Not Categorised)' (see sql/30_views.sql).
        if connection and n_rows:
            unc = _query(connection, "SELECT count(*) FROM transform.transactions_enriched "
                                     "WHERE payment_category = '(Not Categorised)'")
            if unc and unc[0][0]:
                count = unc[0][0]
                add(INFO, "Not categorised", f"{count:,} of {n_rows:,} ({round(100 * count / n_rows)}%) - add rules or mappings in the workbook")
            elif unc:
                add(OK, "Categorisation", "all transactions categorised")

        # 4. Parquet export
        export = _query(connection, "SELECT exported_at, transaction_rows, imported_file_count, reference_load_id "
                                    "FROM extract.export_log ORDER BY export_id DESC LIMIT 1") if connection else []
        if not export:
            add(TODO if n_rows else INFO, "Power BI export", "not run yet", "export-actuals")
        else:
            exported_at, e_rows, e_files, e_load = export[0]
            reasons = []
            if e_files != n_files:
                reasons.append("new bank files")
            if e_load != load_id:
                reasons.append("reference data reloaded")
            if not parquet.is_file():
                reasons.append(f"{parquet.name} missing")
            if reasons:
                add(TODO, "Power BI export", f"out of date: {', '.join(reasons)}", "export-actuals")
            else:
                add(OK, "Power BI export", f"{e_rows:,} rows, {_short(exported_at)} - refresh Power BI Desktop")
    finally:
        if connection:
            connection.close()

    needs_attention = any(marker == TODO for marker, _, _ in lines)
    print(f"\nCost of Living - {'NEEDS ATTENTION' if needs_attention else 'UP TO DATE'}\n")
    for marker, label, text in lines:
        print(f"  {marker:<{MARKER_WIDTH}}{label:<{LABEL_WIDTH}}{text}")
    if todo:
        print(f"\nRun: .\\.venv\\Scripts\\python.exe -m cost_of_living.admin_cli update")
    elif needs_attention:
        print("\nFix the TODO items above.")
    print()
