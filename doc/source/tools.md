# MCP Tools

Four tools are exposed via the Model Context Protocol. Typical workflow: `list_recordings` → `get_schema` → `load_recording` → `query`.

## list_recordings

Discover available MCAP files in the configured data directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | No | Override scan directory (defaults to `MCAP_DATA_DIR`) |
| `after` | string | No | ISO 8601 datetime — only recordings after this time |
| `before` | string | No | ISO 8601 datetime — only recordings before this time |

Returns a JSON array of recording summaries: filename, size, duration, channel list, message counts, metadata keys.

## get_schema

Inspect topics, table names, column names and DuckDB types before loading. Essential for query planning.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Filename or path to the MCAP file |
| `topic` | string | No | Filter to a single topic |

Returns per-topic field information with DuckDB types and a `sql_hint` explaining table naming and JOIN conventions.

## load_recording

Decode an MCAP file and register its data as DuckDB tables. Must be called before `query`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Filename or path to the MCAP file |
| `alias` | string | No | Table prefix for multi-recording comparison (e.g. `"r1"`) |
| `topics` | string[] | No | Subset of topics to load (defaults to all decodable) |
| `start_time` | string | No | ISO 8601 or epoch microseconds — start of time window |
| `end_time` | string | No | ISO 8601 or epoch microseconds — end of time window |
| `downsample` | integer | No | Keep every Nth message |

Returns table names, row counts, column counts, and load time. Topics without a matching decoder are skipped and listed.

### Table naming

Topics are mapped to table names by stripping the leading `/` and replacing `/` with `_`:

| Topic | Table name |
|-------|-----------|
| `/imu` | `imu` |
| `/battery/status` | `battery_status` |
| `/sensors/power` | `sensors_power` |

With an alias `"r1"`, tables become `r1_imu`, `r1_battery_status`, etc.

Every table includes a `timestamp_us` column (BIGINT, microseconds) derived from the MCAP message log time. Use it for cross-topic JOINs.

A `_metadata` table is always created with columns `(record_name, key, value)` containing all MCAP metadata records.

## query

Execute SQL against loaded data. Full DuckDB SQL is supported, including `ASOF JOIN`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sql` | string | Yes | SQL query |
| `limit` | integer | No | Override row limit (default: 1000, max: 10000) |
| `format` | string | No | `"table"` (default), `"csv"`, or `"json"` |

Returns columns, types, rows, row count, truncation flag, and execution time.
