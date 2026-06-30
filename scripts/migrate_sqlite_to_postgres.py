from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, delete, func, insert, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import Base, engine as target_engine, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy an existing local SQLite app database into the configured target DB."
    )
    parser.add_argument(
        "--sqlite-path",
        default="storage/app.db",
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete target rows before copying. Use only for a fresh migration retry.",
    )
    args = parser.parse_args()

    source_path = ROOT / args.sqlite_path
    if not source_path.exists():
        raise SystemExit(f"SQLite source database was not found: {source_path}")

    if target_engine.url.drivername.startswith("sqlite"):
        raise SystemExit("Target DATABASE_URL is SQLite. Point DATABASE_URL at Postgres first.")

    init_db()
    source_engine = create_engine(f"sqlite:///{source_path}")
    with source_engine.begin() as source, target_engine.begin() as target:
        if target_has_rows(target) and not args.replace:
            raise SystemExit(
                "Target database already has rows. Re-run with --replace only if you want to "
                "delete target rows before copying."
            )
        if args.replace:
            for table in reversed(Base.metadata.sorted_tables):
                target.execute(delete(table))

        for table in Base.metadata.sorted_tables:
            rows = [dict(row) for row in source.execute(select(table)).mappings()]
            if rows:
                target.execute(insert(table), rows)
            reset_postgres_sequence(target, table.name, "id" if "id" in table.c else None)
            print(f"{table.name}: copied {len(rows)} rows")


def target_has_rows(connection) -> bool:
    for table in Base.metadata.sorted_tables:
        count = connection.scalar(select(func.count()).select_from(table))
        if count:
            return True
    return False


def reset_postgres_sequence(connection, table_name: str, id_column: str | None) -> None:
    if id_column is None or connection.engine.url.get_backend_name() != "postgresql":
        return
    quoted_table = table_name.replace('"', '""')
    quoted_column = id_column.replace('"', '""')
    connection.execute(
        text(
            f"""
            SELECT setval(
              pg_get_serial_sequence('"{quoted_table}"', '{quoted_column}'),
              COALESCE((SELECT MAX("{quoted_column}") FROM "{quoted_table}"), 1),
              (SELECT MAX("{quoted_column}") IS NOT NULL FROM "{quoted_table}")
            )
            """
        )
    )


if __name__ == "__main__":
    main()
