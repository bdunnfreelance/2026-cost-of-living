"""Command-line entry point for the transaction import workflow."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import duckdb


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_csvs(source: Path, database: Path) -> int:
    """Import CSV files as raw rows, skipping files already imported by content."""
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

            # DuckDB infers the CSV columns; storing each row as JSON keeps this
            # first stage tolerant of different bank export formats.
            safe_path = path.resolve().as_posix().replace("'", "''")
            rows = connection.execute(
                f"SELECT to_json(t) FROM read_csv_auto('{safe_path}', header=true) AS t"
            ).fetchall()
            connection.executemany(
                "INSERT INTO transactions_raw VALUES (?, ?, ?, ?)",
                [(fingerprint, path.name, index, row[0]) for index, row in enumerate(rows, 1)],
            )
            connection.execute(
                "INSERT INTO imported_files (sha256, source_name, row_count) VALUES (?, ?, ?)",
                [fingerprint, path.name, len(rows)],
            )
            print(f"Imported {len(rows)} rows: {path.name}")
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
    args = parser.parse_args()

    if args.command == "import":
        count = import_csvs(args.source, args.database)
        print(f"Finished: {count} new file(s) imported into {args.database}")


if __name__ == "__main__":
    main()
