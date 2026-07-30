# Database Mapper

A small CLI for generating Obsidian-friendly markdown notes from a database schema.

Original SQL scripts and template developed by me, glued together by Copilot into a single workflow.

## Features
- Discovers user-owned database objects such as tables, views, stored procedures, and functions.
- Writes one markdown note per object into folders like Tables and Stored Procedures.
- Adds YAML frontmatter with metadata such as object type, schema, columns, parameters, and dependency relationships.
- Works with SQLite for local verification and with SQL Server when the appropriate driver is available.

## Quick start

### SQLite example

```bash
python -m db_mapper.cli --dialect sqlite --url sqlite:///sample.db --output-dir ./out
```

### SQL Server example

```bash
python -m db_mapper.cli --dialect mssql --server localhost --database MyDb --username sa --password Secret123 --output-dir ./out
```

You can also pass a SQLAlchemy-style URL:

```bash
python -m db_mapper.cli --url "mssql+pyodbc://sa:Secret123@localhost/MyDb?driver=ODBC+Driver+17+for+SQL+Server" --output-dir ./out
```
