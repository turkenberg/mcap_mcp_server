"""Integration tests: exercise the MCP tools end-to-end."""

import json
from pathlib import Path

import pytest

from mcap_mcp_server.config import ServerConfig
from mcap_mcp_server.server import create_server


@pytest.fixture
def mcp_server(tmp_mcap_dir: Path):
    """Create a configured MCP server pointing at test data."""
    config = ServerConfig(data_dir=tmp_mcap_dir)
    return create_server(config)


class TestListRecordings:
    def test_returns_recordings(self, mcp_server, tmp_mcap_dir: Path):
        tool_fn = _get_tool_fn(mcp_server, "list_recordings")
        result = json.loads(tool_fn())
        assert len(result) == 2

    def test_filter_by_after(self, mcp_server):
        tool_fn = _get_tool_fn(mcp_server, "list_recordings")
        result = json.loads(tool_fn(after="2025-01-01T00:00:00Z"))
        assert len(result) == 0


class TestGetSchema:
    def test_returns_schema(self, mcp_server):
        tool_fn = _get_tool_fn(mcp_server, "get_schema")
        result = json.loads(tool_fn(file="session_001.mcap"))
        assert "/battery" in result["topics"]
        battery = result["topics"]["/battery"]
        assert battery["table_name"] == "battery"
        field_names = {f["name"] for f in battery["fields"]}
        assert "timestamp_us" in field_names
        assert "voltage" in field_names

    def test_sql_hint_present(self, mcp_server):
        tool_fn = _get_tool_fn(mcp_server, "get_schema")
        result = json.loads(tool_fn(file="session_001.mcap"))
        assert "sql_hint" in result
        assert "timestamp_us" in result["sql_hint"]


class TestLoadRecording:
    def test_loads_successfully(self, mcp_server):
        tool_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(tool_fn(file="session_001.mcap"))
        assert result["status"] == "loaded"
        assert "battery" in result["tables"]
        assert result["tables"]["battery"]["rows"] == 100

    def test_load_with_alias(self, mcp_server):
        tool_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(tool_fn(file="session_001.mcap", alias="r1"))
        assert "r1_battery" in result["tables"]

    def test_load_with_topic_filter(self, mcp_server):
        tool_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(tool_fn(file="session_002.mcap", topics=["/imu"]))
        table_names = list(result["tables"].keys())
        assert any("imu" in t for t in table_names)
        assert not any("cmd_vel" in t for t in table_names)


class TestQuery:
    def test_simple_select(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")

        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(sql="SELECT * FROM battery LIMIT 5"))
        assert result["row_count"] == 5
        assert "voltage" in result["columns"]

    def test_aggregation_query(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")

        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(
            query_fn(sql="SELECT AVG(voltage) as avg_v, MIN(voltage) as min_v FROM battery")
        )
        assert result["row_count"] == 1

    def test_metadata_query(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")

        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(sql="SELECT * FROM _metadata"))
        assert result["row_count"] > 0

    def test_blocked_sql(self, mcp_server):
        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(sql="COPY battery TO '/tmp/x.csv'"))
        assert "error" in result

    def test_multi_topic_join(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_002.mcap")

        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(
            query_fn(
                sql=(
                    "SELECT i.timestamp_us, i.linear_acceleration_x, c.linear_x "
                    "FROM imu i ASOF JOIN cmd_vel c ON i.timestamp_us >= c.timestamp_us "
                    "LIMIT 5"
                )
            )
        )
        assert result["row_count"] > 0


def _get_tool_fn(server, name: str):
    """Extract a tool's callable from the FastMCP server by name."""
    for tool in server._tool_manager._tools.values():
        if tool.name == name:
            return tool.fn
    raise ValueError(f"Tool {name!r} not found")
