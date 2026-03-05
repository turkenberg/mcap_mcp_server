# MCAP MCP Server

**Query your robot's [MCAP](https://mcap.dev) recordings with SQL — straight from your LLM.**

[![codecov](https://codecov.io/gh/turkenberg/mcap_mcp_server/graph/badge.svg)](https://codecov.io/gh/turkenberg/mcap_mcp_server)
[![License](https://img.shields.io/github/license/turkenberg/mcap_mcp_server)](https://github.com/turkenberg/mcap_mcp_server/blob/master/LICENSE)

## Setup

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

No install, no database, no API keys. Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).


## Usage

Just talk to your LLM:

- *"Tell me what topics are in session_003.mcap"*
- *"In session_017.mcap find all moments where voltage dropped below 22V"*
- *"Correlate IMU acceleration with motor current."*
- *"Compare average battery voltage across my last 5 runs"*
- *"What version of mcap-mcp-server am I running? Update it"*


## Tools

| Tool | Needs loading | What it does |
|------|:---:|-------------|
| `list_recordings` | no | Find MCAP files in your project (or any path) |
| `get_recording_info` | no | Metadata, channels, attachments for a file |
| `get_schema` | no | SQL table names & column types — for query planning |
| `load_recording` | — | **Decode MCAP into DuckDB** (the LLM calls this automatically) |
| `query` | yes | Run SQL (full DuckDB — including ASOF JOIN) |
| `get_version` | no | Server version, available decoders, upgrade command |

**[Project documentation](https://turkenberg.github.io/mcap_mcp_server/index.html)** — configuration, Docker, development setup, and architecture.


## Example SQL (under the hood)

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


## Performance

Metadata tools (`list_recordings`, `get_recording_info`, `get_schema`) return in **< 1 ms** regardless of file size. SQL queries execute in **1–20 ms** once data is loaded. The one-time `load_recording` cost scales with file size:

| Messages | File size | Load time | Memory | Query time |
|----------|-----------|-----------|--------|------------|
| 1K | 23 KB | 8 ms | < 1 MB | 1 ms |
| 10K | 220 KB | 90 ms | 0.5 MB | 1–3 ms |
| 100K | 2.2 MB | 0.7 s | 5 MB | 1–5 ms |
| 500K | 11 MB | 3.9 s | 23 MB | 2–9 ms |
| 1M | 23 MB | 8 s | 46 MB | 2–13 ms |
| 2M | 48 MB | 18 s | 92 MB | 2–22 ms |

*Measured on Apple M4 with JSON-encoded messages, 5 fields per message. Query times are median across aggregation, filter, and window function queries. Memory is the DuckDB in-memory footprint (default budget: 2 GB).*

> **Tip:** use `topics` and `start_time`/`end_time` filters on `load_recording` to load only what you need.


## Update

```bash
uvx mcap-mcp-server[all] --upgrade
```

Or ask your LLM — the `get_version` tool returns the running version and the upgrade command.


## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
