# mcap-mcp-server

[![CI](https://github.com/turkenberg/mcap_mcp_server/actions/workflows/ci.yml/badge.svg)](https://github.com/turkenberg/mcap_mcp_server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/turkenberg/mcap_mcp_server/graph/badge.svg)](https://codecov.io/gh/turkenberg/mcap_mcp_server)
[![PyPI](https://img.shields.io/pypi/v/mcap-mcp-server)](https://pypi.org/project/mcap-mcp-server/)
[![Python](https://img.shields.io/pypi/pyversions/mcap-mcp-server)](https://pypi.org/project/mcap-mcp-server/)
[![License](https://img.shields.io/github/license/turkenberg/mcap_mcp_server)](https://github.com/turkenberg/mcap_mcp_server/blob/master/LICENSE)

A generic SQL query interface for [MCAP](https://mcap.dev) robotics recording data via the [Model Context Protocol](https://modelcontextprotocol.io).

> **Status**: Alpha — Core implementation with all encoding decoders (JSON, Protobuf, ROS 1, ROS 2, FlatBuffers).

## What It Does

Point this MCP server at a directory of MCAP files and query them with SQL — no database server, no ETL pipeline, no custom scripts.

```
MCAP files → mcap-mcp-server → DuckDB (in-memory) → SQL results
```

Works with **Cursor**, **Claude Desktop**, or any MCP-compatible client.

## Quick Start

```bash
# Install
pip install mcap-mcp-server

# Or zero-install via uvx
uvx mcap-mcp-server
```

## MCP Client Configuration

No configuration required — the server scans the project directory by default.
All tools also accept absolute paths, so the LLM can reach any MCAP file on your system.

### Cursor (`.cursor/mcp.json`)

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

### Claude Desktop (`claude_desktop_config.json`)

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

> **Tip:** Set `MCAP_DATA_DIR` only if your recordings live outside the project directory (e.g. a shared NAS or `/data/recordings`).

## Available Tools

| Tool | Description |
|------|-------------|
| `list_recordings` | Discover MCAP files in the project (or any directory via `path`) |
| `get_recording_info` | Full metadata, channels, and attachments for a specific file |
| `get_schema` | Inspect SQL table names, column names and types for query planning |
| `load_recording` | Decode MCAP data and load into DuckDB for SQL querying |
| `query` | Execute SQL against loaded data (full DuckDB SQL including ASOF JOIN) |
| `get_statistics` | Summary stats (min, max, mean, std) for numeric fields of a topic |

## Typical Workflow

1. **Discover** available recordings:
   ```
   → list_recordings
   ```

2. **Inspect** the schema to plan queries:
   ```
   → get_schema file="session_001.mcap"
   ```

3. **Load** data into DuckDB:
   ```
   → load_recording file="session_001.mcap"
   ```

4. **Query** with SQL:
   ```sql
   SELECT timestamp_us, voltage, current
   FROM battery
   WHERE voltage < 22.0
   ORDER BY timestamp_us
   ```

## Example Queries

```sql
-- Time-windowed statistics (1-second windows)
SELECT
  (timestamp_us / 1000000) as second,
  AVG(voltage) as avg_voltage,
  MIN(voltage) as min_voltage
FROM battery
GROUP BY second
ORDER BY second

-- Correlate battery with acceleration using ASOF JOIN
SELECT
  b.timestamp_us,
  b.voltage,
  i.linear_acceleration_x
FROM battery b
ASOF JOIN imu i ON b.timestamp_us >= i.timestamp_us

-- Compare across multiple loaded recordings
SELECT 'run1' as recording, AVG(voltage) as avg_v FROM r1_battery
UNION ALL
SELECT 'run2' as recording, AVG(voltage) as avg_v FROM r2_battery

-- Search metadata
SELECT * FROM _metadata WHERE key LIKE '%serial%'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCAP_DATA_DIR` | `.` | Root directory to scan for MCAP files |
| `MCAP_RECURSIVE` | `true` | Scan subdirectories recursively |
| `MCAP_MAX_MEMORY_MB` | `2048` | Max memory for loaded data (LRU eviction) |
| `MCAP_QUERY_TIMEOUT_S` | `30` | Max SQL query execution time |
| `MCAP_DEFAULT_ROW_LIMIT` | `1000` | Default result row limit |
| `MCAP_MAX_ROW_LIMIT` | `10000` | Maximum allowed row limit |
| `MCAP_LOG_LEVEL` | `INFO` | Server log level |
| `MCAP_TRANSPORT` | `stdio` | Transport: `stdio` or `sse` |
| `MCAP_SSE_PORT` | `8080` | Port for SSE transport |
| `MCAP_FLATTEN_DEPTH` | `3` | Max nesting depth for message flattening |

### Config File (optional)

Create `mcap-mcp-server.toml`:

```toml
[server]
data_dir = "/data/recordings"
recursive = true
transport = "stdio"

[limits]
max_memory_mb = 4096
query_timeout_s = 60
default_row_limit = 1000
max_row_limit = 50000

[decoder]
flatten_depth = 3

[logging]
level = "INFO"
```

Environment variables override config file values.

## Supported Encodings

| Encoding | Install |
|----------|---------|
| JSON | `pip install mcap-mcp-server` (built-in) |
| Protobuf | `pip install mcap-mcp-server[protobuf]` |
| ROS 1 | `pip install mcap-mcp-server[ros1]` |
| ROS 2 (CDR) | `pip install mcap-mcp-server[ros2]` |
| FlatBuffers | `pip install mcap-mcp-server[flatbuffers]` |
| All encodings | `pip install mcap-mcp-server[all]` |

## Docker

```bash
docker run -d \
  -v /data/recordings:/data:ro \
  -e MCAP_DATA_DIR=/data \
  -e MCAP_TRANSPORT=sse \
  -p 8080:8080 \
  ghcr.io/turkenberg/mcap-mcp-server:latest
```

## Development

```bash
git clone https://github.com/turkenberg/mcap_mcp_server.git
cd mcap_mcp_server
git submodule update --init
pip install -e ".[dev]"
pytest
```

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
