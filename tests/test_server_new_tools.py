"""Tests for MCP tools: get_recording_info, and server helpers."""

import decimal
import json
from datetime import datetime
from pathlib import Path

import pytest

from mcap_mcp_server.config import ServerConfig
from mcap_mcp_server.server import _json_default, _parse_datetime, _parse_time_to_ns, _resolve_file, create_server


@pytest.fixture
def mcp_server(tmp_mcap_dir: Path):
    config = ServerConfig(data_dir=tmp_mcap_dir)
    return create_server(config)


def _get_tool_fn(server, name: str):
    for tool in server._tool_manager._tools.values():
        if tool.name == name:
            return tool.fn
    raise ValueError(f"Tool {name!r} not found")


# ---- get_recording_info ----

class TestGetRecordingInfo:
    def test_returns_info(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "get_recording_info")
        result = json.loads(fn(file="session_001.mcap"))
        assert result["file"] == "session_001.mcap"
        assert "path" in result
        assert result["size_mb"] >= 0
        assert result["message_count"] == 100
        assert result["duration_s"] > 0
        assert "/battery" in result["channels"]
        ch = result["channels"]["/battery"]
        assert ch["schema_name"] == "BatteryState"
        assert ch["message_encoding"] == "json"
        assert ch["message_count"] == 100

    def test_metadata_present(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "get_recording_info")
        result = json.loads(fn(file="session_001.mcap"))
        assert "session_info" in result["metadata"]
        assert result["metadata"]["session_info"]["session_id"] == "test-001"

    def test_multi_topic_info(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "get_recording_info")
        result = json.loads(fn(file="session_002.mcap"))
        assert "/imu" in result["channels"]
        assert "/cmd_vel" in result["channels"]
        assert "hardware" in result["metadata"]

    def test_attachments_field(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "get_recording_info")
        result = json.loads(fn(file="session_001.mcap"))
        assert "attachments" in result
        assert isinstance(result["attachments"], list)

    def test_file_not_found(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "get_recording_info")
        with pytest.raises(FileNotFoundError):
            fn(file="nonexistent.mcap")


# ---- load_recording extras ----

class TestLoadRecordingExtras:
    def test_memory_mb_in_response(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(load_fn(file="session_001.mcap"))
        assert "memory_mb" in result
        assert isinstance(result["memory_mb"], (int, float))
        assert result["memory_mb"] >= 0

    def test_downsample(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(load_fn(file="session_001.mcap", downsample=10))
        assert result["tables"]["battery"]["rows"] == 10

    def test_time_range_filter_iso(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        # Fixture base time is 1_700_000_000s = 2023-11-14T22:13:20Z
        # 100 msgs at 20ms intervals = 2s window
        result = json.loads(load_fn(
            file="session_001.mcap",
            start_time="2023-11-14T22:13:20Z",
            end_time="2023-11-14T22:13:21Z",
        ))
        assert result["tables"]["battery"]["rows"] < 100
        assert result["tables"]["battery"]["rows"] > 0

    def test_skipped_reason_when_no_skips(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        result = json.loads(load_fn(file="session_001.mcap"))
        assert result["skipped_reason"] is None
        assert result["skipped_topics"] == []


# ---- query format ----

class TestQueryFormats:
    def test_csv_format(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")
        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(
            sql="SELECT voltage FROM battery LIMIT 2", format="csv"
        ))
        assert "data" in result
        assert "voltage" in result["data"]

    def test_json_format(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")
        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(
            sql="SELECT voltage FROM battery LIMIT 2", format="json"
        ))
        assert "data" in result
        assert isinstance(result["data"], list)

    def test_query_with_limit_override(self, mcp_server):
        load_fn = _get_tool_fn(mcp_server, "load_recording")
        load_fn(file="session_001.mcap")
        query_fn = _get_tool_fn(mcp_server, "query")
        result = json.loads(query_fn(sql="SELECT * FROM battery", limit=3))
        assert result["row_count"] == 3


# ---- Helper unit tests ----

class TestJsonDefault:
    def test_decimal(self):
        assert _json_default(decimal.Decimal("3.14")) == 3.14

    def test_bytes(self):
        assert _json_default(b"\xde\xad") == "dead"

    def test_bytearray(self):
        assert _json_default(bytearray(b"\xca\xfe")) == "cafe"

    def test_datetime(self):
        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = _json_default(dt)
        assert "2024" in result

    def test_fallback_str(self):
        assert _json_default(object()) is not None


class TestParseDatetime:
    def test_none(self):
        assert _parse_datetime(None) is None

    def test_empty(self):
        assert _parse_datetime("") is None

    def test_valid_iso(self):
        result = _parse_datetime("2024-01-15T00:00:00Z")
        assert result is not None

    def test_invalid_format(self):
        assert _parse_datetime("not a date") is None


class TestParseTimeToNs:
    def test_none(self):
        assert _parse_time_to_ns(None) is None

    def test_integer_microseconds(self):
        result = _parse_time_to_ns("1000000")
        assert result == 1000000 * 1000

    def test_iso_string(self):
        result = _parse_time_to_ns("2024-01-15T00:00:00Z")
        assert result is not None
        assert result > 0

    def test_iso_string_no_tz(self):
        result = _parse_time_to_ns("2024-01-15T00:00:00")
        assert result is not None

    def test_invalid_returns_none(self):
        assert _parse_time_to_ns("not valid") is None


class TestResolveFile:
    def test_absolute_path(self, simple_mcap: Path):
        result = _resolve_file(str(simple_mcap), simple_mcap.parent)
        assert result == simple_mcap

    def test_relative_to_data_dir(self, simple_mcap: Path):
        result = _resolve_file(simple_mcap.name, simple_mcap.parent)
        assert result == simple_mcap

    def test_recursive_search(self, tmp_path: Path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        mcap = subdir / "deep.mcap"
        from tests.conftest import create_simple_mcap
        create_simple_mcap(mcap, num_messages=5)
        result = _resolve_file("deep.mcap", tmp_path)
        assert result == mcap

    def test_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            _resolve_file("missing.mcap", tmp_path)
