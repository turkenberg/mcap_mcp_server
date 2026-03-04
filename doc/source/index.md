# mcap-mcp-server

**A generic SQL query interface for MCAP robotics data via the Model Context Protocol.**

---

## Overview

`mcap-mcp-server` is an MCP server that exposes [MCAP](https://mcap.dev) recording files as queryable SQL tables using [DuckDB](https://duckdb.org). It allows any MCP-compatible client (Cursor, Claude Desktop, etc.) to:

- **Discover** available MCAP recordings and their schemas
- **Load** and decode messages from any encoding (Protobuf, JSON, ROS 1/2, CDR, FlatBuffers)
- **Query** data with standard SQL — no custom DSL, no one-off scripts
- **Compare** signals across multiple recording sessions

Zero infrastructure required — point at a directory of MCAP files and go.

## Status

> **Draft** — Design phase. Not yet implemented. See the [spec](../specs/spec-mcap-mcp-server.md) for the full design.

## Documentation

```{toctree}
:maxdepth: 2
:hidden:

Specification <../specs/spec-mcap-mcp-server>
```

## Links

- [MCAP format](https://mcap.dev)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [DuckDB](https://duckdb.org)
