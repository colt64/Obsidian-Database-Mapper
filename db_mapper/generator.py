from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Iterable


class DatabaseConnection:
    def __init__(self, connection: Any, dialect: str) -> None:
        self.connection = connection
        self.dialect = dialect

    def execute(self, query: str, params: Iterable[Any] | None = None) -> Any:
        if self.dialect == "sqlite":
            return self.connection.execute(query, params or ())
        return self.connection.cursor().execute(query, params or ())

    def fetchall(self, query: str, params: Iterable[Any] | None = None) -> list[tuple[Any, ...]]:
        cursor = self.execute(query, params)
        if self.dialect == "sqlite":
            return cursor.fetchall()
        return cursor.fetchall()

    def commit(self) -> None:
        if self.dialect == "sqlite":
            self.connection.commit()
        else:
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def connect_to_database(config: Any) -> DatabaseConnection:
    if getattr(config, "url", None):
        url = config.url
        if url.startswith("sqlite"):
            db_path = url.replace("sqlite://", "", 1)
            if db_path.startswith("/"):
                path = db_path
            else:
                path = db_path
            return DatabaseConnection(sqlite3.connect(path), "sqlite")
        try:
            from sqlalchemy import create_engine
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("SQLAlchemy is required for non-SQLite URLs") from exc
        engine = create_engine(url)
        return DatabaseConnection(engine.connect(), "sqlalchemy")

    if getattr(config, "dialect", None) in {"sqlite", "sqlite3"}:
        path = getattr(config, "database", None) or getattr(config, "url", None)
        if not path:
            raise ValueError("SQLite requires a database path")
        return DatabaseConnection(sqlite3.connect(path), "sqlite")

    if getattr(config, "dialect", None) in {"mssql", "sqlserver"}:
        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("pyodbc is required for SQL Server connections") from exc
        server = getattr(config, "server", None)
        database = getattr(config, "database", None)
        username = getattr(config, "username", None)
        password = getattr(config, "password", None)
        driver = getattr(config, "driver", "ODBC Driver 17 for SQL Server")
        if not server or not database:
            raise ValueError("SQL Server requires both server and database")
        if username and password:
            conn_str = (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={username};PWD={password};"
            )
        else:
            conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
        return DatabaseConnection(pyodbc.connect(conn_str), "mssql")

    raise ValueError("Unsupported connection configuration")


