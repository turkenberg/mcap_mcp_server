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

    def test_missing_table_returns_hint(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")

        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(sql="SELECT * FROM gps"))
        assert "error" in result
        assert "hint" in result
        assert "load_recording" in result["hint"]
        assert "loaded_tables" in result
        assert "battery" in result["loaded_tables"]


class TestLoadRecordingMemoryInfo:
    def test_memory_budget_in_response(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(load_fn(file="session_001.mcap"))
        assert "memory_used_mb" in result
        assert "memory_budget_mb" in result
        assert result["memory_budget_mb"] == 2048

    def test_invalid_memory_budget(self):
        with pytest.raises(ValueError, match="too low"):
            ServerConfig(max_memory_mb=0)
        with pytest.raises(ValueError, match="too low"):
            ServerConfig(max_memory_mb=32)


class TestBtNodeNames:
    """Tests for the auto-unnested bt_node_names lookup table."""

    @pytest.fixture
    def bt_server(self, bt_snapshot_mcap: Path):
        config = ServerConfig(data_dir=bt_snapshot_mcap.parent)
        return create_server(config)

    def test_bt_node_names_table_created(self, bt_server):
        load_fn = _get_tool_fn(bt_server, "load_recording")
        result = json.loads(load_fn(file="bt_snapshot.mcap"))
        assert result["status"] == "loaded"
        assert "bt_node_names" in result["tables"]
        assert result["tables"]["bt_node_names"]["rows"] == 5
        assert result["tables"]["bt_node_names"]["columns"] == 3

    def test_bt_node_names_queryable(self, bt_server):
        load_fn = _get_tool_fn(bt_server, "load_recording")
        load_fn(file="bt_snapshot.mcap")

        query_fn = _get_tool_fn(bt_server, "query")
        result = json.loads(
            query_fn(sql="SELECT node_uid, node_name, node_type FROM bt_node_names ORDER BY node_uid")
        )
        assert result["row_count"] == 5
        assert result["columns"] == ["node_uid", "node_name", "node_type"]
        assert result["rows"][0][0] == 1
        assert result["rows"][0][1] == "NavigateToPose"
        assert result["rows"][0][2] == "Action"

    def test_bt_node_names_join_with_transitions(self, bt_server):
        load_fn = _get_tool_fn(bt_server, "load_recording")
        load_fn(file="bt_snapshot.mcap")

        query_fn = _get_tool_fn(bt_server, "query")
        result = json.loads(
            query_fn(
                sql=(
                    "SELECT n.node_name, n.node_type, "
                    "COUNT(*) as transitions, "
                    "SUM(CASE WHEN t.current_status = 3 THEN 1 ELSE 0 END) as failures "
                    "FROM bt_transition t "
                    "JOIN bt_node_names n ON t.node_uid = n.node_uid "
                    "GROUP BY n.node_name, n.node_type "
                    "ORDER BY failures DESC"
                )
            )
        )
        assert result["row_count"] > 0
        row_names = [r[0] for r in result["rows"]]
        assert "NavigateToPose" in row_names

    def test_bt_node_names_with_alias(self, bt_server):
        load_fn = _get_tool_fn(bt_server, "load_recording")
        result = json.loads(load_fn(file="bt_snapshot.mcap", alias="r1"))
        assert "r1_bt_node_names" in result["tables"]

        query_fn = _get_tool_fn(bt_server, "query")
        q_result = json.loads(
            query_fn(sql="SELECT COUNT(*) FROM r1_bt_node_names")
        )
        assert q_result["rows"][0][0] == 5

    def test_no_bt_node_names_without_snapshot(self, mcp_server):
        """Regular recordings without BT snapshot should not create the table."""
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(load_fn(file="session_001.mcap"))
        assert "bt_node_names" not in result["tables"]


def _get_tool_fn(server, name: str):
    """Extract a tool's callable from the FastMCP server by name."""
    for tool in server._tool_manager._tools.values():
        if tool.name == name:
            return tool.fn
    raise ValueError(f"Tool {name!r} not found")
