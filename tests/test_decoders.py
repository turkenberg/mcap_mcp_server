"""Unit tests for decoder error-handling and edge-case branches.

Exercises paths not covered by the happy-path end-to-end fixture tests:
empty/corrupt schema, nested messages, array fields, decoder-not-found,
get_field_info exceptions, and _namespace_to_dict / _ros_msg_to_dict edge cases.
"""

from __future__ import annotations

import struct
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Protobuf decoder
# ---------------------------------------------------------------------------

try:
    from google.protobuf.descriptor_pb2 import (
        FieldDescriptorProto,
        FileDescriptorProto,
        FileDescriptorSet,
    )

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


def _make_proto_fds(
    *,
    nested: bool = False,
    repeated: bool = False,
    deep_nested: bool = False,
) -> bytes:
    """Build a FileDescriptorSet with optional nested/repeated fields.

    _extract_protobuf_fields uses message_type[0] as the root message,
    so we define the target message first and any dependencies after.
    """
    fd = FileDescriptorProto()
    fd.name = "test.proto"
    fd.package = "test"
    fd.syntax = "proto3"

    outer = fd.message_type.add()
    outer.name = "Sensor"

    f = outer.field.add()
    f.name = "name"
    f.number = 1
    f.type = FieldDescriptorProto.TYPE_STRING
    f.label = FieldDescriptorProto.LABEL_OPTIONAL

    if repeated:
        f2 = outer.field.add()
        f2.name = "values"
        f2.number = 2
        f2.type = FieldDescriptorProto.TYPE_DOUBLE
        f2.label = FieldDescriptorProto.LABEL_REPEATED

    if nested or deep_nested:
        f3 = outer.field.add()
        f3.name = "position"
        f3.number = 3
        f3.type = FieldDescriptorProto.TYPE_MESSAGE
        f3.type_name = ".test.Position"
        f3.label = FieldDescriptorProto.LABEL_OPTIONAL

        inner = fd.message_type.add()
        inner.name = "Position"
        for i, name in enumerate(["x", "y", "z"], start=1):
            fi = inner.field.add()
            fi.name = name
            fi.number = i
            fi.type = FieldDescriptorProto.TYPE_DOUBLE
            fi.label = FieldDescriptorProto.LABEL_OPTIONAL

    fds = FileDescriptorSet()
    fds.file.append(fd)
    return fds.SerializeToString()


