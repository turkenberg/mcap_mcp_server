# Architecture

## Data flow

```{mermaid}
graph TD
    Client["MCP Client"]
    Server["server.py<br/>FastMCP tools"]
    Index["recording_index.py<br/>Directory scanner"]
    Reader["mcap_reader.py<br/>Summary & iteration"]
    Registry["decoder_registry.py<br/>Encoding dispatch"]
    Decoders["decoders/<br/>JSON · Protobuf · ROS1 · ROS2 · FlatBuffer"]
    Engine["query_engine.py<br/>DuckDB wrapper"]
    Files["MCAP files on disk"]

    Client -->|"list_recordings<br/>get_recording_info<br/>get_schema<br/>get_version"| Server
    Client -->|load_recording| Server
    Client -->|query| Server

    Server --> Index
    Server --> Reader
    Server --> Registry
    Server --> Engine

    Index --> Files
    Reader --> Files
    Registry --> Decoders
    Engine -->|"register DataFrame<br/>execute SQL<br/>LRU eviction"| Engine
```

## Module responsibilities

| Module | Role |
|--------|------|
| `server.py` | MCP tool registration (6 tools), request orchestration |
| `config.py` | Config loading: defaults → TOML → env vars → CLI. Validates `max_memory_mb >= 64` |
| `recording_index.py` | Scans directories for `.mcap` files, caches summaries, filters by date |
| `mcap_reader.py` | Reads MCAP summary and iterates messages using indexed reader |
| `decoder_registry.py` | Discovers and dispatches to the correct `MessageDecoder` by encoding |
| `decoders/base.py` | `MessageDecoder` protocol and type mappings |
| `decoders/*.py` | One decoder per encoding (JSON, Protobuf, ROS1, ROS2, FlatBuffer) |
| `query_engine.py` | DuckDB connection, table registration, SQL execution, LRU eviction, safety enforcement |
| `flatten.py` | Nested dict flattening for multi-level message schemas |

## Load path

1. `load_recording` receives a filename and optional topic/time filters
2. `mcap_reader.get_summary()` reads the MCAP summary section (end of file, fast)
3. For each channel, `decoder_registry` resolves the decoder by `(message_encoding, schema_encoding)`
4. `mcap_reader.iter_messages()` iterates messages using MCAP chunk indexes
5. Each message is decoded to a flat Python dict via the appropriate decoder
6. Dicts are accumulated into per-topic column lists, then converted to `pd.DataFrame`
7. `query_engine` registers each DataFrame as a named DuckDB table
8. If memory exceeds the configured budget, LRU eviction removes the oldest tables and reports them back to the caller
9. Subsequent `query` calls execute SQL against these tables

## Memory management

The query engine tracks approximate memory usage of registered tables. When `max_memory_mb` is exceeded, the least-recently-used tables are evicted. The `load_recording` response includes `memory_used_mb`, `memory_budget_mb`, and any `evicted_tables` so the LLM can adapt its strategy.

`max_memory_mb` must be at least 64 MB — lower values are rejected at config time.

## Query safety

- DuckDB runs in read-only mode
- File system functions (`read_csv`, `read_parquet`, `COPY`, `EXPORT`) are blocked
- Queries are subject to a configurable timeout (default 30s) and row limit (default 1000)
- When a query references an unloaded table, the error includes `loaded_tables` and a `hint` to guide the LLM toward loading the correct recording
