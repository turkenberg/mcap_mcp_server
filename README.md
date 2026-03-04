# mcap-mcp-server

[![PyPI](https://img.shields.io/pypi/v/mcap-mcp-server)](https://pypi.org/project/mcap-mcp-server/)
[![Python](https://img.shields.io/pypi/pyversions/mcap-mcp-server)](https://pypi.org/project/mcap-mcp-server/)
[![CI](https://github.com/turkenberg/mcap_mcp_server/actions/workflows/ci.yml/badge.svg)](https://github.com/turkenberg/mcap_mcp_server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/turkenberg/mcap_mcp_server/graph/badge.svg)](https://codecov.io/gh/turkenberg/mcap_mcp_server)
[![License](https://img.shields.io/github/license/turkenberg/mcap_mcp_server)](https://github.com/turkenberg/mcap_mcp_server/blob/master/LICENSE)

**Query your robot's [MCAP](https://mcap.dev) recordings with SQL — straight from your LLM.**

Point Claude, Cursor, or any MCP client at your bag files. Ask questions in plain English. Get SQL-powered answers from DuckDB. No scripts, no pipelines, no BS.

```
MCAP files → mcap-mcp-server → DuckDB (in-memory) → SQL results → LLM
```

Supports **JSON, Protobuf, ROS 1, ROS 2, and FlatBuffers** out of the box.

**[Full documentation](https://turkenberg.github.io/mcap_mcp_server/index.html)**

---

## Install

Requires [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (the Python package runner). If you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

That's it — `uvx` handles the rest. No `pip install` needed.

> **Manual install** (optional): `pip install mcap-mcp-server[all]`

## Configure Your MCP Client

Copy-paste the config below. That's it — no API keys, no setup, no database.

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "mcap-query": {
      "command": "uvx",
      "args": ["mcap-mcp-server[all]"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcap-query": {
      "command": "uvx",
      "args": ["mcap-mcp-server[all]"]
    }
  }
}
```

### Windsurf / VS Code / Other MCP Clients

Same JSON — check your client's docs for where to put it.

> **Recordings outside the project?** Set `MCAP_DATA_DIR=/path/to/recordings` as an env var, or just give the LLM an absolute path — it handles that too.

---

## What Can It Do?

Once configured, just talk to your LLM. It has 6 tools:

| Tool | What it does |
|------|-------------|
| `list_recordings` | Find MCAP files in your project (or any path) |
| `get_recording_info` | Metadata, channels, attachments for a file |
| `get_schema` | SQL table names & column types — for query planning |
| `load_recording` | Decode MCAP data into DuckDB |
| `query` | Run SQL (full DuckDB — including ASOF JOIN) |
| `get_statistics` | Quick stats (min/max/mean/std) for numeric fields |

### Example Prompts

Just ask your LLM:

- *"List all my recordings and show me what topics are in session_003.mcap"*
- *"Load the battery data and find all moments where voltage dropped below 22V"*
- *"Correlate IMU acceleration with motor current using an ASOF JOIN"*
- *"Compare average battery voltage across my last 5 runs"*

### Example SQL (under the hood)

```sql
-- Time-windowed stats
SELECT (timestamp_us / 1000000) as second,
       AVG(voltage) as avg_v, MIN(voltage) as min_v
FROM battery GROUP BY second ORDER BY second

-- Cross-sensor correlation via ASOF JOIN
SELECT b.timestamp_us, b.voltage, i.linear_acceleration_x
FROM battery b ASOF JOIN imu i ON b.timestamp_us >= i.timestamp_us

-- Multi-recording comparison
SELECT 'run1' as run, AVG(voltage) FROM r1_battery
UNION ALL
SELECT 'run2', AVG(voltage) FROM r2_battery
```

---

## Supported Encodings

| Encoding | Install |
|----------|---------|
| JSON | Built-in |
| Protobuf | `pip install mcap-mcp-server[protobuf]` |
| ROS 1 | `pip install mcap-mcp-server[ros1]` |
| ROS 2 (CDR) | `pip install mcap-mcp-server[ros2]` |
| FlatBuffers | `pip install mcap-mcp-server[flatbuffers]` |
| All | `pip install mcap-mcp-server[all]` |

## Configuration (Optional)

Defaults work for most setups. Tune if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCAP_DATA_DIR` | `.` | Root directory to scan for MCAP files |
| `MCAP_RECURSIVE` | `true` | Scan subdirectories |
| `MCAP_MAX_MEMORY_MB` | `2048` | Max memory for loaded data (LRU eviction) |
| `MCAP_QUERY_TIMEOUT_S` | `30` | SQL query timeout |
| `MCAP_DEFAULT_ROW_LIMIT` | `1000` | Default result row limit |
| `MCAP_MAX_ROW_LIMIT` | `10000` | Max allowed row limit |
| `MCAP_TRANSPORT` | `stdio` | `stdio` or `sse` |

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
