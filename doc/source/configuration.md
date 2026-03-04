# Configuration

Configuration is layered: **defaults → TOML file → environment variables → CLI arguments**. Each layer overrides the previous.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCAP_DATA_DIR` | `.` | Root directory to scan for MCAP files |
| `MCAP_RECURSIVE` | `true` | Scan subdirectories |
| `MCAP_MAX_MEMORY_MB` | `2048` | Max memory for loaded data |
| `MCAP_QUERY_TIMEOUT_S` | `30` | SQL query timeout (seconds) |
| `MCAP_DEFAULT_ROW_LIMIT` | `1000` | Default result row limit |
| `MCAP_MAX_ROW_LIMIT` | `10000` | Maximum allowed row limit |
| `MCAP_LOG_LEVEL` | `INFO` | Log level |
| `MCAP_TRANSPORT` | `stdio` | Transport: `stdio` or `sse` |
| `MCAP_SSE_PORT` | `8080` | Port for SSE transport |
| `MCAP_FLATTEN_DEPTH` | `3` | Max nesting depth for message flattening |

## TOML config file

Optional. Place a `mcap-mcp-server.toml` in the working directory:

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

## MCP client integration

### Cursor (`.cursor/mcp.json`)

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

### Claude Desktop (`claude_desktop_config.json`)

Same format as Cursor.

### Docker (SSE)

```bash
docker run -d \
  -v /data/recordings:/data:ro \
  -e MCAP_DATA_DIR=/data \
  -e MCAP_TRANSPORT=sse \
  -p 8080:8080 \
  ghcr.io/turkenberg/mcap-mcp-server:latest
```

Then in Cursor: `"url": "http://localhost:8080/sse"`.
