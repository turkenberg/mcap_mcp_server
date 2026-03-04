# mcap-mcp-server

**SQL query interface for MCAP robotics data via the Model Context Protocol.**

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

Point this server at a directory of MCAP files and query them with SQL. No database server, no ETL, no custom scripts.

## Current state

| Component | Status |
|-----------|--------|
| Core server (list, load, query, schema) | Done |
| Decoders (JSON, Protobuf, ROS1, ROS2, FlatBuffers) | Done |
| Test suite (106 tests) | Passing |
| Performance optimizations | Profiled, not yet implemented |
| Distribution (PyPI, Docker) | Pending |

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

- [MCAP format](https://mcap.dev)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [DuckDB](https://duckdb.org)
