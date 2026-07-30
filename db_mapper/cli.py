from __future__ import annotations

import argparse
import os
from typing import Sequence

from .generator import connect_to_database, generate_obsidian_notes


class CLIConfig:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Obsidian-friendly database notes from a database schema")
    parser.add_argument("--dialect", choices=["sqlite", "mssql", "sqlserver"], help="Database dialect")
    parser.add_argument("--url", "--connection-string", dest="url", help="Connection URL or connection string; for SQLite this can be a file path")
    parser.add_argument("--server", help="SQL Server server name")
    parser.add_argument("--database", help="Database name")
    parser.add_argument("--username", help="Database username")
    parser.add_argument("--password", help="Database password")
    parser.add_argument("--driver", default="ODBC Driver 17 for SQL Server", help="SQL Server ODBC driver")
    parser.add_argument("--output-dir", default="./obsidian-database-map", help="Directory for generated notes")
    parser.add_argument("--include-types", nargs="+", help="Optional list of object types to include")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = CLIConfig(
        dialect=args.dialect,
        url=args.url,
        server=args.server,
        database=args.database,
        username=args.username,
        password=args.password,
        driver=args.driver,
    )
    if not args.url and not args.dialect:
        if os.environ.get("DBMAPPER_CONNECTION_STRING"):
            config.url = os.environ["DBMAPPER_CONNECTION_STRING"]
        elif os.environ.get("DBMAPPER_URL"):
            config.url = os.environ["DBMAPPER_URL"]
        elif os.environ.get("DBMAPPER_DIALECT"):
            config.dialect = os.environ["DBMAPPER_DIALECT"]
    connection = connect_to_database(config)
    try:
        notes = generate_obsidian_notes(connection, args.output_dir, include_types=args.include_types)
    finally:
        connection.close()
    print(f"Wrote {len(notes)} note(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
