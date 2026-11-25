"""DuckDB setup (schemas, tables, views) and loading of the Excel reference workbook.

Pipeline layout inside the database:
    extract   - raw landing tables (bank rows, reference sheets as read)
    transform - cleaned tables and the enriched transaction view
    present   - views that reports and exports read

The SQL lives in the package's ``sql/`` folder so it can also be run in the DuckDB UI.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

SQL_FOLDER = Path(__file__).resolve().parent / "sql"

# Sheet names in the reference workbook (see Excel Prototype.md). Change here if they differ.
SHEET_CATEGORIES = "Categories"
SHEET_MANUAL_MAP = "Description Mapping"
SHEET_RULES = "Mapping Rules"


def _sql(name: str) -> str:
    return (SQL_FOLDER / name).read_text(encoding="utf-8")


def open_database(path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the database and make sure schemas, tables and views exist."""
    if read_only:
        return duckdb.connect(str(path), read_only=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    try:
        connection.execute(_sql("00_schema.sql"))
        columns = {row[0] for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'transform' AND table_name = 'transactions'").fetchall()}
        if "data_issue" not in columns:
            raise RuntimeError(
                f"{path.name} was created by an older version of this tool and has an out-of-date layout. "
                f"Delete {path} and run the update again; everything is rebuilt from your bank files "
                "and the reference workbook."
            )
        connection.execute(_sql("30_views.sql"))
    except Exception:
        connection.close()
        raise
    return connection


def _load_excel_extension(connection: duckdb.DuckDBPyConnection) -> None:
    try:
        connection.execute("INSTALL excel")  # no-op once installed; needs internet the first time
        connection.execute("LOAD excel")
    except duckdb.Error as exc:
        raise RuntimeError(
            "Could not load DuckDB's 'excel' extension. The first run needs internet access, "
            "and DuckDB must be version 1.2 or newer. Original error: " + str(exc)
        ) from exc


def load_reference_workbook(
    connection: duckdb.DuckDBPyConnection, workbook: Path, *, quiet: bool = False
) -> dict[str, int]:
    """Replace the reference tables from the Excel workbook and return the row counts.

    Bad or blank values in the sheets never stop the load: every row is loaded, and problems
    show up as flags in the exported data (see the Data Status column). Only a missing
    workbook, sheet or column header stops it. All-or-nothing: on any error the previous
    reference tables are left untouched. With quiet=True the per-sheet progress lines are skipped.
    """
    if not workbook.is_file():
        raise FileNotFoundError(f"Reference workbook not found: {workbook}")
    _load_excel_extension(connection)
    extract_sql = (
        _sql("10_extract_reference.sql")
        .replace("{workbook}", str(workbook).replace("'", "''"))
        .replace("{sheet_categories}", SHEET_CATEGORIES)
        .replace("{sheet_manual_map}", SHEET_MANUAL_MAP)
        .replace("{sheet_rules}", SHEET_RULES)
    )

    connection.execute("BEGIN TRANSACTION")
    try:
        try:
            connection.execute(extract_sql)
        except duckdb.BinderException as exc:
            detail = str(exc).split("\n\nLINE", 1)[0].strip()
            raise ValueError(
                f"Could not read the reference workbook {workbook.name}.\n"
                f"  Sheets expected: {SHEET_CATEGORIES!r}, {SHEET_MANUAL_MAP!r}, {SHEET_RULES!r}\n"
                f"  Columns expected: Categories -> Payment Category, Category Group, Cash Flow, Comment; "
                f"Description Mapping -> Account, Description, Manual Category; "
                f"Mapping Rules -> Rule Type, MatchText, Payment Category, Comment\n"
                f"  If a sheet name differs, change SHEET_* at the top of database.py; "
                f"if a column is missing, fix the header in Excel.\n"
                f"  DuckDB said: {detail}"
            ) from exc
        if not quiet:
            print(f"Reading {workbook.name}")
            for sheet, table in ((SHEET_CATEGORIES, "ref_categories"), (SHEET_MANUAL_MAP, "ref_manual_map"),
                                 (SHEET_RULES, "ref_rules")):
                count, last = connection.execute(f"SELECT count(*), max(sheet_row) FROM extract.{table}").fetchone()
                print(f"  Sheet '{sheet}': {count} row(s) read, down to Excel row {last}")
        connection.execute(_sql("20_transform_reference.sql"))
        counts = {
            table: connection.execute(f"SELECT count(*) FROM transform.{table}").fetchone()[0]
            for table in ("budget_categories", "manual_category_mappings", "mapping_rules")
        }
        connection.execute(
            "INSERT INTO extract.reference_loads (load_id, workbook_name, workbook_mtime, categories, "
            "manual_mappings, rules) SELECT coalesce(max(load_id), 0) + 1, ?, ?, ?, ?, ? "
            "FROM extract.reference_loads",
            [workbook.name, workbook.stat().st_mtime, counts["budget_categories"],
             counts["manual_category_mappings"], counts["mapping_rules"]],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return counts


def record_export(connection: duckdb.DuckDBPyConnection, parquet_path: Path) -> None:
    """Log an export so `status` can tell whether the Parquet file is out of date."""
    connection.execute(
        """
        INSERT INTO extract.export_log
        SELECT coalesce((SELECT max(export_id) FROM extract.export_log), 0) + 1,
               current_timestamp, ?,
               (SELECT count(*) FROM transform.transactions),
               (SELECT count(*) FROM extract.imported_files),
               (SELECT max(load_id) FROM extract.reference_loads)
        """,
        [parquet_path.name],
    )
