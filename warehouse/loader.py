"""Applies warehouse/schema.sql to a target SQLite database.

In production this same DDL (with the noted Postgres substitutions) would be
applied via a migration tool; for this project a local SQLite file stands in
for the warehouse so the whole pipeline can run without external infra.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def apply_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ddl = SCHEMA_PATH.read_text()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ddl)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="data/market_data.db")
    args = parser.parse_args()
    apply_schema(Path(args.db_path))
    print(f"schema applied to {args.db_path}")


if __name__ == "__main__":
    main()
