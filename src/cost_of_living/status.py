"""`status` command: show what has been done, what is out of date, and the next command to run.

Read-only. Works from the run log tables (extract.reference_loads, extract.export_log)
plus the database, the reference workbook, the Parquet file and Git.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import duckdb

OK, TODO, INFO = "[ OK ]", "[TODO]", "[info]"


def _query(connection: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    """Run a query; a missing table or view (older database) counts as no data."""
    try:
        return connection.execute(sql).fetchall()
    except duckdb.CatalogException:
        return []


def _git(project_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=project_root, capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _when(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def print_status(database: Path, workbook: Path, parquet: Path, project_root: Path) -> None:
    lines: list[tuple[str, str]] = []   # (marker, text)
    todo: list[str] = []                # commands to run, in order

    def add(marker: str, text: str, command: str | None = None) -> None:
        lines.append((marker, text))
        if marker == TODO and command:
            todo.append(command)

    connection = duckdb.connect(str(database), read_only=True) if database.is_file() else None
    try:
        # 1. Bank files
        files = _query(connection, "SELECT count(*), coalesce(sum(row_count), 0) FROM extract.imported_files") if connection else []
        n_files, n_rows = files[0] if files else (0, 0)
        if not connection:
            add(TODO, f"Database not found: {database}", "import")
        elif n_files == 0:
            add(TODO, "No bank files imported yet", "import")
        else:
            span = _query(connection, "SELECT min(transaction_date), max(transaction_date) FROM transform.transactions")
            first, last = span[0] if span else (None, None)
            add(OK, f"Bank files: {n_files} imported, {n_rows} transactions ({first} to {last})")

        # 2. Reference workbook
        load = _query(connection, "SELECT load_id, loaded_at, workbook_mtime, categories, manual_mappings, rules "
                                  "FROM extract.reference_loads ORDER BY load_id DESC LIMIT 1") if connection else []
        have_ref = _query(connection, "SELECT count(*) FROM transform.budget_categories") if connection else []
        have_ref = bool(have_ref and have_ref[0][0])
        load_id = None
        if not workbook.is_file():
            add(TODO, f"Reference workbook not found: {workbook}")
        elif not load:
            note = " (tables have data, but the load wasn't recorded; run it once to start tracking)" if have_ref else ""
            add(TODO, f"Reference workbook not loaded{note}", "load-mappings")
        else:
            load_id, loaded_at, loaded_mtime, cats, manual, rules = load[0]
            if workbook.stat().st_mtime - loaded_mtime > 1:
                add(TODO, f"Reference workbook changed since it was loaded ({loaded_at:%Y-%m-%d %H:%M}); "
                          f"workbook saved {_when(workbook.stat().st_mtime)}", "load-mappings")
            else:
                add(OK, f"Reference loaded {loaded_at:%Y-%m-%d %H:%M}: {cats} categories, {manual} manual mappings, {rules} rules")

        # 3. Categorisation (information only). Unmapped transactions get the default
        # category '(Not Categorised)' (see sql/30_views.sql).
        if connection and n_rows:
            unc = _query(connection, "SELECT count(*) FROM transform.transactions_enriched "
                                     "WHERE payment_category = '(Not Categorised)'")
            if unc and unc[0][0]:
                add(INFO, f"{unc[0][0]} of {n_rows} transactions are '(Not Categorised)' (add rules or manual mappings in the workbook)")
            elif unc:
                add(OK, "All transactions are categorised")

        # 4. Parquet export
        export = _query(connection, "SELECT exported_at, transaction_rows, imported_file_count, reference_load_id "
                                    "FROM extract.export_log ORDER BY export_id DESC LIMIT 1") if connection else []
        if not export:
            add(TODO if n_rows else INFO, "Power BI export has not been run", "export-actuals")
        else:
            exported_at, e_rows, e_files, e_load = export[0]
            reasons = []
            if e_files != n_files:
                reasons.append("bank files imported since")
            if e_load != load_id:
                reasons.append("reference data reloaded since")
            if not parquet.is_file():
                reasons.append(f"{parquet.name} is missing")
            if reasons:
                add(TODO, f"Power BI export is out of date ({'; '.join(reasons)})", "export-actuals")
            else:
                add(OK, f"Power BI export up to date: {e_rows} rows, {exported_at:%Y-%m-%d %H:%M}. "
                        f"Refresh the data in Power BI Desktop if it is open.")
    finally:
        if connection:
            connection.close()

    # 5. Git
    status = _git(project_root, "status", "--porcelain", "--branch")
    if status is None:
        add(INFO, "Git status unavailable (is git installed and this folder a repository?)")
    else:
        rows = status.splitlines()
        branch = rows[0] if rows else ""
        changed = [r for r in rows[1:] if r.strip()]
        if changed:
            add(TODO, f"Git: {len(changed)} uncommitted change(s); review with 'git status', then commit")
        else:
            add(OK, "Git: nothing uncommitted")
        if "[ahead" in branch:
            add(INFO, f"Git: commits not pushed yet ({branch.split('[', 1)[1].rstrip(']')})")

    print("Cost of Living status\n")
    for marker, text in lines:
        print(f"  {marker} {text}")
    commands = [c for c in todo if c in {"import", "load-mappings", "export-actuals"}]
    print()
    if commands:
        print("Next, in this order:")
        for command in dict.fromkeys(commands):
            print(f"  .\\.venv\\Scripts\\python.exe -m cost_of_living.admin_cli {command}")
    elif any(marker == TODO for marker, _ in lines):
        print("Next: deal with the [TODO] items above.")
    else:
        print("Everything is up to date. See doc/NEXT_STEPS.md for the next planned step.")
