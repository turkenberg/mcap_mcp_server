"""Tests for the Protobuf decoder."""

import json
from typing import Any

import pytest

try:
    from google.protobuf.compiler.plugin_pb2 import CodeGeneratorRequest
    from google.protobuf.descriptor_pb2 import (
        DescriptorProto,
        FieldDescriptorProto,
        FileDescriptorProto,
        FileDescriptorSet,
    )

    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False

pytestmark = pytest.mark.skipif(not PROTOBUF_AVAILABLE, reason="protobuf not installed")


def _make_simple_fds(msg_name: str = "BatteryState") -> bytes:
    """Build a FileDescriptorSet with a simple message for testing."""
    field_voltage = FieldDescriptorProto(
        name="voltage",
        number=1,
        type=FieldDescriptorProto.TYPE_DOUBLE,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
    )
    field_current = FieldDescriptorProto(
        name="current",
        number=2,
        type=FieldDescriptorProto.TYPE_DOUBLE,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
    )
    field_active = FieldDescriptorProto(
        name="active",
        number=3,
        type=FieldDescriptorProto.TYPE_BOOL,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
    )

    msg_desc = DescriptorProto(
        name=msg_name,
        field=[field_voltage, field_current, field_active],
    )

    file_desc = FileDescriptorProto(
        name="test.proto",
        package="test",
        message_type=[msg_desc],
        syntax="proto3",
    )

    fds = FileDescriptorSet(file=[file_desc])
    return fds.SerializeToString()


class TestProtobufDecoder:
    def test_can_decode(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        assert dec.can_decode("protobuf", "protobuf")
        assert not dec.can_decode("json", "jsonschema")
        assert not dec.can_decode("cdr", "ros2msg")

    def test_get_field_info(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        schema_data = _make_simple_fds()
        fields = dec.get_field_info(schema_data, "protobuf")
        names = {f.name for f in fields}
        assert "voltage" in names
        assert "current" in names
        assert "active" in names

        voltage = next(f for f in fields if f.name == "voltage")
        assert voltage.type == "DOUBLE"
        active = next(f for f in fields if f.name == "active")
        assert active.type == "BOOLEAN"

    def test_get_field_info_empty_schema(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        assert dec.get_field_info(b"", "protobuf") == []

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        assert dec.get_field_info(b"data", "json") == []

    def test_decode_roundtrip(self):
        """Encode a protobuf message, write it to MCAP, decode it back."""
        from google.protobuf.descriptor_pool import DescriptorPool
        from google.protobuf.descriptor_pb2 import FileDescriptorSet
        from google.protobuf.message_factory import GetMessageClassesForFiles

        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        schema_data = _make_simple_fds()
        fds = FileDescriptorSet.FromString(schema_data)
        pool = DescriptorPool()
        for fd in fds.file:
            pool.Add(fd)

        classes = GetMessageClassesForFiles([fd.name for fd in fds.file], pool)
        msg_cls = classes["test.BatteryState"]

        msg = msg_cls()
        msg.voltage = 23.5
        msg.current = -1.2
        msg.active = True
        encoded = msg.SerializeToString()

        dec = ProtobufDecoder()
        result = dec.decode(
            schema_data,
            encoded,
            schema_name="test.BatteryState",
            schema_encoding="protobuf",
            schema_id=1,
        )
        assert result["voltage"] == 23.5
        assert result["current"] == pytest.approx(-1.2)
        assert result["active"] is True
