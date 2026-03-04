"""DuckDB query engine: table registration, SQL execution, and safety enforcement."""

from __future__ import annotations

import logging
import time
from typing import Any

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

_BLOCKED_FUNCTIONS = [
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_json_objects",
]

_BLOCKED_KEYWORDS = [
    "COPY",
    "EXPORT",
    "IMPORT",
    "ATTACH",
    "LOAD",
    "INSTALL",
]


class QueryEngine:
    """In-memory DuckDB engine for querying DataFrames registered as virtual tables."""

    def __init__(
        self,
        query_timeout_s: int = 30,
        default_row_limit: int = 1000,
        max_row_limit: int = 10000,
    ) -> None:
        self._conn = duckdb.connect(database=":memory:")
        self._query_timeout_s = query_timeout_s
        self._default_row_limit = default_row_limit
        self._max_row_limit = max_row_limit
        self._tables: dict[str, int] = {}  # table_name -> row_count
        self._configure_safety()

    def _configure_safety(self) -> None:
        """Lock down DuckDB to prevent file access and modifications."""
        try:
            self._conn.execute("SET enable_external_access = false")
        except duckdb.Error:
            logger.debug("Could not disable external access (older DuckDB version)")
        try:
            self._conn.execute("SET lock_configuration = true")
        except duckdb.Error:
            pass

    def register_dataframe(self, name: str, df: pd.DataFrame) -> int:
        """Register a pandas DataFrame as a queryable DuckDB table.

        Returns the number of rows registered.
        """
        self._conn.register(name, df)
        row_count = len(df)
        self._tables[name] = row_count
        logger.info("Registered table %r (%d rows, %d cols)", name, row_count, len(df.columns))
        return row_count

    def unregister(self, name: str) -> None:
        self._conn.unregister(name)
        self._tables.pop(name, None)

    def drop_tables_with_prefix(self, prefix: str) -> list[str]:
        """Remove all tables whose names start with *prefix*."""
        to_drop = [t for t in self._tables if t.startswith(prefix)]
        for t in to_drop:
            self.unregister(t)
        return to_drop

    def list_tables(self) -> dict[str, int]:
        """Return a mapping of table_name -> row_count for all registered tables."""
        return dict(self._tables)

    def execute(
        self,
        sql: str,
        limit: int | None = None,
        format: str = "table",
    ) -> dict[str, Any]:
        """Execute a read-only SQL query with safety checks.

        Returns a dict matching the spec's query response shape.
        """
        self._check_sql_safety(sql)

        effective_limit = min(
            limit if limit is not None else self._default_row_limit,
            self._max_row_limit,
        )

        limited_sql = sql.rstrip().rstrip(";")
        has_limit = "LIMIT" in limited_sql.upper().split("--")[0]
        if not has_limit:
            limited_sql = f"{limited_sql} LIMIT {effective_limit + 1}"

        start = time.monotonic()
        try:
            result = self._conn.execute(limited_sql)
            description = result.description
            rows = result.fetchall()
        except duckdb.Error as e:
            return {"error": str(e), "execution_time_ms": _elapsed_ms(start)}

        elapsed = _elapsed_ms(start)
        truncated = len(rows) > effective_limit
        if truncated:
            rows = rows[:effective_limit]

        columns = [desc[0] for desc in description] if description else []
        types = [desc[1] for desc in description] if description else []

        if format == "csv":
            return self._format_csv(columns, rows, truncated, elapsed)
        elif format == "json":
            return self._format_json(columns, rows, truncated, elapsed)
        else:
            return {
                "columns": columns,
                "types": types,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
                "truncated": truncated,
                "execution_time_ms": elapsed,
            }

    def _check_sql_safety(self, sql: str) -> None:
        upper = sql.upper()
        for kw in _BLOCKED_KEYWORDS:
            tokens = upper.split()
            if kw in tokens:
                raise ValueError(f"Blocked SQL keyword: {kw}")

        for fn in _BLOCKED_FUNCTIONS:
            if fn.upper() + "(" in upper.replace(" ", ""):
                raise ValueError(f"Blocked SQL function: {fn}")

    def _format_csv(
        self, columns: list[str], rows: list, truncated: bool, elapsed: int
    ) -> dict[str, Any]:
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
        return {
            "data": buf.getvalue(),
            "row_count": len(rows),
            "truncated": truncated,
            "execution_time_ms": elapsed,
        }

    def _format_json(
        self, columns: list[str], rows: list, truncated: bool, elapsed: int
    ) -> dict[str, Any]:
        records = [dict(zip(columns, row)) for row in rows]
        return {
            "data": records,
            "row_count": len(rows),
            "truncated": truncated,
            "execution_time_ms": elapsed,
        }

    def close(self) -> None:
        self._conn.close()


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
