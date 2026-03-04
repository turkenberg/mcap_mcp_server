# mcap-mcp-server

**SQL query interface for [MCAP](https://mcap.dev) robotics data via the [Model Context Protocol](https://modelcontextprotocol.io).**

Decodes MCAP recordings (any encoding), loads them into [DuckDB](https://duckdb.org) as in-memory tables, and exposes 6 MCP tools for discovery, schema inspection, loading, and SQL querying. Runs in-process — no external database, no ETL.

```{mermaid}
graph LR
    Client["MCP Client<br/>(Cursor, Claude Desktop)"]
    Server["mcap-mcp-server"]
    DuckDB["DuckDB<br/>(in-process SQL)"]
    Files["MCAP Files<br/>(any encoding)"]

    Client -->|MCP protocol| Server
    Server -->|register tables| DuckDB
    Server -->|read & decode| Files
    Client -->|SQL queries| DuckDB
```

## Quick Start

```bash
pip install mcap-mcp-server        # core (JSON built-in)
pip install mcap-mcp-server[ros2]  # + ROS 2 CDR decoder
pip install mcap-mcp-server[all]   # all encodings
```

Add to your MCP client config (Cursor: `.cursor/mcp.json`, Claude Desktop: `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mcap-query": {
      "command": "uvx",
      "args": ["mcap-mcp-server"]
    }
  }
}
```

That's it. Point your LLM at MCAP files and ask questions.

## Key Design Choices

- **Encoding-agnostic** — Pluggable decoder system: JSON, Protobuf, ROS 1, ROS 2, FlatBuffers. Add custom decoders via entry points.
- **DuckDB as query engine** — Full analytical SQL including `ASOF JOIN` for cross-sensor time correlation. Read-only, sandboxed (no file-system access from SQL).
- **Zero infrastructure** — No database server, no schema migration, no config files required. Scans the working directory by default.
- **LRU memory management** — Configurable memory cap (`MCAP_MAX_MEMORY_MB`, default 2 GB) with least-recently-used eviction across loaded recordings.
- **Topic → table mapping** — `/sensors/imu` becomes table `imu`, `/battery/status` becomes `battery_status`. Every table gets a `timestamp_us` column for JOINs. A `_metadata` table holds MCAP metadata records.

## Tools

| Tool | Purpose |
|------|---------|
| `list_recordings` | Discover MCAP files in a directory |
| `get_recording_info` | Metadata, channels, attachments |
| `get_schema` | Table names, column names & DuckDB types |
| `load_recording` | Decode + register as DuckDB tables |
| `query` | Execute SQL (full DuckDB dialect) |
| `get_statistics` | Min/max/mean/std for numeric fields |

## Supported Encodings

| Encoding | Decoder | Install extra |
|----------|---------|---------------|
| JSON | `JsonDecoder` | — |
| Protobuf | `ProtobufDecoder` | `[protobuf]` |
| ROS 1 (bag) | `Ros1Decoder` | `[ros1]` |
| ROS 2 (CDR) | `Ros2Decoder` | `[ros2]` |
| FlatBuffers | `FlatBufferDecoder` | `[flatbuffers]` |

```{toctree}
:maxdepth: 2
:caption: Architecture

architecture
```

```{toctree}
:maxdepth: 2
:caption: Interfaces

tools
decoders
```

```{toctree}
:maxdepth: 2
:caption: Configuration

configuration
```

## Links

- [PyPI package](https://pypi.org/project/mcap-mcp-server/)
- [GitHub repository](https://github.com/turkenberg/mcap_mcp_server)
- [MCAP format](https://mcap.dev)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [DuckDB](https://duckdb.org)
