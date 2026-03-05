"""MCP server: tool and resource registration for MCAP querying."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from mcp.server.fastmcp import FastMCP

from mcap_mcp_server import __version__
from mcap_mcp_server.config import ServerConfig
from mcap_mcp_server.decoder_registry import DecoderRegistry
from mcap_mcp_server.mcap_reader import (
    get_schema_info,
    get_summary,
    topic_to_table_name,
)
from mcap_mcp_server.query_engine import QueryEngine
from mcap_mcp_server.recording_index import RecordingIndex, _ns_to_iso

logger = logging.getLogger(__name__)


def create_server(config: ServerConfig) -> FastMCP:
    """Build and return a fully configured MCP server instance."""
    mcp = FastMCP(
        name="mcap-mcp-server",
        instructions=(
            "This server provides SQL query access to MCAP robotics recording files. "
            "Use list_recordings to discover files, get_schema to inspect available "
            "tables and columns, load_recording to load data into DuckDB, and query "
            "to run SQL. All tables have a timestamp_us (BIGINT, microseconds) column "
            "for time-based JOINs across topics."
        ),
    )

    registry = DecoderRegistry(flatten_depth=config.flatten_depth)
    registry.discover()

    index = RecordingIndex(recursive=config.recursive)

    engine = QueryEngine(
        query_timeout_s=config.query_timeout_s,
        default_row_limit=config.default_row_limit,
        max_row_limit=config.max_row_limit,
        max_memory_mb=config.max_memory_mb,
    )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @mcp.tool(
        name="list_recordings",
        description=(
            "Discover available MCAP recording files. Does not require loading. "
            "Returns file names, sizes, durations, channel lists, and message counts. "
            "Use this first to see what data is available before loading. "
            "By default scans the project directory; pass an absolute 'path' to "
            "scan any directory on the filesystem."
        ),
    )
    def list_recordings(
        path: str | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> str:
        """List MCAP recordings in the data directory."""
        scan_path = Path(path) if path else config.data_dir
        after_dt = _parse_datetime(after)
        before_dt = _parse_datetime(before)
        summaries = index.scan(scan_path, after=after_dt, before=before_dt)
        return json.dumps(index.to_json(summaries), indent=2)

    @mcp.tool(
        name="get_recording_info",
        description=(
            "Get full metadata, channel details, and attachment list for a "
            "specific MCAP recording file. Does not require loading. "
            "Use this for detailed inspection before loading data."
        ),
    )
    def get_recording_info(file: str) -> str:
        """Return detailed recording metadata, channels, and attachments."""
        file_path = _resolve_file(file, config.data_dir)
        s = get_summary(file_path)

        channels: dict[str, Any] = {}
        for ch in s.channels:
            channels[ch.topic] = {
                "schema_name": ch.schema_name,
                "message_encoding": ch.message_encoding,
                "message_count": ch.message_count,
            }

        result: dict[str, Any] = {
            "file": Path(s.path).name,
            "path": s.path,
            "size_mb": round(s.size_mb, 1),
            "library": s.library,
            "start_time": _ns_to_iso(s.start_time_ns),
            "end_time": _ns_to_iso(s.end_time_ns),
            "duration_s": round(s.duration_s, 1),
            "message_count": s.message_count,
            "channels": channels,
            "metadata": s.metadata,
            "attachments": s.attachment_names,
        }
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="get_schema",
        description=(
            "Inspect the SQL schema for a recording: topic names, table names, "
            "column names and DuckDB types. Does not require loading. "
            "Use this to plan SQL queries before running them. "
            "Returns a sql_hint with JOIN guidance."
        ),
    )
    def get_schema(
        file: str,
        topic: str | None = None,
    ) -> str:
        """Get schema info for SQL query planning."""
        file_path = _resolve_file(file, config.data_dir)
        topics_info = get_schema_info(file_path, registry, topic=topic)

        result: dict[str, Any] = {
            "file": Path(file_path).name,
            "topics": {},
            "metadata_table": "_metadata",
            "sql_hint": (
                "Tables are named from topics: strip leading '/', replace '/' "
                "with '_'. All tables have a 'timestamp_us' column (BIGINT, "
                "microseconds). Use it for JOINs across topics. DuckDB supports "
                "ASOF JOIN for time-series with different sample rates."
            ),
        }
        for topic_name, schema in topics_info.items():
            result["topics"][topic_name] = {
                "table_name": schema.table_name,
                "message_count": schema.message_count,
                "schema_name": schema.schema_name,
                "message_encoding": schema.message_encoding,
                "fields": [
                    {"name": f.name, "type": f.type, "description": f.description}
                    for f in schema.fields
                ],
            }
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="load_recording",
        description=(
            "Decode an MCAP file and load its data into DuckDB for SQL querying. "
            "This decodes all messages and may take seconds to tens of seconds "
            "depending on file size. You must call this before running queries. "
            "For large files, use 'topics' to load only the topics you need and "
            "'start_time'/'end_time' to narrow the time window — this significantly "
            "reduces both load time and memory usage. "
            "Set an alias for multi-recording comparison."
        ),
    )
    def load_recording(
        file: str,
        alias: str | None = None,
        topics: list[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        downsample: int | None = None,
    ) -> str:
        """Load MCAP data into DuckDB tables."""
        file_path = _resolve_file(file, config.data_dir)
        summary = get_summary(file_path)

        start_ns = _parse_time_to_ns(start_time)
        end_ns = _parse_time_to_ns(end_time)

        decodable_channels: dict[int, dict] = {}
        skipped_topics: list[str] = []

        for ch in summary.channels:
            if topics and ch.topic not in topics:
                continue
            decoder = registry.get_decoder(ch.message_encoding, ch.schema_encoding)
            if decoder is None:
                skipped_topics.append(ch.topic)
                continue
            decodable_channels[ch.channel_id] = {
                "topic": ch.topic,
                "decoder": decoder,
                "schema_id": ch.schema_id,
                "schema_name": ch.schema_name,
                "schema_encoding": ch.schema_encoding,
                "message_encoding": ch.message_encoding,
            }

        # Accumulate decoded messages per topic
        topic_columns: dict[str, dict[str, list]] = {}
        topic_field_names: dict[str, list[str] | None] = {}

        load_start = time.monotonic()
        msg_count = 0

        with open(file_path, "rb") as f:
            from mcap.reader import make_reader

            reader = make_reader(f)
            file_summary = reader.get_summary()
            schemas_by_id = file_summary.schemas if file_summary else {}

            topic_list = [info["topic"] for info in decodable_channels.values()] or None

            for schema_rec, channel, message in reader.iter_messages(
                topics=topic_list,
                start_time=start_ns,
                end_time=end_ns,
                log_time_order=True,
            ):
                if channel.id not in decodable_channels:
                    continue

                msg_count += 1
                if downsample and msg_count % downsample != 0:
                    continue

                info = decodable_channels[channel.id]
                decoder = info["decoder"]
                topic = info["topic"]

                schema_data = b""
                if schema_rec is not None:
                    schema_data = schema_rec.data
                elif info["schema_id"] in schemas_by_id:
                    schema_data = schemas_by_id[info["schema_id"]].data

                try:
                    decoded = decoder.decode(
                        schema_data,
                        message.data,
                        schema_name=info["schema_name"],
                        schema_encoding=info["schema_encoding"],
                        schema_id=info["schema_id"],
                    )
                except Exception:
                    logger.debug("Failed to decode message on %s", topic, exc_info=True)
                    continue

                if topic not in topic_columns:
                    topic_columns[topic] = {"timestamp_us": []}
                    topic_field_names[topic] = None

                cols = topic_columns[topic]
                cols["timestamp_us"].append(message.log_time // 1000)

                if topic_field_names[topic] is None:
                    topic_field_names[topic] = list(decoded.keys())
                    for field_name in decoded:
                        cols[field_name] = []

                for field_name in topic_field_names[topic]:  # type: ignore[union-attr]
                    cols.setdefault(field_name, []).append(decoded.get(field_name))

        tables_info: dict[str, dict[str, int]] = {}
        total_rows = 0
        total_memory_bytes = 0
        load_group = alias or Path(file_path).name

        engine.drain_evicted()

        for topic, cols in topic_columns.items():
            table_name = topic_to_table_name(topic, alias)
            df = pd.DataFrame(cols)
            total_memory_bytes += int(df.memory_usage(deep=True).sum())
            row_count = engine.register_dataframe(table_name, df, group=load_group)
            tables_info[table_name] = {"rows": row_count, "columns": len(df.columns)}
            total_rows += row_count

        _register_metadata_table(engine, summary, alias, group=load_group)

        if alias:
            _register_recordings_entry(engine, summary, alias)

        load_time = time.monotonic() - load_start

        evicted = engine.drain_evicted()
        memory_budget_mb = config.max_memory_mb
        memory_used_mb = round(engine.total_memory_bytes / (1024 * 1024), 1)

        result: dict[str, Any] = {
            "status": "loaded",
            "file": Path(file_path).name,
            "alias": alias,
            "tables": tables_info,
            "skipped_topics": skipped_topics,
            "skipped_reason": "no decoder available or binary blob" if skipped_topics else None,
            "total_rows": total_rows,
            "memory_mb": round(total_memory_bytes / (1024 * 1024), 1),
            "memory_used_mb": memory_used_mb,
            "memory_budget_mb": memory_budget_mb,
            "load_time_s": round(load_time, 1),
        }
        if evicted:
            result["evicted_tables"] = sorted(set(evicted))
            result["eviction_warning"] = (
                "Memory budget exceeded. Previously loaded tables were evicted "
                "to make room. Use topic and time filters to reduce memory usage."
            )
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="query",
        description=(
            "Execute a SQL query against loaded MCAP data. Supports full DuckDB SQL "
            "including JOINs, GROUP BY, window functions, and ASOF JOIN for "
            "time-series correlation. Data must be loaded first via load_recording. "
            "If a table is missing, call load_recording with the needed topic."
        ),
    )
    def query(
        sql: str,
        limit: int | None = None,
    ) -> str:
        """Run a SQL query on loaded data."""
        try:
            result = engine.execute(sql, limit=limit)
        except ValueError as e:
            result = {"error": str(e)}

        if "error" in result and "does not exist" in str(result["error"]):
            loaded = engine.list_tables()
            result["loaded_tables"] = list(loaded.keys()) if loaded else []
            result["hint"] = (
                "Table not found. Call load_recording to load the needed topic. "
                "Use get_schema to see available topics in a file."
            )

        return json.dumps(result, default=_json_default, indent=2)

    @mcp.tool(
        name="get_version",
        description=(
            "Return the server version, supported encodings, and upgrade command. "
            "Use this to check for updates or diagnose compatibility issues."
        ),
    )
    def get_version() -> str:
        """Return version info and available decoders."""
        result = {
            "version": __version__,
            "decoders": registry.available_encodings,
            "upgrade": "uvx mcap-mcp-server[all] --upgrade",
        }
        return json.dumps(result, indent=2)

    return mcp


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _resolve_file(file: str, data_dir: Path) -> Path:
    """Resolve a filename or path to an absolute Path."""
    p = Path(file)
    if p.is_absolute() and p.is_file():
        return p
    candidate = data_dir / file
    if candidate.is_file():
        return candidate
    # Try searching recursively
    for match in data_dir.rglob(Path(file).name):
        if match.is_file():
            return match
    raise FileNotFoundError(f"MCAP file not found: {file} (searched in {data_dir})")


def _normalize_iso(value: str) -> str:
    """Replace trailing 'Z' with '+00:00' for Python 3.10 fromisoformat compat."""
    if value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(_normalize_iso(value))
    except ValueError:
        return None


def _parse_time_to_ns(value: str | None) -> int | None:
    """Parse an ISO 8601 string or integer microseconds to nanoseconds."""
    if value is None:
        return None
    try:
        us = int(value)
        return us * 1000
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(_normalize_iso(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1e9)
    except ValueError:
        return None


def _register_metadata_table(
    engine: QueryEngine, summary: Any, alias: str | None, group: str = "_default"
) -> None:
    """Create the _metadata table from MCAP metadata records."""
    rows = []
    for record_name, kv in summary.metadata.items():
        for k, v in kv.items():
            rows.append({"record_name": record_name, "key": k, "value": v})
    if rows:
        table_name = f"{alias}__metadata" if alias else "_metadata"
        df = pd.DataFrame(rows)
        engine.register_dataframe(table_name, df, group=group)


def _register_recordings_entry(
    engine: QueryEngine, summary: Any, alias: str
) -> None:
    """Add an entry to the cross-recording _recordings table."""
    row = {
        "alias": alias,
        "file_path": summary.path,
        "start_time": summary.start_time_ns,
        "end_time": summary.end_time_ns,
        "duration_s": summary.duration_s,
        "message_count": summary.message_count,
        "channel_count": len(summary.channels),
    }
    df = pd.DataFrame([row])
    try:
        existing = engine.execute("SELECT * FROM _recordings", limit=10000)
        if "error" not in existing:
            engine.unregister("_recordings")
            old_df = pd.DataFrame(existing["rows"], columns=existing["columns"])
            df = pd.concat([old_df, df], ignore_index=True)
    except Exception:
        pass
    engine.register_dataframe("_recordings", df)


def _json_default(obj: Any) -> Any:
    """JSON serialiser fallback for types DuckDB may return."""
    import decimal

    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)