def discover_objects(connection: DatabaseConnection) -> list[dict[str, Any]]:
    if connection.dialect == "sqlite":
        rows = connection.fetchall(
            """
            SELECT name, type, tbl_name, sql
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        )
        return [
            {
                "name": name,
                "object_type": "table" if object_type == "table" else "view",
                "schema": "main",
                "sql": sql or "",
            }
            for name, object_type, _tbl_name, sql in rows
        ]

    rows = connection.fetchall(
        """
        SELECT s.name AS schema_name,
               o.name AS object_name,
               o.type_desc AS object_type
        FROM sys.objects o
        JOIN sys.schemas s ON o.schema_id = s.schema_id
        WHERE o.is_ms_shipped = 0
          AND o.type IN ('U','V','P','FN','IF','TF')
          AND s.name NOT IN ('sys', 'INFORMATION_SCHEMA')
        ORDER BY s.name, o.name
        """
    )
    result: list[dict[str, Any]] = []
    for schema_name, object_name, object_type in rows:
        normalized_type = object_type.split(" ")[0] if " " in object_type else object_type
        normalized_type = normalized_type.upper()
        normalized = {
            "U": "table",
            "V": "view",
            "P": "stored-procedure",
            "FN": "function",
            "IF": "function",
            "TF": "function",
            "SQL_STORED_PROCEDURE": "stored-procedure",
            "SQL_TABLE": "table",
            "SQL_VIEW": "view",
            "SQL_INLINE_TABLE_VALUED_FUNCTION": "function",
            "SQL_SCALAR_FUNCTION": "function",
            "SQL_TABLE_VALUED_FUNCTION": "function",
            "SQL_PROCEDURE": "stored-procedure",
            "USER_TABLE": "table",
            "VIEW": "view",
            "TABLE": "table",
            "PROCEDURE": "stored-procedure",
            "FUNCTION": "function",
            "SQL_USER_TABLE": "table",
            "SQL_VIEW": "view",
            "SQL_FUNCTION": "function",
            "SQL_STORED_PROCEDURE": "stored-procedure",
            "STORED_PROCEDURE": "stored-procedure",
            "INLINE_TABLE_VALUED_FUNCTION": "function",
            "SCALAR_FUNCTION": "function",
            "TABLE_VALUED_FUNCTION": "function",
        }.get(normalized_type, "object")
        result.append({"name": object_name, "object_type": normalized, "schema": schema_name})
    return result


def get_columns(connection: DatabaseConnection, schema: str, name: str) -> list[dict[str, Any]]:
    if connection.dialect == "sqlite":
        pragma_rows = connection.fetchall(f'PRAGMA table_info("{name}")')
        return [
            {
                "name": row[1],
                "type": row[2],
                "nullable": not bool(row[3]),
                "primary_key": bool(row[5]),
                "default": row[4],
            }
            for row in pragma_rows
        ]

    rows = connection.fetchall(
        """
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """,
        (schema, name),
    )
    return [
        {
            "name": column_name,
            "type": data_type,
            "nullable": is_nullable.lower() == "yes",
            "default": column_default,
        }
        for column_name, data_type, is_nullable, column_default in rows
    ]


def get_parameters(connection: DatabaseConnection, schema: str, name: str) -> list[dict[str, Any]]:
    if connection.dialect == "sqlite":
        return []
    rows = connection.fetchall(
        """
        SELECT p.PARAMETER_NAME, p.DATA_TYPE, p.PARAMETER_MODE
        FROM INFORMATION_SCHEMA.PARAMETERS p
        JOIN INFORMATION_SCHEMA.ROUTINES r
          ON p.SPECIFIC_SCHEMA = r.SPECIFIC_SCHEMA AND p.SPECIFIC_NAME = r.SPECIFIC_NAME
        WHERE r.ROUTINE_SCHEMA = ? AND r.ROUTINE_NAME = ?
        ORDER BY p.ORDINAL_POSITION
        """,
        (schema, name),
    )
    return [
        {
            "name": parameter_name,
            "type": data_type,
            "mode": parameter_mode,
        }
        for parameter_name, data_type, parameter_mode in rows
    ]


def get_relationships(connection: DatabaseConnection, schema: str, name: str, object_type: str) -> dict[str, Any]:
    if connection.dialect == "sqlite":
        return {"references": [], "referenced-by": [], "edges": []}

    def normalize_type(raw_type: str | None) -> str:
        if not raw_type:
            return "object"
        normalized = raw_type.split(" ")[0].upper()
        mapping = {
            "U": "table",
            "V": "view",
            "P": "stored-procedure",
            "FN": "function",
            "IF": "function",
            "TF": "function",
            "SQL_STORED_PROCEDURE": "stored-procedure",
            "SQL_TABLE": "table",
            "SQL_VIEW": "view",
            "SQL_INLINE_TABLE_VALUED_FUNCTION": "function",
            "SQL_SCALAR_FUNCTION": "function",
            "SQL_TABLE_VALUED_FUNCTION": "function",
            "SQL_PROCEDURE": "stored-procedure",
            "USER_TABLE": "table",
            "VIEW": "view",
            "TABLE": "table",
            "PROCEDURE": "stored-procedure",
            "FUNCTION": "function",
        }
        return mapping.get(normalized, "object")

    rows = connection.fetchall(
        """
        SELECT
            s.name AS referencing_schema,
            o.name AS referencing_name,
            o.type_desc AS referencing_type,
            d.referenced_schema_name AS referenced_schema,
            d.referenced_entity_name AS referenced_name,
            COALESCE((SELECT o2.type_desc FROM sys.objects o2 WHERE o2.object_id = d.referenced_id), d.referenced_class_desc) AS referenced_type_desc
        FROM sys.sql_expression_dependencies d
        JOIN sys.objects o ON d.referencing_id = o.object_id
        JOIN sys.schemas s ON o.schema_id = s.schema_id
        WHERE o.is_ms_shipped = 0
          AND s.name = ?
          AND o.name = ?
        ORDER BY o.name
        """,
        (schema, name),
    )
    references = []
    edges = []
    for row in rows:
        if len(row) >= 6:
            referencing_schema, referencing_name, referencing_type, referenced_schema, referenced_name, referenced_type_desc = row
        else:
            referencing_schema, referencing_name, referencing_type, referenced_schema, referenced_name = row
            referenced_type_desc = None
        link_target = f"{referenced_schema}-{referenced_name}" if referenced_schema and referenced_name else (referenced_name or "unknown")
        mermaid_target = f"{referenced_schema}.{referenced_name}" if referenced_schema and referenced_name else (referenced_name or "unknown")
        references.append(f"[[{slugify(link_target)}]]")
        edges.append(
            {
                "source": f"{schema}.{name}",
                "target": mermaid_target,
                "source_type": object_type,
                "target_type": normalize_type(referenced_type_desc),
            }
        )

    reverse_rows = connection.fetchall(
        """
        SELECT
            s.name AS referencing_schema,
            o.name AS referencing_name,
            o.type_desc AS referencing_type,
            d.referenced_schema_name AS referenced_schema,
            d.referenced_entity_name AS referenced_name
        FROM sys.sql_expression_dependencies d
        JOIN sys.objects o ON d.referencing_id = o.object_id
        JOIN sys.schemas s ON o.schema_id = s.schema_id
        WHERE o.is_ms_shipped = 0
          AND d.referenced_schema_name = ?
          AND d.referenced_entity_name = ?
        ORDER BY o.name
        """,
        (schema, name),
    )
    referenced_by = []
    for referencing_schema, referencing_name, referencing_type, referenced_schema, referenced_name in reverse_rows:
        referenced_by.append(f"[[{slugify(f'{referencing_schema}-{referencing_name}')}]]")

    return {"references": references, "referenced-by": referenced_by, "edges": edges}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return slug or "object"


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\n", "\\n")
        if any(char in escaped for char in [":", "#", "[", "]", "{", "}", "*", "&", "!", "|", ">", "'", '"']):
            return '"' + escaped.replace('"', '\\"') + '"'
        return escaped
    return str(value)


def _yaml_lines(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}{{}}"]
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                if not item:
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}:")
                    lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}- {item.get('name', '')}:" if 'name' in item else f"{prefix}-")
                if len(item) == 1 and 'name' in item:
                    pass
                else:
                    for child_key, child_value in item.items():
                        if child_key == 'name':
                            continue
                        if isinstance(child_value, (dict, list)):
                            lines.append(f"{' ' * (indent + 4)}{child_key}:")
                            lines.extend(_yaml_lines(child_value, indent + 6))
                        else:
                            lines.append(f"{' ' * (indent + 4)}{child_key}: {_yaml_scalar(child_value)}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_yaml_lines(item, indent + 4))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


def build_frontmatter(metadata: dict[str, Any]) -> str:
    frontmatter_lines = ["---", * _yaml_lines(metadata), "---"]
    return "\n".join(frontmatter_lines) + "\n"


def render_parameters_table(parameters: Iterable[dict[str, Any]]) -> str:
    rows = ["| Name | Type | Mode |", "| --- | --- | --- |"]
    for parameter in parameters:
        rows.append(f"| {parameter.get('name', '')} | {parameter.get('type', '')} | {parameter.get('mode', '')} |")
    return "\n".join(rows)


def render_columns_table(columns: Iterable[dict[str, Any]]) -> str:
    rows = ["| Name | Type | Nullable | Default |", "| --- | --- | --- | --- |"]
    for column in columns:
        rows.append(
            f"| {column.get('name', '')} | {column.get('type', '')} | {'yes' if column.get('nullable', False) else 'no'} | {column.get('default', '')} |"
        )
    return "\n".join(rows)


def write_note(output_dir: str, object_type: str, schema: str, name: str, metadata: dict[str, Any], local_diagram: str | None = None) -> str:
    folder_name = {
        "table": "Tables",
        "view": "Views",
        "stored-procedure": "Stored Procedures",
        "function": "Functions",
    }.get(object_type, object_type.replace("-", " ").title())

    folder_path = os.path.join(output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    filename = f"{slugify(schema)}-{slugify(name)}.md"
    path = os.path.join(folder_path, filename)

    frontmatter_metadata = dict(metadata)
    body_sections: list[str] = [f"# {name}", ""]

    if object_type in {"stored-procedure", "function"}:
        parameters = frontmatter_metadata.pop("parameters", [])
        if parameters:
            body_sections.extend(["## Parameters", "", render_parameters_table(parameters), ""])
    elif object_type in {"table", "view"}:
        columns = frontmatter_metadata.pop("columns", [])
        if columns:
            body_sections.extend(["## Columns", "", render_columns_table(columns), ""])

    if local_diagram:
        body_sections.extend(["## Local Diagram", "", "```mermaid", local_diagram, "```", ""])

    body = "\n".join(body_sections)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_frontmatter(frontmatter_metadata))
        handle.write(body)
    return path


def create_navigation_files(output_dir: str, objects: Iterable[dict[str, Any]]) -> None:
    object_list = list(objects)
    folders = {
        "table": "Tables",
        "view": "Views",
        "stored-procedure": "Stored Procedures",
        "function": "Functions",
    }

    readme_path = os.path.join(output_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as handle:
        handle.write("# Database Map\n\n")
        handle.write("## Overview\n\n")
        handle.write("Add a brief overview for this database here.\n\n")
        handle.write("## Content Map\n\n")
        for folder_key, folder_name in folders.items():
            folder_path = os.path.join(output_dir, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            entries = [
                f"- [{entry['name']}]({folder_name}/{slugify(entry['schema'] + '-' + entry['name'])}.md)"
                for entry in object_list
                if entry["object_type"] == folder_key
            ]
            if entries:
                handle.write(f"### {folder_name}\n\n")
                handle.write("\n".join(entries) + "\n\n")

    for folder_key, folder_name in folders.items():
        folder_path = os.path.join(output_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        folder_note_path = os.path.join(folder_path, f"{folder_name}.md")
        with open(folder_note_path, "w", encoding="utf-8") as handle:
            handle.write(f"# {folder_name}\n\n")
            handle.write("This folder note is temporary and will be expanded later.\n\n")
            handle.write("## Entries\n\n")
            entries = [
                f"- [{entry['name']}]({slugify(entry['schema'] + '-' + entry['name'])}.md)"
                for entry in object_list
                if entry["object_type"] == folder_key
            ]
            if entries:
                handle.write("\n".join(entries) + "\n")
            else:
                handle.write("No entries found.\n")


def build_local_mermaid_diagram(root_name: str, root_type: str, relationships: Iterable[dict[str, Any]]) -> str:
    nodes: list[str] = [root_name]
    edges: list[tuple[str, str]] = []
    node_types: dict[str, str] = {root_name: root_type}
    for relationship in relationships:
        source = relationship.get("source")
        target = relationship.get("target")
        if not source or not target:
            continue
        if source == root_name or target == root_name:
            edges.append((source, target))
            if source not in nodes:
                nodes.append(source)
            if target not in nodes:
                nodes.append(target)
        if source and source in nodes:
            node_types[source] = relationship.get("source_type") or node_types.get(source, "object")
        if target and target in nodes:
            node_types[target] = relationship.get("target_type") or node_types.get(target, "object")

    lines = ["flowchart LR"]
    for node in nodes:
        node_type = node_types.get(node, "object")
        if node == root_name:
            if node_type == "stored-procedure":
                lines.append(f"{node}[/{node}/]")
            elif node_type == "view":
                lines.append(f"{node}[\\{node}/]")
            elif node_type == "function":
                lines.append(f"{node}([{node}])")
            else:
                lines.append(f"{node}[{node}]")
        else:
            if node_type == "stored-procedure":
                lines.append(f"{node}[/{node}/]")
            elif node_type == "view":
                lines.append(f"{node}[\\{node}/]")
            elif node_type == "function":
                lines.append(f"{node}([{node}])")
            else:
                lines.append(f"{node}[{node}]")

    for source, target in edges:
        lines.append(f"{source} --> {target}")
    return "\n".join(lines)


def build_mermaid_diagram(objects: Iterable[dict[str, Any]], relationships: Iterable[dict[str, Any]]) -> str:
    lines = ["flowchart LR"]
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()
    node_classes: dict[str, str] = {}

    for entry in objects:
        node_name = f"{entry['schema']}.{entry['name']}"
        object_type = entry.get("object_type", "object")
        shape = {
            "table": f"{node_name}[{node_name}]",
            "view": f"{node_name}[\\{node_name}/]",
            "stored-procedure": f"{node_name}[/{node_name}/]",
            "function": f"{node_name}([{node_name}])",
        }.get(object_type, f"{node_name}[{node_name}]")
        lines.append(shape)
        seen_nodes.add(node_name)
        node_classes[node_name] = object_type if object_type in {"table", "view", "stored-procedure", "function"} else "internal-link"

    for relationship in relationships:
        source = relationship.get("source")
        target = relationship.get("target")
        if not source or not target:
            continue
        edge_key = f"{source}->{target}"
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        lines.append(f"{source} --> {target}")

    lines.extend([
        "",
        "classDef table fill:#f7f7f7,stroke:#1f2937,stroke-width:1px,color:#111827",
        "classDef view fill:#eef6ff,stroke:#2563eb,stroke-width:1px,color:#111827",
        "classDef stored-procedure fill:#fff7ed,stroke:#ea580c,stroke-width:1px,color:#111827",
        "classDef function fill:#fdf2f8,stroke:#db2777,stroke-width:1px,color:#111827",
        "classDef internal-link fill:#f3f4f6,stroke:#6b7280,stroke-width:1px,color:#111827",
    ])

    for node_name in sorted(seen_nodes):
        node_id = node_name.replace("-", "_")
        class_name = node_classes.get(node_name, "internal-link")
        lines.append(f"class {node_id} {class_name}")
    return "\n".join(lines)


def write_master_diagram(output_dir: str, objects: Iterable[dict[str, Any]], relationships: list[dict[str, Any]]) -> None:
    diagram_path = os.path.join(output_dir, "Master Diagram.md")
    diagram = build_mermaid_diagram(objects, relationships)
    with open(diagram_path, "w", encoding="utf-8") as handle:
        handle.write("# Master Diagram\n\n")
        handle.write("```mermaid\n")
        handle.write(diagram)
        handle.write("\n```\n")


def generate_obsidian_notes(connection: DatabaseConnection, output_dir: str, include_types: Iterable[str] | None = None) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    objects = discover_objects(connection)
    include_set = {value.lower() for value in (include_types or [])}

    written_files: list[str] = []
    filtered_objects: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for entry in objects:
        object_type = entry["object_type"]
        if include_set and object_type not in include_set:
            continue
        filtered_objects.append(entry)
        schema = entry["schema"]
        name = entry["name"]
        metadata: dict[str, Any] = {
            "object-type": object_type,
            "schema": schema,
            "name": name,
        }
        if object_type in {"table", "view"}:
            metadata["columns"] = get_columns(connection, schema, name)
        elif object_type in {"stored-procedure", "function"}:
            metadata["parameters"] = get_parameters(connection, schema, name)

        relationship_info = get_relationships(connection, schema, name, object_type)
        if relationship_info["references"]:
            metadata["references"] = relationship_info["references"]
        if relationship_info["referenced-by"]:
            metadata["referenced-by"] = relationship_info["referenced-by"]
        relationships.extend(relationship_info.get("edges", []))

        local_diagram = None
        if relationship_info.get("edges"):
            local_diagram = build_local_mermaid_diagram(f"{schema}.{name}", object_type, relationship_info["edges"])

        written_files.append(write_note(output_dir, object_type, schema, name, metadata, local_diagram=local_diagram))

    create_navigation_files(output_dir, filtered_objects)
    write_master_diagram(output_dir, filtered_objects, relationships)
    return written_files
