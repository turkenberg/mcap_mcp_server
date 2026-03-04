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

    Client -->|list_recordings| Server
    Client -->|get_schema| Server
    Client -->|load_recording| Server
    Client -->|query| Server

    Server --> Index
    Server --> Reader
    Server --> Registry
    Server --> Engine

    Index --> Files
    Reader --> Files
    Registry --> Decoders
    Engine -->|"register DataFrame<br/>execute SQL"| Engine
```

## Module responsibilities

| Module | Role |
|--------|------|
| `server.py` | MCP tool registration, request orchestration |
| `config.py` | Config loading: defaults → TOML → env vars → CLI |
| `recording_index.py` | Scans directories for `.mcap` files, caches summaries, filters by date |
| `mcap_reader.py` | Reads MCAP summary and iterates messages using indexed reader |
| `decoder_registry.py` | Discovers and dispatches to the correct `MessageDecoder` by encoding |
| `decoders/base.py` | `MessageDecoder` protocol and type mappings |
| `decoders/*.py` | One decoder per encoding (JSON, Protobuf, ROS1, ROS2, FlatBuffer) |
| `query_engine.py` | DuckDB connection, table registration, SQL execution, safety enforcement |
| `flatten.py` | Nested dict flattening for multi-level message schemas |

## Load path

1. `load_recording` receives a filename and optional topic/time filters
2. `mcap_reader.get_summary()` reads the MCAP summary section (end of file, fast)
3. For each channel, `decoder_registry` resolves the decoder by `(message_encoding, schema_encoding)`
4. `mcap_reader.iter_messages()` iterates messages using MCAP chunk indexes
5. Each message is decoded to a flat Python dict via the appropriate decoder
6. Dicts are accumulated into per-topic column lists, then converted to `pd.DataFrame`
7. `query_engine` registers each DataFrame as a named DuckDB table
8. Subsequent `query` calls execute SQL against these tables

## Query safety

- DuckDB runs in read-only mode
- File system functions (`read_csv`, `read_parquet`, `COPY`, `EXPORT`) are blocked
- Queries are subject to a configurable timeout (default 30s) and row limit (default 1000)
