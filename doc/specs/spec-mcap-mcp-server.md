# Spec: MCAP Query MCP Server

## Title

`mcap-mcp-server` — A generic SQL query interface for MCAP robotics data via the Model Context Protocol.

## Status

**Phase 1 complete** — Core server, all decoders (JSON, Protobuf, ROS1, ROS2, FlatBuffers), query engine, and test suite implemented. Phase 2 items (memory management, SSE transport) pending.

## Date

2026-03-04

---

## 1. Problem Statement

### What is MCAP?

[MCAP](https://mcap.dev) is an open-source container file format for heterogeneous,
timestamped robotics data. It is encoding-agnostic (supports Protobuf, JSON, FlatBuffers,
ROS 1/2 messages, CDR, and custom encodings) and designed for high-throughput recording and
efficient indexed playback. MCAP is used across the robotics industry for logging sensor data,
control signals, diagnostics, and system events.

### The Problem

MCAP files are designed for **sequential playback** (in tools like Foxglove Studio) — not
for **analytical queries**. Today, answering questions like:

- "In which runs did motor temperature exceed 80°C?"
- "What is the average battery voltage across the last 50 missions?"
- "Correlate network latency with operator command delay"
- "Find all error log entries in the last week of runs"

...requires writing one-off scripts, manually opening files in a visualizer, or building
custom pipelines. There is no standard query interface for MCAP data.

### The Opportunity

The Model Context Protocol (MCP) provides a standard way for AI assistants and tools to
access external data sources. An MCP server that exposes MCAP data as queryable SQL tables
would allow any human or LLM to:

- Discover available recordings and their schemas
- Load data and run arbitrary SQL queries
- Compare signals across multiple recording sessions
- Get summary statistics without writing code

No such tool exists today. MCAP + MCP + DuckDB is a natural combination that fills this gap.

---

## 2. Goals & Non-Goals

### Goals

- **G1**: Provide a standards-based query interface (MCP protocol) for MCAP files, usable
  from Cursor, Claude Desktop, or any MCP-compatible client.
- **G2**: Support SQL as the query language (via DuckDB) — no custom DSL.
- **G3**: Be **encoding-agnostic** — work with any MCAP message encoding (JSON, Protobuf,
  FlatBuffers, ROS, CDR) through a pluggable decoder system.
- **G4**: Handle MCAP files up to 1 GB with acceptable latency (<5s for metadata, <30s for
  full-file load on SSD).
- **G5**: Zero infrastructure — no database server, no ETL pipeline. Point at a directory
  of MCAP files and go.
- **G6**: Read-only. The server never modifies MCAP files.
- **G7**: Be a generic, domain-agnostic tool. Works for any robotics platform, any sensor
  suite, any message schema.
- **G8**: Distribute as a PyPI package (primary) and Docker image (secondary).

### Non-Goals (for v1)

- **NG1**: Writing or modifying MCAP files.
- **NG2**: Real-time streaming / live telemetry ingestion.
- **NG3**: Video, image, or pointcloud data queries (binary blob topics are skipped).
- **NG4**: Persistent database storage (future — TSDB migration path).
- **NG5**: Authentication or multi-user access control.
- **NG6**: Arbitrary Python code execution (future power-user escape hatch).

---

## 3. Architecture Overview

```
┌───────────────────────────────────────────────────────────────────┐
│                        MCP Client                                 │
│              (Cursor / Claude Desktop / custom)                   │
└──────────────────────────┬────────────────────────────────────────┘
                           │ MCP Protocol (stdio or SSE)
┌──────────────────────────▼────────────────────────────────────────┐
│                     MCP Server Layer                               │
│                                                                    │
│  Tools:                          Resources:                        │
│  ┌─────────────────┐             ┌──────────────────────┐         │
│  │ list_recordings  │             │ mcap://recordings     │         │
│  │ get_recording_info│            │ mcap://schema/{file}  │         │
│  │ get_schema       │             └──────────────────────┘         │
│  │ load_recording   │                                              │
│  │ query            │                                              │
│  └─────────────────┘                                              │
└──────────────────────────┬────────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────────┐
│                     Query Engine (DuckDB)                          │
│                                                                    │
│  In-memory columnar SQL engine. Queries DataFrames as virtual      │
│  tables with zero-copy via Apache Arrow. C++ under the hood.      │
│                                                                    │
│  Registered tables (per loaded recording):                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ /topic_a │ │ /topic_b │ │ /topic_c │ │ /topic_d │  ...       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│                                                                    │
│  Cross-recording table (when multiple loaded):                     │
│  ┌──────────────────────────────────────┐                         │
│  │ _recordings  (metadata registry)     │                         │
│  └──────────────────────────────────────┘                         │
└──────────────────────────┬────────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────────┐
│                     MCAP Reader Layer                              │
│                                                                    │
│  mcap Python library (indexed reader):                             │
│  - get_summary() → metadata, schemas, channels, statistics        │
│  - iter_decoded_messages() → decoded message objects               │
│                                                                    │
│  Pluggable decoders:                                               │
│  ┌──────┐ ┌──────────┐ ┌──────────────┐ ┌─────┐ ┌───────┐      │
│  │ JSON │ │ Protobuf │ │ FlatBuffers  │ │ ROS │ │ CDR   │      │
│  └──────┘ └──────────┘ └──────────────┘ └─────┘ └───────┘      │
└──────────────────────────┬────────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────────┐
│                     File System                                    │
│                                                                    │
│  /data/                                                            │
│  ├── session_2026-01-15_001.mcap                                  │
│  ├── session_2026-01-16_002.mcap                                  │
│  ├── experiment_outdoor_003.mcap                                   │
│  └── ...                                                           │
└───────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| MCP Server | `mcp` Python SDK (official, Anthropic) | Standard protocol, supported by Cursor & Claude Desktop |
| SQL Engine | DuckDB (`duckdb` Python package) | In-process columnar analytics, C++ performance, zero-copy Arrow |
| MCAP Reader | `mcap` Python library | Standard MCAP reader with indexed access |
| Decoders | Pluggable per encoding | `mcap-protobuf-support`, `mcap-ros2-support`, etc. (official mcap decoder packages) + built-in JSON + FlatBuffers |
| DataFrames | pandas + pyarrow | Bridge between decoded messages and DuckDB |
| Transport | stdio (default) or HTTP+SSE | stdio for local use, SSE for remote/Docker |

### Why DuckDB

DuckDB is an embedded (in-process) analytical SQL database written in C++.

1. **SQL is universal.** Every LLM writes SQL fluently. Every engineer knows it. No custom
   query language to design, document, or maintain.
2. **Zero-copy DataFrame queries.** DuckDB reads pandas DataFrames directly via Apache Arrow
   without copying data. Load MCAP into a DataFrame once, query it N times at native speed.
3. **Analytical performance.** Columnar execution, vectorized processing, automatic
   parallelism. Handles millions of rows on a laptop.
4. **No infrastructure.** No server to install, no data ingestion pipeline. Single
   `pip install duckdb`.
5. **Future migration path.** DuckDB reads Parquet natively. When/if you move to archived
   Parquet or a TSDB, SQL queries stay the same — only the data source changes.

### Why Not Alternatives

| Alternative | Why not (for v1) |
|-------------|-----------------|
| InfluxDB / TimescaleDB | Requires running server, data ingestion, ops overhead |
| SQLite | Row-oriented, slow for analytical queries on millions of rows |
| Pandas only | No SQL interface, slow on large data, Python-specific API |
| Custom DSL | Massive design/maintenance burden, LLMs won't know it |
| Arbitrary Python exec | Security concerns, harder to sandbox, SQL covers 95% of use cases |

---

## 4. Data Model

### 4.1 MCAP File Structure

An MCAP file contains:

- **Channels**: Named topics (e.g., `/imu`, `/battery`, `/cmd_vel`, `/diagnostics`)
- **Schemas**: Message type definitions per channel (Protobuf descriptors, JSON schemas,
  FlatBuffer binary schemas, ROS message definitions, etc.)
- **Messages**: Timestamped, encoded data on each channel
- **Metadata**: Named key-value string maps (arbitrary, set by the recorder)
- **Attachments**: Named binary blobs (calibration files, config snapshots, etc.)
- **Statistics**: Message counts per channel, time ranges (stored in summary section)

The file format supports indexed access — the summary section at the end contains chunk
indexes that allow seeking to specific time ranges without scanning the entire file.

### 4.2 Topic → Table Mapping

When a recording is loaded, each MCAP channel/topic becomes a DuckDB table. The table name
is derived from the topic name by stripping the leading `/` and replacing `/` with `_`:

```
/imu            → table "imu"
/battery/status → table "battery_status"
/cmd_vel        → table "cmd_vel"
/diagnostics    → table "diagnostics"
```

Every table includes a synthetic `timestamp_us` (BIGINT) column derived from the MCAP
message `log_time` (nanoseconds → microseconds). This provides a consistent time column
across all tables for JOINs.

Additional columns come from the decoded message fields. Their types are mapped from the
message schema (see Section 4.4).

### 4.3 Metadata Table

A `_metadata` table is always created:

```sql
CREATE TABLE _metadata (
  record_name VARCHAR,  -- metadata record name (e.g., "session_info")
  key VARCHAR,
  value VARCHAR
);
```

This captures all MCAP metadata records as queryable rows.

### 4.4 Multi-Recording Loading

When multiple recordings are loaded, tables are prefixed with a user-chosen alias:

```sql
-- Single recording (default, no prefix)
SELECT * FROM imu WHERE accel_z > 15.0

-- Multiple recordings with aliases
SELECT * FROM r1_imu WHERE accel_z > 15.0
UNION ALL
SELECT * FROM r2_imu WHERE accel_z > 15.0

-- Cross-recording registry
SELECT * FROM _recordings
-- columns: alias, file_path, start_time, end_time, duration_s,
--          message_count, channel_count, ...
```

### 4.5 Type Mapping

Message fields are mapped to DuckDB types based on their schema type:

| Schema type | DuckDB type |
|------------|-------------|
| bool | BOOLEAN |
| int8 / byte | TINYINT |
| uint8 | UTINYINT |
| int16 | SMALLINT |
| uint16 | USMALLINT |
| int32 / int | INTEGER |
| uint32 | UINTEGER |
| int64 / long | BIGINT |
| uint64 | UBIGINT |
| float / float32 | FLOAT |
| double / float64 | DOUBLE |
| string | VARCHAR |
| bytes | BLOB |
| enum | VARCHAR (string representation) |
| nested message | Flattened with dot notation (e.g., `pose.position.x`) |
| repeated / array | JSON string (v1), native LIST type (future) |

Nested messages are flattened to dot-separated column names up to a configurable depth
(default: 3 levels). For example, a Protobuf message with `pose.position.x` becomes a
column named `pose_position_x`.

---

## 5. MCP Tool Specifications

### 5.1 `list_recordings`

**Purpose:** Discover available MCAP files in the configured data directory.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | No | Override directory to scan. Defaults to configured `MCAP_DATA_DIR`. |
| `after` | string | No | Filter recordings after this ISO8601 datetime. |
| `before` | string | No | Filter recordings before this ISO8601 datetime. |

**Returns:** JSON array of recording summaries.

```json
[
  {
    "file": "session_2026-01-15_001.mcap",
    "path": "/data/session_2026-01-15_001.mcap",
    "size_mb": 203.4,
    "start_time": "2026-01-15T14:32:00.000Z",
    "end_time": "2026-01-15T15:02:42.500Z",
    "duration_s": 1842.5,
    "message_count": 461200,
    "channels": [
      {"topic": "/imu", "message_count": 184000, "schema": "sensor_msgs/Imu"},
      {"topic": "/battery", "message_count": 92000, "schema": "sensor_msgs/BatteryState"},
      {"topic": "/cmd_vel", "message_count": 92000, "schema": "geometry_msgs/Twist"},
      {"topic": "/diagnostics", "message_count": 93200, "schema": "diagnostic_msgs/DiagnosticArray"}
    ],
    "metadata_keys": ["session_id", "operator", "location"]
  }
]
```

**Implementation notes:**

- Uses MCAP indexed reader `get_summary()` per file — reads only the summary section at the
  **end** of the file. For a 1 GB file, this takes <100ms.
- Results are cached in memory after first scan. Cache invalidation via directory mtime check
  or explicit reload.

### 5.2 `get_recording_info`

**Purpose:** Get full metadata, channel details, and attachment list for a specific recording.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file` | string | Yes | Filename or full path to the MCAP file. |

**Returns:** Detailed recording information.

```json
{
  "file": "session_2026-01-15_001.mcap",
  "path": "/data/session_2026-01-15_001.mcap",
  "size_mb": 203.4,
  "library": "mcap-ros2-recorder",
  "start_time": "2026-01-15T14:32:00.000Z",
  "end_time": "2026-01-15T15:02:42.500Z",
  "duration_s": 1842.5,
  "message_count": 461200,
  "channels": {
    "/imu": {
      "schema_name": "sensor_msgs/Imu",
      "message_encoding": "cdr",
      "message_count": 184000
    },
    "/battery": {
      "schema_name": "sensor_msgs/BatteryState",
      "message_encoding": "cdr",
      "message_count": 92000
    }
  },
  "metadata": {
    "session_info": {"session_id": "abc-123", "operator": "jdoe"},
    "hardware": {"robot_model": "my_robot", "serial": "001"}
  },
  "attachments": [
    {"name": "calibration.yaml", "size_bytes": 2340, "media_type": "application/yaml"},
    {"name": "config.json", "size_bytes": 892, "media_type": "application/json"}
  ]
}
```

### 5.3 `get_schema`

**Purpose:** Inspect what topics and fields are available for SQL querying.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file` | string | Yes | Filename or full path to the MCAP file. |
| `topic` | string | No | Specific topic. If omitted, returns all topics. |

**Returns:** Schema information optimized for SQL query planning.

```json
{
  "file": "session_2026-01-15_001.mcap",
  "topics": {
    "/imu": {
      "table_name": "imu",
      "message_count": 184000,
      "schema_name": "sensor_msgs/Imu",
      "message_encoding": "cdr",
      "fields": [
        {"name": "timestamp_us", "type": "BIGINT", "description": "Message timestamp (microseconds, from MCAP log_time)"},
        {"name": "orientation_x", "type": "DOUBLE"},
        {"name": "orientation_y", "type": "DOUBLE"},
        {"name": "orientation_z", "type": "DOUBLE"},
        {"name": "orientation_w", "type": "DOUBLE"},
        {"name": "angular_velocity_x", "type": "DOUBLE"},
        {"name": "angular_velocity_y", "type": "DOUBLE"},
        {"name": "angular_velocity_z", "type": "DOUBLE"},
        {"name": "linear_acceleration_x", "type": "DOUBLE"},
        {"name": "linear_acceleration_y", "type": "DOUBLE"},
        {"name": "linear_acceleration_z", "type": "DOUBLE"}
      ]
    },
    "/battery": {
      "table_name": "battery",
      "message_count": 92000,
      "schema_name": "sensor_msgs/BatteryState",
      "message_encoding": "cdr",
      "fields": [
        {"name": "timestamp_us", "type": "BIGINT", "description": "Message timestamp (microseconds, from MCAP log_time)"},
        {"name": "voltage", "type": "FLOAT"},
        {"name": "current", "type": "FLOAT"},
        {"name": "percentage", "type": "FLOAT"},
        {"name": "present", "type": "BOOLEAN"}
      ]
    }
  },
  "metadata_table": "_metadata",
  "sql_hint": "Tables are named from topics: strip leading '/', replace '/' with '_'. All tables have a 'timestamp_us' column (BIGINT, microseconds). Use it for JOINs across topics."
}
```

**The `sql_hint` field** is critical — it gives LLMs the context they need to write correct
SQL without additional prompting.

### 5.4 `load_recording`

**Purpose:** Decode an MCAP file and load its data into DuckDB for SQL querying.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file` | string | Yes | Filename or full path to the MCAP file. |
| `alias` | string | No | Table prefix for multi-recording loading (e.g., "r1"). No prefix by default. |
| `topics` | string[] | No | Specific topics to load. Defaults to all decodable topics. |
| `start_time` | string | No | ISO8601 or epoch microseconds. Load data from this time. |
| `end_time` | string | No | ISO8601 or epoch microseconds. Load data until this time. |
| `downsample` | integer | No | Keep every Nth message (e.g., 10 = 10x reduction). For large files. |

**Returns:** Load confirmation with table info.

```json
{
  "status": "loaded",
  "file": "session_2026-01-15_001.mcap",
  "alias": null,
  "tables": {
    "imu": {"rows": 184000, "columns": 11},
    "battery": {"rows": 92000, "columns": 5},
    "cmd_vel": {"rows": 92000, "columns": 6},
    "diagnostics": {"rows": 93200, "columns": 4}
  },
  "skipped_topics": ["/camera/image_raw"],
  "skipped_reason": "no decoder available or binary blob",
  "total_rows": 461200,
  "memory_mb": 45.2,
  "load_time_s": 3.8
}
```

**Implementation notes:**

- **Decoder selection**: The server inspects each channel's `message_encoding` and
  `schema_encoding` fields to select the appropriate decoder:
  - `json` / `jsonschema` → built-in JSON decoder
  - `protobuf` → `mcap-protobuf-support` (optional dependency)
  - `flatbuffer` → `flatbuffers` reflection decoder (optional dependency)
  - `ros1msg` → `mcap-ros1-support` (optional dependency)
  - `cdr` (ROS 2) → `mcap-ros2-support` (optional dependency)
  - Unknown → topic is skipped with a warning
- **Topics with no available decoder** are skipped and listed in `skipped_topics`.
- **Memory management**: For large files, the `topics`, `start_time`/`end_time`, and
  `downsample` parameters reduce memory usage. An LRU cache evicts oldest loaded recordings
  when the configurable memory limit is reached.
- **MCAP indexed reading**: `iter_messages(topics=..., start_time=..., end_time=...)` uses
  chunk indexes to seek directly to relevant data.

### 5.5 `query`

**Purpose:** Execute a SQL query against loaded recording data.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `sql` | string | Yes | SQL query to execute. |
| `limit` | integer | No | Override result row limit. Default: 1000. Max: 10000. |
| `format` | string | No | Output format: `"table"` (default), `"csv"`, `"json"`. |

**Returns:** Query results.

```json
{
  "columns": ["timestamp_us", "voltage", "current"],
  "types": ["BIGINT", "FLOAT", "FLOAT"],
  "rows": [
    [1736950320000000, 23.4, -2.1],
    [1736950320020000, 23.3, -2.0],
    [1736950320040000, 23.1, -1.8]
  ],
  "row_count": 3,
  "truncated": false,
  "execution_time_ms": 12
}
```

**Example queries:**

```sql
-- Find voltage drops below threshold
SELECT timestamp_us, voltage, percentage
FROM battery
WHERE voltage < 22.0
ORDER BY timestamp_us

-- Correlate battery state with acceleration
SELECT
  b.timestamp_us,
  b.voltage,
  i.linear_acceleration_x,
  i.linear_acceleration_y,
  i.linear_acceleration_z,
  SQRT(
    i.linear_acceleration_x * i.linear_acceleration_x +
    i.linear_acceleration_y * i.linear_acceleration_y +
    i.linear_acceleration_z * i.linear_acceleration_z
  ) as accel_magnitude
FROM battery b
ASOF JOIN imu i ON b.timestamp_us >= i.timestamp_us
WHERE b.voltage < 23.0

-- Time-windowed statistics (1-second windows)
SELECT
  (timestamp_us / 1000000) as second,
  AVG(voltage) as avg_voltage,
  MIN(voltage) as min_voltage,
  MAX(current) as max_current
FROM battery
GROUP BY second
ORDER BY second

-- Cross-recording comparison
SELECT 'run1' as recording, AVG(voltage) as avg_v FROM r1_battery
UNION ALL
SELECT 'run2' as recording, AVG(voltage) as avg_v FROM r2_battery

-- Search metadata
SELECT * FROM _metadata
WHERE key LIKE '%serial%'

-- Find error diagnostics
SELECT timestamp_us, message
FROM diagnostics
WHERE level >= 2
ORDER BY timestamp_us DESC
LIMIT 20
```

**Note on ASOF JOIN**: DuckDB supports `ASOF JOIN`, which is ideal for joining time-series
tables that have different sampling rates. Instead of requiring exact timestamp matches,
it joins each row to the nearest preceding row in the other table. This is critical for
robotics data where topics are often logged at different frequencies.

**Safety:**

- DuckDB is configured in read-only mode. Data modification statements are rejected.
- File system access functions (`read_csv`, `read_parquet`, etc.) are disabled.
- Query timeout: configurable, default 30 seconds.
- Result row limit: configurable, default 1000, max 10000.

---

## 6. MCP Resources

Read-only MCP resources for client-side browsing:

| URI Pattern | Description |
|-------------|-------------|
| `mcap://recordings` | JSON index of all available recordings |
| `mcap://schema/{filename}` | Full schema for a specific recording |

---

## 7. Pluggable Decoder Architecture

The server must handle any MCAP message encoding. This is achieved via a decoder registry:

```python
class MessageDecoder(Protocol):
    """Interface for message decoders."""

    def can_decode(self, message_encoding: str, schema_encoding: str) -> bool:
        """Return True if this decoder handles the given encoding."""
        ...

    def decode(self, schema: bytes, data: bytes) -> dict:
        """Decode a single message into a flat dict of field→value."""
        ...

    def get_field_info(self, schema: bytes) -> list[FieldInfo]:
        """Extract field names and types from the schema definition."""
        ...
```

### Built-in Decoders

| Encoding | Schema encoding | Decoder | Dependency |
|----------|----------------|---------|------------|
| `json` | `jsonschema` | `JsonDecoder` | None (stdlib) |

### Optional Decoders (installed via extras)

| Encoding | Schema encoding | Decoder | Dependency |
|----------|----------------|---------|------------|
| `protobuf` | `protobuf` | `ProtobufDecoder` | `mcap-protobuf-support` |
| `flatbuffer` | `flatbuffer` | `FlatBufferDecoder` | `flatbuffers` |
| `ros1msg` | `ros1msg` | `Ros1Decoder` | `mcap-ros1-support` |
| `cdr` | `ros2msg` / `ros2idl` | `Ros2Decoder` | `mcap-ros2-support` |

### Installation with Decoder Support

```bash
# Base (JSON only)
pip install mcap-mcp-server

# With Protobuf support
pip install mcap-mcp-server[protobuf]

# With ROS 2 support
pip install mcap-mcp-server[ros2]

# With FlatBuffers support
pip install mcap-mcp-server[flatbuffers]

# Everything
pip install mcap-mcp-server[all]
```

### Custom Decoders

Users can register custom decoders via a Python entry point:

```toml
# In a third-party package's pyproject.toml
[project.entry-points."mcap_mcp_server.decoders"]
my_custom = "my_package:MyCustomDecoder"
```

The server discovers and loads all registered decoders at startup.

---

## 8. MCAP Reading Strategy

### 8.1 Summary-Only Access (Fast Path)

For `list_recordings`, `get_recording_info`, and `get_schema`:

- `get_summary()` reads the MCAP summary section at the **end** of the file.
- Returns metadata, schemas, channels, and statistics without scanning messages.
- For a 1 GB file, this takes <100ms.

### 8.2 Indexed Message Iteration (Data Loading)

For `load_recording`:

- `iter_messages(topics=..., start_time=..., end_time=...)` uses chunk indexes to seek
  directly to relevant data.
- Avoids reading chunks outside the requested time window or topic set.
- Messages are decoded in a streaming fashion and accumulated into per-column arrays.

### 8.3 Batch Decode Optimization

Instead of creating Python dicts per message (slow), accumulate values into per-field lists
or numpy arrays, then construct DataFrames in one pass:

```python
columns = {name: [] for name in field_names}
columns["timestamp_us"] = []

for schema, channel, message in reader.iter_messages(topics=[topic]):
    decoded = decoder.decode(schema.data, message.data)
    columns["timestamp_us"].append(message.log_time // 1000)  # ns → μs
    for name in field_names:
        columns[name].append(decoded.get(name))

df = pd.DataFrame(columns)
```

### 8.4 Nested Message Flattening

For encodings with nested messages (Protobuf, ROS), fields are flattened:

```
pose.position.x → column "pose_position_x"
pose.orientation.w → column "pose_orientation_w"
header.stamp.sec → column "header_stamp_sec"
```

Flattening depth is configurable (default: 3). Deeper nesting is serialized as JSON strings.

---

## 9. Performance Considerations

### 9.1 Expected Performance

| Scenario | File size | Messages | Expected load time |
|----------|----------|----------|--------------------|
| Short test | 10 MB | ~5K | < 1s |
| Typical session | 200 MB | ~100K | 3-5s |
| Long session | 500 MB | ~250K | 8-15s |
| Maximum expected | 1 GB | ~500K | 15-30s |

### 9.2 Memory Budget

Rule of thumb: in-memory DataFrame ≈ 2-4x compressed MCAP size.

| MCAP size | Approx. memory |
|-----------|---------------|
| 10 MB | 20-40 MB |
| 200 MB | 400-800 MB |
| 1 GB | 2-4 GB |

### 9.3 Mitigation Strategies for Large Files

1. **Topic filtering**: Only decode topics the user requests.
2. **Time-range filtering**: Use MCAP chunk indexes to skip irrelevant windows.
3. **Downsampling**: Load every Nth message for exploratory queries.
4. **LRU cache**: Evict oldest recordings when memory limit is reached (default: 2 GB).
5. **Columnar batch decode**: Avoid per-message Python object overhead.

### 9.4 Performance Benchmarks (Required Before v1 Release)

- [ ] `list_recordings` latency with 10, 100, 1000 files
- [ ] `load_recording` latency and memory for 10 MB, 200 MB, 500 MB, 1 GB files
- [ ] `query` latency for simple filter, JOIN, GROUP BY on 100K–500K rows
- [ ] Decoder throughput per encoding type (messages/sec)
- [ ] Memory profile under multi-recording loading

---

## 10. Configuration

### 10.1 Environment Variables

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

### 10.2 Config File (Optional)

`mcap-mcp-server.toml`:

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

---

## 11. Distribution

### 11.1 Primary: PyPI Package

```bash
pip install mcap-mcp-server

# Or zero-install via uvx
uvx mcap-mcp-server --data-dir /path/to/data
```

**Cursor** (`.cursor/mcp.json`):

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

**Claude Desktop** (`claude_desktop_config.json`):

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

> Set `MCAP_DATA_DIR` only if recordings live outside the project directory.

**Advantages**: Standard MCP pattern. No Docker. Direct file access. Simple setup.

### 11.2 Secondary: Docker Image

```bash
docker run -d \
  -v /data/recordings:/data:ro \
  -e MCAP_DATA_DIR=/data \
  -e MCAP_TRANSPORT=sse \
  -p 8080:8080 \
  ghcr.io/<owner>/mcap-mcp-server:latest
```

**Cursor SSE config**:

```json
{
  "mcpServers": {
    "mcap-query": {
      "url": "http://mcap-server:8080/sse"
    }
  }
}
```

**Advantages**: Isolation, deployable on shared infrastructure, read-only volume mount.

### 11.3 Recommendation by Use Case

| Use case | Recommendation |
|----------|---------------|
| Individual developer on laptop | PyPI + uvx |
| Cursor / Claude Desktop integration | PyPI + uvx (stdio) |
| Shared team data server | Docker (SSE transport) |
| CI/CD analysis pipelines | Docker |
| Air-gapped environments | PyPI wheel with vendored deps |

---

## 12. Package Structure

```
mcap-mcp-server/
├── pyproject.toml
├── README.md
├── LICENSE
├── Dockerfile
├── src/
│   └── mcap_mcp_server/
│       ├── __init__.py
│       ├── __main__.py              # Entry point: parse args, start server
│       ├── server.py                # MCP server setup, tool/resource registration
│       ├── mcap_reader.py           # MCAP summary, schema extraction, message iteration
│       ├── decoder_registry.py      # Pluggable decoder discovery and registration
│       ├── decoders/
│       │   ├── __init__.py
│       │   ├── json_decoder.py      # Built-in JSON message decoder
│       │   ├── protobuf_decoder.py  # Optional: Protobuf decoder
│       │   ├── flatbuffer_decoder.py# Optional: FlatBuffers decoder
│       │   ├── ros1_decoder.py      # Optional: ROS 1 decoder
│       │   └── ros2_decoder.py      # Optional: ROS 2 decoder
│       ├── query_engine.py          # DuckDB wrapper: table registration, query, safety
│       ├── recording_index.py       # Directory scanning, caching, filtering
│       ├── flatten.py               # Nested message flattening logic
│       └── config.py                # Config loading: env vars, TOML, CLI args
└── tests/
    ├── conftest.py
    ├── test_mcap_reader.py
    ├── test_json_decoder.py
    ├── test_query_engine.py
    ├── test_recording_index.py
    ├── test_flatten.py
    ├── test_server_integration.py
    └── fixtures/
        ├── simple.mcap              # JSON-encoded test file
        ├── protobuf.mcap            # Protobuf-encoded test file
        └── multi_topic.mcap         # Multi-channel test file
```

---

## 13. Dependencies

### Required

| Package | Purpose |
|---------|---------|
| `mcp` | MCP server SDK |
| `mcap` | MCAP file reading |
| `duckdb` | In-process SQL analytics |
| `pandas` | DataFrame construction |
| `pyarrow` | Zero-copy Arrow bridge |

### Optional (decoder extras)

| Extra | Packages |
|-------|----------|
| `[protobuf]` | `mcap-protobuf-support`, `protobuf` |
| `[flatbuffers]` | `flatbuffers` |
| `[ros1]` | `mcap-ros1-support` |
| `[ros2]` | `mcap-ros2-support` |
| `[all]` | All of the above |

### System Requirements

- Python >= 3.10
- No C compiler needed (all deps have wheels)
- No external services

---

## 14. Security

### Read-Only Enforcement

- MCAP files are opened read-only.
- DuckDB is configured to reject data modification and file system access functions.
- Docker deployments use `:ro` volume mounts.

### SQL Safety

- Query timeout prevents resource exhaustion (default 30s).
- Row limit prevents memory exhaustion (default 1000, max 10000).
- File system functions disabled (`read_csv`, `read_parquet`, `COPY TO`, `EXPORT`).

### Audit

- All tool invocations are logged with timestamp and parameters.
- Configurable log level.

---

## 15. Future Extensions (Post-v1)

| Extension | Phase | Description |
|-----------|-------|-------------|
| TSDB backend | v2 | Ingest MCAP data into TimescaleDB/QuestDB for fleet-scale queries |
| Parquet archival | v2 | Convert MCAP to Parquet; DuckDB reads Parquet natively |
| Python execution | v2 | Sandboxed pandas/numpy code execution for power users |
| Video correlation | v3 | Extract video frames at timestamps returned by SQL queries |
| Event definitions | v2 | User-defined SQL views as named "events" (e.g., `CREATE VIEW low_battery AS ...`) |
| Report generation | v3 | LLM-driven report generation from query results |
| WebSocket transport | v2 | Real-time query streaming for dashboards |
| Attachment extraction | v2 | Query/download MCAP attachments (config files, calibration) |

---

## 16. Open Questions

1. **Package name**: `mcap-mcp-server` vs `mcap-query-mcp` vs `mcap-duckdb-mcp`?
   Prefer `mcap-mcp-server` for discoverability.

2. **Separate repository**: This should live in its own public repository (not inside any
   company-specific codebase) to be usable by the broader MCAP community.

3. **License**: GNU GPL v3. Copyleft ensures derivatives stay open-source.

4. **MCAP decoder ecosystem**: The official `mcap-protobuf-support` and `mcap-ros2-support`
   packages provide `DecoderFactory` classes. Should we wrap those directly, or build our
   own decoder abstraction? Recommendation: wrap the official packages for maximum
   compatibility.

5. **Handling large repeated/array fields**: Some ROS messages contain large arrays
   (pointclouds, images as byte arrays). These should be excluded from DataFrame loading
   by default. Need a policy for which field types to skip.

6. **DuckDB persistence**: Should users be able to save a loaded session to a DuckDB file
   for later re-query without re-loading the MCAP? This would be a shortcut for repeated
   analysis. However, it creates a writable artifact — conflicts with read-only principle.

---

## 17. Implementation Plan

### Phase 1: Core — done

- [x] Repository setup, CI, `pyproject.toml`
- [x] MCAP reader layer (summary, schema extraction, message iteration)
- [x] JSON decoder (built-in, no optional deps)
- [x] DuckDB query engine (register tables, execute SQL, enforce safety)
- [x] MCP server with stdio transport
- [x] Tools: `list_recordings`, `get_schema`, `load_recording`, `query`
- [x] Tests with JSON-encoded MCAP fixture files (106 tests)
- [x] README with usage examples and MCP client configuration

### Phase 1b: All Decoders — done

- [x] FlatBuffers decoder (custom bfbs parser + binary decode)
- [x] Protobuf decoder (via `mcap-protobuf-support`)
- [x] ROS 1 decoder (via `mcap-ros1-support`)
- [x] ROS 2 decoder (via `mcap-ros2-support`)
- [x] Decoder registry with entry-point discovery

### Phase 2: Polish — pending

- [ ] `get_recording_info` tool
- [ ] MCP resources
- [ ] Memory management (LRU cache)
- [ ] Multi-recording loading with aliases
- [ ] Downsampling support

### Phase 3: Distribution — pending

- [ ] PyPI package publishing
- [ ] Docker image and Dockerfile
- [ ] SSE transport support
- [ ] CI/CD for publishing

### Phase 4: Performance — pending

- [ ] Load performance optimizations (see [load-performance spec](spec-load-performance.md))
- [ ] Benchmarks on real-world MCAP files (10 MB → 1 GB)
- [ ] Edge cases (corrupted files, missing schemas, empty recordings)

---

## 18. Success Criteria

1. An engineer or LLM can go from "what MCAP files do I have?" to "here's the SQL result"
   in under 60 seconds using only MCP tool calls.

2. Loading a 200 MB MCAP file takes < 5 seconds.

3. A SQL query on 100K rows returns in < 100ms.

4. The server works with at least JSON and one binary encoding (FlatBuffers or Protobuf)
   at v1 release.

5. `pip install mcap-mcp-server && uvx mcap-mcp-server` works out of the box with zero
   configuration beyond setting `MCAP_DATA_DIR`.
