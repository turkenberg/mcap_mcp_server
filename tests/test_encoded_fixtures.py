"""End-to-end tests for real encoded MCAP fixtures (protobuf, ROS 1, ROS 2, FlatBuffers).

Each test verifies the full pipeline: MCAP file → summary → schema → load → SQL query.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcap_mcp_server.config import ServerConfig
from mcap_mcp_server.server import create_server

try:
    import google.protobuf  # noqa: F401

    _HAS_PROTOBUF = True
except ImportError:
    _HAS_PROTOBUF = False

try:
    import mcap_ros1  # noqa: F401

    _HAS_ROS1 = True
except ImportError:
    _HAS_ROS1 = False

try:
    import mcap_ros2  # noqa: F401

    _HAS_ROS2 = True
except ImportError:
    _HAS_ROS2 = False

try:
    import flatbuffers  # noqa: F401

    _HAS_FLATBUFFERS = True
except ImportError:
    _HAS_FLATBUFFERS = False


def _get_tool_fn(server, name: str):
    for tool in server._tool_manager._tools.values():
        if tool.name == name:
            return tool.fn
    raise ValueError(f"Tool {name!r} not found")


def _make_server(mcap_path: Path):
    config = ServerConfig(data_dir=mcap_path.parent)
    return create_server(config)


# ---------------------------------------------------------------------------
# Protobuf
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_PROTOBUF, reason="protobuf not installed")
class TestProtobufMcap:
    def test_summary(self, protobuf_mcap: Path):
        from mcap_mcp_server.mcap_reader import get_summary

        s = get_summary(protobuf_mcap)
        assert s.message_count == 50
        assert len(s.channels) == 1
        assert s.channels[0].topic == "/battery"
        assert s.channels[0].message_encoding == "protobuf"
        assert s.channels[0].schema_encoding == "protobuf"

    def test_schema_info(self, protobuf_mcap: Path):
        from mcap_mcp_server.decoder_registry import DecoderRegistry
        from mcap_mcp_server.mcap_reader import get_schema_info

        info = get_schema_info(protobuf_mcap, DecoderRegistry())
        assert "/battery" in info
        field_names = [f.name for f in info["/battery"].fields]
        assert "timestamp_us" in field_names
        assert "voltage" in field_names
        assert "current" in field_names
        assert "percentage" in field_names

    def test_load_and_query(self, protobuf_mcap: Path):
        server = _make_server(protobuf_mcap)
        load = _get_tool_fn(server, "load_recording")
        query = _get_tool_fn(server, "query")

        result = json.loads(load(file=protobuf_mcap.name))
        assert result["status"] == "loaded"
        assert "battery" in result["tables"]
        assert result["tables"]["battery"]["rows"] == 50

        qr = json.loads(query(sql="SELECT voltage, current FROM battery LIMIT 3"))
        assert qr["row_count"] == 3
        assert abs(qr["rows"][0][0] - 24.0) < 0.01
        assert abs(qr["rows"][0][1] - (-2.0)) < 0.01


# ---------------------------------------------------------------------------
# ROS 1
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_ROS1, reason="mcap-ros1-support not installed")
class TestRos1Mcap:
    def test_summary(self, ros1_mcap: Path):
        from mcap_mcp_server.mcap_reader import get_summary

        s = get_summary(ros1_mcap)
        assert s.message_count == 50
        assert s.channels[0].message_encoding == "ros1"
        assert s.channels[0].schema_encoding == "ros1msg"

    def test_schema_info(self, ros1_mcap: Path):
        from mcap_mcp_server.decoder_registry import DecoderRegistry
        from mcap_mcp_server.mcap_reader import get_schema_info

        info = get_schema_info(ros1_mcap, DecoderRegistry())
        assert "/battery" in info
        field_names = [f.name for f in info["/battery"].fields]
        assert "timestamp_us" in field_names
        assert "voltage" in field_names

    def test_load_and_query(self, ros1_mcap: Path):
        server = _make_server(ros1_mcap)
        load = _get_tool_fn(server, "load_recording")
        query = _get_tool_fn(server, "query")

        result = json.loads(load(file=ros1_mcap.name))
        assert result["status"] == "loaded"
        assert result["tables"]["battery"]["rows"] == 50

        qr = json.loads(query(sql="SELECT voltage, percentage FROM battery LIMIT 1"))
        assert qr["row_count"] == 1
        assert abs(qr["rows"][0][0] - 24.0) < 0.01
        assert abs(qr["rows"][0][1] - 1.0) < 0.01


# ---------------------------------------------------------------------------
# ROS 2
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_ROS2, reason="mcap-ros2-support not installed")
class TestRos2Mcap:
    def test_summary(self, ros2_mcap: Path):
        from mcap_mcp_server.mcap_reader import get_summary

        s = get_summary(ros2_mcap)
        assert s.message_count == 50
        assert s.channels[0].message_encoding == "cdr"
        assert s.channels[0].schema_encoding == "ros2msg"

    def test_schema_info(self, ros2_mcap: Path):
        from mcap_mcp_server.decoder_registry import DecoderRegistry
        from mcap_mcp_server.mcap_reader import get_schema_info

        info = get_schema_info(ros2_mcap, DecoderRegistry())
        assert "/battery" in info
        field_names = [f.name for f in info["/battery"].fields]
        assert "timestamp_us" in field_names
        assert "voltage" in field_names

    def test_load_and_query(self, ros2_mcap: Path):
        server = _make_server(ros2_mcap)
        load = _get_tool_fn(server, "load_recording")
        query = _get_tool_fn(server, "query")

        result = json.loads(load(file=ros2_mcap.name))
        assert result["status"] == "loaded"
        assert result["tables"]["battery"]["rows"] == 50

        qr = json.loads(query(sql="SELECT voltage, current FROM battery LIMIT 1"))
        assert qr["row_count"] == 1
        assert abs(qr["rows"][0][0] - 24.0) < 0.01
        assert abs(qr["rows"][0][1] - (-2.0)) < 0.01


# ---------------------------------------------------------------------------
# FlatBuffers
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_FLATBUFFERS, reason="flatbuffers not installed")
class TestFlatBufferMcap:
    def test_summary(self, flatbuffer_mcap: Path):
        from mcap_mcp_server.mcap_reader import get_summary

        s = get_summary(flatbuffer_mcap)
        assert s.message_count == 50
        assert s.channels[0].message_encoding == "flatbuffer"
        assert s.channels[0].schema_encoding == "flatbuffer"

    def test_schema_info(self, flatbuffer_mcap: Path):
        from mcap_mcp_server.decoder_registry import DecoderRegistry
        from mcap_mcp_server.mcap_reader import get_schema_info

        info = get_schema_info(flatbuffer_mcap, DecoderRegistry())
        assert "/battery" in info
        field_names = [f.name for f in info["/battery"].fields]
        assert "timestamp_us" in field_names
        assert "voltage" in field_names or "current" in field_names

    def test_load_and_query(self, flatbuffer_mcap: Path):
        server = _make_server(flatbuffer_mcap)
        load = _get_tool_fn(server, "load_recording")
        query = _get_tool_fn(server, "query")

        result = json.loads(load(file=flatbuffer_mcap.name))
        assert result["status"] == "loaded"
        assert result["tables"]["battery"]["rows"] == 50

        qr = json.loads(query(sql="SELECT voltage, current FROM battery LIMIT 1"))
        assert qr["row_count"] == 1
        assert abs(qr["rows"][0][0] - 24.0) < 0.01
        assert abs(qr["rows"][0][1] - (-2.0)) < 0.01


# ---------------------------------------------------------------------------
# Cross-encoding: all decoders produce consistent schema
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not all([_HAS_PROTOBUF, _HAS_ROS1, _HAS_ROS2, _HAS_FLATBUFFERS]),
    reason="requires all optional decoder packages",
)
class TestCrossEncodingConsistency:
    """Verify that the same logical message produces queryable tables
    regardless of the encoding format."""

    def test_all_encodings_produce_battery_table(
        self,
        protobuf_mcap: Path,
        ros1_mcap: Path,
        ros2_mcap: Path,
        flatbuffer_mcap: Path,
    ):
        for mcap_path in [protobuf_mcap, ros1_mcap, ros2_mcap, flatbuffer_mcap]:
            server = _make_server(mcap_path)
            load = _get_tool_fn(server, "load_recording")
            query = _get_tool_fn(server, "query")

            result = json.loads(load(file=mcap_path.name))
            assert result["status"] == "loaded", f"Failed for {mcap_path.name}"
            assert "battery" in result["tables"], f"No battery table for {mcap_path.name}"

            qr = json.loads(
                query(sql="SELECT COUNT(*) AS cnt FROM battery")
            )
            assert qr["rows"][0][0] == 50, f"Wrong count for {mcap_path.name}"

    def test_all_encodings_have_timestamp(
        self,
        protobuf_mcap: Path,
        ros1_mcap: Path,
        ros2_mcap: Path,
        flatbuffer_mcap: Path,
    ):
        from mcap_mcp_server.decoder_registry import DecoderRegistry
        from mcap_mcp_server.mcap_reader import get_schema_info

        reg = DecoderRegistry()
        for mcap_path in [protobuf_mcap, ros1_mcap, ros2_mcap, flatbuffer_mcap]:
            info = get_schema_info(mcap_path, reg)
            assert "/battery" in info, f"Missing /battery in {mcap_path.name}"
            field_names = [f.name for f in info["/battery"].fields]
            assert "timestamp_us" in field_names, f"No timestamp_us in {mcap_path.name}"
