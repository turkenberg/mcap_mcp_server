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

## Usage

Just talk to your LLM:

- *"List all my recordings and show me what topics are in session_003.mcap"*
- *"Load the battery data and find all moments where voltage dropped below 22V"*
- *"Correlate IMU acceleration with motor current using an ASOF JOIN"*
- *"Compare average battery voltage across my last 5 runs"*
- *"What version of mcap-mcp-server am I running? Update it"*

### Tools

| Tool | Needs loading | What it does |
|------|:---:|-------------|
| `list_recordings` | no | Find MCAP files in your project (or any path) |
| `get_recording_info` | no | Metadata, channels, attachments for a file |
| `get_schema` | no | SQL table names & column types — for query planning |
| `load_recording` | — | **Decode MCAP into DuckDB** (the LLM calls this automatically) |
| `query` | yes | Run SQL (full DuckDB — including ASOF JOIN) |
| `get_version` | no | Server version, available decoders, upgrade command |

**[Project documentation](https://turkenberg.github.io/mcap_mcp_server/index.html)** — configuration, Docker, development setup, and architecture.

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

## Performance

Metadata tools (`list_recordings`, `get_recording_info`, `get_schema`) return in **< 1 ms** regardless of file size. SQL queries execute in **1–10 ms** once data is loaded. The one-time `load_recording` cost scales with file size:

| Messages | File size | Load time | Query time |
|----------|-----------|-----------|------------|
| 1K | 23 KB | 8 ms | 1 ms |
| 10K | 220 KB | 90 ms | 1–3 ms |
| 100K | 2.2 MB | 0.7 s | 1–5 ms |
| 500K | 11 MB | 3.9 s | 2–9 ms |

*Measured on Apple M4 with JSON-encoded messages, 5 fields per message. Load times include full message decoding and DuckDB registration. Query times are median across aggregation, filter, and window function queries.*

> **Tip:** use `topics` and `start_time`/`end_time` filters on `load_recording` to load only what you need.

---

## Update

```bash
uvx mcap-mcp-server[all] --upgrade
```

Or ask your LLM — the `get_version` tool returns the running version and the upgrade command.

## Supported Encodings

JSON built-in. Protobuf, ROS 1, ROS 2, FlatBuffers via `[all]` (or install individually: `[protobuf]`, `[ros1]`, `[ros2]`, `[flatbuffers]`).

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
