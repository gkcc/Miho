from __future__ import annotations

from typing import Any


VISUALIZER_DATA_SCHEMA_VERSION = "miho-visualizer-data-v2"


def compact_visualizer_data(value: dict[str, Any]) -> dict[str, Any]:
    """Column-encode dense top-level object arrays without losing fields."""

    payload: dict[str, Any] = {}
    tables: dict[str, Any] = {}
    for name, item in value.items():
        table = _dense_columnar_table(item)
        if table is None:
            payload[name] = item
        else:
            tables[name] = table
    return {
        "schema_version": VISUALIZER_DATA_SCHEMA_VERSION,
        "payload": payload,
        "tables": tables,
    }


def expand_visualizer_data(value: Any) -> Any:
    """Expand a strict v2 envelope; legacy objects pass through unchanged."""

    if not isinstance(value, dict) or value.get("schema_version") != VISUALIZER_DATA_SCHEMA_VERSION:
        return value
    if set(value) != {"schema_version", "payload", "tables"}:
        raise ValueError("visualizer data v2 envelope has unexpected fields")
    payload = value.get("payload")
    tables = value.get("tables")
    if not isinstance(payload, dict) or not isinstance(tables, dict):
        raise ValueError("visualizer data v2 payload or tables are invalid")
    expanded = dict(payload)
    for name, table in tables.items():
        if name in expanded or not isinstance(name, str) or not isinstance(table, dict):
            raise ValueError("visualizer data v2 table is invalid or colliding")
        if set(table) != {"columns", "rows"}:
            raise ValueError("visualizer data v2 table has unexpected fields")
        columns = table.get("columns")
        rows = table.get("rows")
        if (
            not isinstance(columns, list)
            or not columns
            or not all(isinstance(column, str) for column in columns)
            or len(set(columns)) != len(columns)
            or not isinstance(rows, list)
        ):
            raise ValueError("visualizer data v2 columns or rows are invalid")
        decoded_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError("visualizer data v2 row width does not match columns")
            decoded_rows.append(dict(zip(columns, row, strict=True)))
        expanded[name] = decoded_rows
    return expanded


def _dense_columnar_table(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or len(value) < 4 or not isinstance(value[0], dict) or not value[0]:
        return None
    columns = sorted(value[0])
    expected = set(columns)
    if not all(isinstance(row, dict) and len(row) == len(columns) and set(row) == expected for row in value):
        return None
    return {
        "columns": columns,
        "rows": [[row[column] for column in columns] for row in value],
    }
