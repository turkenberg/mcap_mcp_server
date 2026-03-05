# mcap-mcp-server

[![codecov](https://codecov.io/gh/turkenberg/mcap_mcp_server/graph/badge.svg)](https://codecov.io/gh/turkenberg/mcap_mcp_server)
[![License](https://img.shields.io/github/license/turkenberg/mcap_mcp_server)](https://github.com/turkenberg/mcap_mcp_server/blob/master/LICENSE)

**Query your robot's [MCAP](https://mcap.dev) recordings with SQL — straight from your LLM.**

## Setup

Add to `.cursor/mcp.json` (or `claude_desktop_config.json` for Claude Desktop):

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

That's it. No install, no database, no API keys. Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

> **Upgrade:** `uvx mcap-mcp-server[all] --upgrade` — or just ask your LLM *"what version of mcap-mcp-server am I running?"*

---

## Usage

Just talk to your LLM:

- *"List all my recordings and show me what topics are in session_003.mcap"*
- *"Load the battery data and find all moments where voltage dropped below 22V"*
- *"Correlate IMU acceleration with motor current using an ASOF JOIN"*
- *"Compare average battery voltage across my last 5 runs"*

### Tools

| Tool | Speed | What it does |
|------|-------|-------------|
| `list_recordings` | fast | Find MCAP files in your project (or any path) |
| `get_recording_info` | fast | Metadata, channels, attachments for a file |
| `get_schema` | fast | SQL table names & column types — for query planning |
| `load_recording` | **slow** | Decode all messages into DuckDB (required before query) |
| `query` | fast | Run SQL (full DuckDB — including ASOF JOIN) |
| `get_version` | fast | Server version, available decoders, upgrade command |

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

JSON built-in. Protobuf, ROS 1, ROS 2, FlatBuffers via `[all]` (or install individually: `[protobuf]`, `[ros1]`, `[ros2]`, `[flatbuffers]`).

---

**[Full documentation](https://turkenberg.github.io/mcap_mcp_server/index.html)** — configuration, Docker, development setup, and architecture.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