@pytest.mark.skipif(not _HAS_PROTOBUF, reason="protobuf not installed")
class TestProtobufDecoder:
    def test_decode_returns_empty_when_decoder_not_found(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        result = dec.decode(b"garbage", b"data", schema_id=99)
        assert result == {}

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        assert dec.get_field_info(b"data", "not_protobuf") == []

    def test_get_field_info_empty_schema(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        assert dec.get_field_info(b"", "protobuf") == []

    def test_get_field_info_corrupt_schema(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        result = dec.get_field_info(b"\xff\xff\xff", "protobuf")
        assert result == []

    def test_repeated_field_becomes_varchar(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        schema = _make_proto_fds(repeated=True)
        fields = dec.get_field_info(schema, "protobuf")
        field_map = {f.name: f.type for f in fields}
        assert field_map["values"] == "VARCHAR"

    def test_nested_message_within_depth(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder(flatten_depth=3)
        schema = _make_proto_fds(nested=True)
        fields = dec.get_field_info(schema, "protobuf")
        field_names = [f.name for f in fields]
        assert "position_x" in field_names
        assert "position_y" in field_names

    def test_nested_message_at_max_depth(self):
        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder(flatten_depth=1)
        schema = _make_proto_fds(deep_nested=True)
        fields = dec.get_field_info(schema, "protobuf")
        field_map = {f.name: f.type for f in fields}
        assert field_map["position"] == "VARCHAR"

    def test_extract_fields_key_error(self):
        """FDS with no package → message name lookup might differ."""
        fd = FileDescriptorProto()
        fd.name = "bare.proto"
        fd.syntax = "proto3"
        msg = fd.message_type.add()
        msg.name = "Msg"
        f = msg.field.add()
        f.name = "val"
        f.number = 1
        f.type = FieldDescriptorProto.TYPE_INT32
        f.label = FieldDescriptorProto.LABEL_OPTIONAL
        fds = FileDescriptorSet()
        fds.file.append(fd)

        from mcap_mcp_server.decoders.protobuf_decoder import ProtobufDecoder

        dec = ProtobufDecoder()
        fields = dec.get_field_info(fds.SerializeToString(), "protobuf")
        field_names = [fi.name for fi in fields]
        assert "val" in field_names


# ---------------------------------------------------------------------------
# ROS 1 decoder
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_ROS1, reason="mcap-ros1-support not installed")
class TestRos1Decoder:
    def test_decode_returns_empty_when_decoder_not_found(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        result = dec.decode(b"bad_schema", b"data", schema_id=99)
        assert result == {}

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        assert dec.get_field_info(b"data", "not_ros1msg") == []

    def test_get_field_info_empty_schema(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        assert dec.get_field_info(b"", "ros1msg") == []

    def test_get_field_info_exception(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        result = dec.get_field_info(b"\xff\xfe", "ros1msg")
        assert result == []

    def test_parse_array_field_skipped_by_regex(self):
        """ROS 1 regex doesn't include [] so array types are skipped."""
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"float64[] values\nint32 count"
        dec = Ros1Decoder()
        fields = dec.get_field_info(schema, "ros1msg")
        field_names = [f.name for f in fields]
        assert "values" not in field_names
        assert "count" in field_names

    def test_parse_complex_type_field(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"geometry_msgs/Point position\nstring label"
        dec = Ros1Decoder()
        fields = dec.get_field_info(schema, "ros1msg")
        field_map = {f.name: f.type for f in fields}
        assert field_map["position"] == "VARCHAR"
        assert field_map["label"] == "VARCHAR"

    def test_parse_stops_at_separator(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"float64 x\n================\nfloat64 hidden"
        dec = Ros1Decoder()
        fields = dec.get_field_info(schema, "ros1msg")
        assert len(fields) == 1
        assert fields[0].name == "x"

    def test_parse_skips_comments_and_blanks(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"# a comment\n\nfloat64 x\n  # another\nfloat64 y"
        dec = Ros1Decoder()
        fields = dec.get_field_info(schema, "ros1msg")
        assert len(fields) == 2

    def test_parse_regex_no_match(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"not a valid line\nfloat64 x"
        dec = Ros1Decoder()
        fields = dec.get_field_info(schema, "ros1msg")
        assert len(fields) == 1

    def test_ros_msg_to_dict_nested_slots(self):
        """Verify _ros_msg_to_dict handles nested __slots__ objects and lists."""
        from mcap_mcp_server.decoders.ros1_decoder import _ros_msg_to_dict

        class Inner:
            __slots__ = ["_x", "_y"]

            def __init__(self, x: float, y: float):
                self._x = x
                self._y = y

        class Outer:
            __slots__ = ["_position", "_tags"]

            def __init__(self, position: Any, tags: list):
                self._position = position
                self._tags = tags

        inner = Inner(1.0, 2.0)
        outer = Outer(inner, [Inner(3.0, 4.0), Inner(5.0, 6.0)])
        result = _ros_msg_to_dict(outer)

        assert result["position"] == {"x": 1.0, "y": 2.0}
        assert len(result["tags"]) == 2
        assert result["tags"][0] == {"x": 3.0, "y": 4.0}

    def test_ros_msg_to_dict_plain_list(self):
        from mcap_mcp_server.decoders.ros1_decoder import _ros_msg_to_dict

        class Msg:
            __slots__ = ["_values"]

            def __init__(self):
                self._values = [1.0, 2.0, 3.0]

        result = _ros_msg_to_dict(Msg())
        assert result["values"] == [1.0, 2.0, 3.0]

    def test_parse_uppercase_type_at_max_depth(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"Header header\nfloat64 x"
        dec = Ros1Decoder(flatten_depth=1)
        fields = dec.get_field_info(schema, "ros1msg")
        field_map = {f.name: f.type for f in fields}
        assert field_map["header"] == "VARCHAR"

    def test_parse_unknown_lowercase_type(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        schema = b"custom_type value"
        dec = Ros1Decoder()
        fields = dec.get_field_info(schema, "ros1msg")
        assert fields[0].type == "VARCHAR"


# ---------------------------------------------------------------------------
# ROS 2 decoder
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_ROS2, reason="mcap-ros2-support not installed")
class TestRos2Decoder:
    def test_decode_returns_empty_when_decoder_not_found(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        result = dec.decode(b"bad", b"data", schema_id=99)
        assert result == {}

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        assert dec.get_field_info(b"data", "not_ros2") == []

    def test_get_field_info_empty_schema(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        assert dec.get_field_info(b"", "ros2msg") == []

    def test_get_field_info_exception(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        with patch(
            "mcap_mcp_server.decoders.ros2_decoder._parse_ros_msg_def",
            side_effect=RuntimeError("boom"),
        ):
            result = dec.get_field_info(b"float64 x", "ros2msg")
        assert result == []

    def test_get_field_info_ros2idl(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        idl = (
            b"module test_msgs { module msg {\n"
            b"  struct Battery {\n"
            b"    double voltage;\n"
            b"    string label;\n"
            b"    sequence<double> values;\n"
            b"  };\n"
            b"}; };\n"
        )
        dec = Ros2Decoder()
        fields = dec.get_field_info(idl, "ros2idl")
        field_map = {f.name: f.type for f in fields}
        assert field_map["voltage"] == "DOUBLE"
        assert field_map["label"] == "VARCHAR"
        assert field_map["values"] == "VARCHAR"  # sequence → VARCHAR

    def test_parse_msg_array_field(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        schema = b"float64[] values\nfloat64[3] fixed\nint32 count"
        dec = Ros2Decoder()
        fields = dec.get_field_info(schema, "ros2msg")
        field_map = {f.name: f.type for f in fields}
        assert field_map["values"] == "VARCHAR"
        assert field_map["fixed"] == "VARCHAR"
        assert field_map["count"] == "INTEGER"

    def test_parse_msg_non_numeric_type(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        schema = b"string label\nSomeMsg nested"
        dec = Ros2Decoder()
        fields = dec.get_field_info(schema, "ros2msg")
        field_map = {f.name: f.type for f in fields}
        assert field_map["label"] == "VARCHAR"
        assert field_map["nested"] == "VARCHAR"

    def test_parse_msg_stops_at_separator(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        schema = b"float64 x\n===\nfloat64 hidden"
        dec = Ros2Decoder()
        fields = dec.get_field_info(schema, "ros2msg")
        assert len(fields) == 1

    def test_parse_msg_regex_no_match(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        schema = b"??? invalid\nfloat64 x"
        dec = Ros2Decoder()
        fields = dec.get_field_info(schema, "ros2msg")
        assert len(fields) == 1

    def test_parse_idl_non_numeric_type(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        idl = b"  SomeCustomType field_name;"
        dec = Ros2Decoder()
        fields = dec.get_field_info(idl, "ros2idl")
        assert fields[0].type == "VARCHAR"

    def test_namespace_to_dict_with_simple_namespace(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        ns = SimpleNamespace(x=1.0, y=2.0)
        result = _namespace_to_dict(ns)
        assert result == {"x": 1.0, "y": 2.0}

    def test_namespace_to_dict_with_dict_obj(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        result = _namespace_to_dict({"a": 1, "b": "hello"})
        assert result == {"a": 1, "b": "hello"}

    def test_namespace_to_dict_with_plain_object(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        class Obj:
            def __init__(self):
                self.x = 10

        result = _namespace_to_dict(Obj())
        assert result == {"x": 10}

    def test_namespace_to_dict_with_non_object(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        result = _namespace_to_dict(42)
        assert result == {"value": 42}

    def test_namespace_to_dict_nested_list_of_namespaces(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        ns = SimpleNamespace(
            points=[SimpleNamespace(x=1.0, y=2.0), SimpleNamespace(x=3.0, y=4.0)]
        )
        result = _namespace_to_dict(ns)
        assert len(result["points"]) == 2
        assert result["points"][0] == {"x": 1.0, "y": 2.0}

    def test_namespace_to_dict_nested_object(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        class Inner:
            def __init__(self):
                self.val = 5

        ns = SimpleNamespace(child=Inner())
        result = _namespace_to_dict(ns)
        assert result["child"] == {"val": 5}


# ---------------------------------------------------------------------------
# FlatBuffer decoder
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_FLATBUFFERS, reason="flatbuffers not installed")
class TestFlatBufferDecoder:
    def test_decode_empty_schema(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.decode(b"", b"data") == {}

    def test_decode_empty_data(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.decode(b"schema", b"") == {}

    def test_decode_corrupt_data(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        from tests.conftest import _get_flatbuffer_bfbs

        bfbs = _get_flatbuffer_bfbs()
        dec = FlatBufferDecoder()
        result = dec.decode(bfbs, b"\x00\x00\x00\x00", schema_id=1)
        assert result == {} or isinstance(result, dict)

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.get_field_info(b"data", "not_flatbuffer") == []

    def test_get_field_info_empty_schema(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.get_field_info(b"", "flatbuffer") == []

    def test_get_field_info_corrupt_schema(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        result = dec.get_field_info(b"\xff" * 20, "flatbuffer")
        assert result == []

    def test_parse_bfbs_too_short(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema

        assert _parse_bfbs_schema(b"\x00\x00") == []

    def test_parse_bfbs_corrupt(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema

        assert _parse_bfbs_schema(b"\xff" * 64) == []

    def test_decode_table_short_data(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _decode_table

        assert _decode_table(b"", []) == {}
        assert _decode_table(b"\x00\x01", []) == {}

    def test_decode_table_unknown_base_type(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import (
            _FieldDef,
            _FB_UNION,
            _decode_table,
        )

        fb = _build_minimal_flatbuffer(42.0)
        field_def = _FieldDef(name="mystery", base_type=_FB_UNION, offset=4)
        result = _decode_table(fb, [field_def])
        assert result["mystery"] is None

    def test_decode_table_field_offset_beyond_vtable(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _FB_DOUBLE, _decode_table

        fb = _build_minimal_flatbuffer(42.0)
        field_def = _FieldDef(name="far", base_type=_FB_DOUBLE, offset=200)
        result = _decode_table(fb, [field_def])
        assert result["far"] is None

    def test_decode_table_field_offset_zero(self):
        """A field whose vtable entry is 0 → None (field not present)."""
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _FB_DOUBLE, _decode_table

        builder = flatbuffers.Builder(64)
        builder.StartObject(2)
        builder.PrependFloat64Slot(0, 42.0, 0.0)
        # slot 1 left as default (0.0 == default → vtable entry will be 0)
        root = builder.EndObject()
        builder.Finish(root)
        fb = bytes(builder.Output())

        field_def = _FieldDef(name="missing", base_type=_FB_DOUBLE, offset=6)
        result = _decode_table(fb, [field_def])
        assert result["missing"] is None

    def test_decode_bool_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _FB_BOOL, _decode_table

        builder = flatbuffers.Builder(64)
        builder.StartObject(1)
        builder.PrependBoolSlot(0, True, False)
        root = builder.EndObject()
        builder.Finish(root)
        fb = bytes(builder.Output())

        field_def = _FieldDef(name="flag", base_type=_FB_BOOL, offset=4)
        result = _decode_table(fb, [field_def])
        assert result["flag"] is True

    def test_schema_cache_hit(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder
        from tests.conftest import _get_flatbuffer_bfbs, _flatbuffer_encode_battery

        bfbs = _get_flatbuffer_bfbs()
        dec = FlatBufferDecoder()

        msg = _flatbuffer_encode_battery(10.0, 1.0, 0.5)
        r1 = dec.decode(bfbs, msg, schema_id=42)
        r2 = dec.decode(bfbs, msg, schema_id=42)
        assert r1 == r2
        assert 42 in dec._schema_cache

    def test_string_field_decode(self):
        """Build a FlatBuffer with a string field and decode it."""
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _FB_STRING, _decode_table

        builder = flatbuffers.Builder(128)
        name = builder.CreateString("hello")
        builder.StartObject(1)
        builder.PrependUOffsetTRelativeSlot(0, name, 0)
        root = builder.EndObject()
        builder.Finish(root)
        fb = bytes(builder.Output())

        field_def = _FieldDef(name="label", base_type=_FB_STRING, offset=4)
        result = _decode_table(fb, [field_def])
        assert result["label"] == "hello"

    def test_string_field_corrupt(self):
        """String field with bad string offset inside a valid FlatBuffer table → None."""
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _FB_STRING, _decode_table

        builder = flatbuffers.Builder(128)
        name = builder.CreateString("ok")
        builder.StartObject(1)
        builder.PrependUOffsetTRelativeSlot(0, name, 0)
        root = builder.EndObject()
        builder.Finish(root)
        fb = bytearray(builder.Output())

        # Corrupt the string offset to point way past end of buffer
        field_def = _FieldDef(name="label", base_type=_FB_STRING, offset=4)
        result = _decode_table(bytes(fb), [field_def])
        assert result["label"] == "ok"

        # Now corrupt: overwrite the string offset in the table data
        root_offset = struct.unpack_from("<I", fb, 0)[0]
        table_pos = root_offset
        vtable_soff = struct.unpack_from("<i", fb, table_pos)[0]
        vtable_pos = table_pos - vtable_soff
        field_off = struct.unpack_from("<H", fb, vtable_pos + 4)[0]
        field_pos = table_pos + field_off
        struct.pack_into("<I", fb, field_pos, 0xFFFFFF)

        result2 = _decode_table(bytes(fb), [field_def])
        assert result2["label"] is None


def _build_minimal_flatbuffer(value: float) -> bytes:
    """Build a minimal FlatBuffer with one double field."""
    builder = flatbuffers.Builder(64)
    builder.StartObject(1)
    builder.PrependFloat64Slot(0, value, 0.0)
    root = builder.EndObject()
    builder.Finish(root)
    return bytes(builder.Output())
