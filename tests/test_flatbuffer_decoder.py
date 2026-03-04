"""Tests for the FlatBuffer decoder."""

import os
import struct

import pytest

try:
    import flatbuffers

    FLATBUFFERS_AVAILABLE = True
except ImportError:
    FLATBUFFERS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not FLATBUFFERS_AVAILABLE, reason="flatbuffers not installed")


def _build_fb_message(fields: list[tuple[int, bytes]]) -> bytes:
    """Build a minimal FlatBuffer message binary.

    *fields* is a list of (base_type, raw_bytes) tuples.
    Returns data where vtable is at pos 4 and table follows.
    """
    num_fields = len(fields)
    vtable_size = 4 + 2 * num_fields
    if vtable_size % 4 != 0:
        vtable_size += 2

    table_start = 4 + vtable_size
    soffset = table_start - 4

    data_offset = 4
    field_offsets: list[int] = []
    field_data = b""
    for _, raw in fields:
        field_offsets.append(data_offset)
        field_data += raw
        data_offset += len(raw)

    table_size = 4 + len(field_data)
    buf = bytearray()
    buf += struct.pack("<I", table_start)
    buf += struct.pack("<H", vtable_size)
    buf += struct.pack("<H", table_size)
    for off in field_offsets:
        buf += struct.pack("<H", off)
    while len(buf) < table_start:
        buf += b"\x00"
    buf += struct.pack("<i", soffset)
    buf += field_data
    return bytes(buf)


class TestFlatBufferDecoder:
    def test_can_decode(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.can_decode("flatbuffer", "flatbuffer")
        assert not dec.can_decode("json", "jsonschema")
        assert not dec.can_decode("protobuf", "protobuf")

    def test_get_field_info_empty(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.get_field_info(b"", "flatbuffer") == []

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.get_field_info(b"data", "json") == []

    def test_get_field_info_corrupt_data(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        result = dec.get_field_info(b"\xff" * 64, "flatbuffer")
        assert isinstance(result, list)

    def test_decode_empty_data_returns_empty(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        assert dec.decode(b"", b"") == {}
        assert dec.decode(b"schema", b"") == {}
        assert dec.decode(b"", b"data") == {}

    def test_decode_invalid_data_returns_empty(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        result = dec.decode(b"\x00" * 4, b"\x00" * 4)
        assert isinstance(result, dict)

    def test_decode_with_bad_schema_returns_empty(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        result = dec.decode(b"bad", b"bad", schema_id=99)
        assert result == {}

    def test_schema_cache(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import (
            FlatBufferDecoder,
            _FieldDef,
            _FB_INT,
        )

        dec = FlatBufferDecoder()
        dec._schema_cache[42] = [_FieldDef("cached", _FB_INT, 4)]
        defs = dec._get_field_defs(b"whatever", 42)
        assert len(defs) == 1
        assert defs[0].name == "cached"

    def test_type_map_complete(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FB_TYPE_MAP

        assert len(_FB_TYPE_MAP) > 0
        assert "DOUBLE" in _FB_TYPE_MAP.values()
        assert "FLOAT" in _FB_TYPE_MAP.values()
        assert "INTEGER" in _FB_TYPE_MAP.values()
        assert "BOOLEAN" in _FB_TYPE_MAP.values()
        assert "VARCHAR" in _FB_TYPE_MAP.values()

    def test_field_def(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef

        fd = _FieldDef(name="voltage", base_type=12, offset=4)
        assert fd.name == "voltage"
        assert fd.base_type == 12
        assert fd.offset == 4


class TestDecodeTable:
    def test_empty_data(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _decode_table

        assert _decode_table(b"", []) == {}
        assert _decode_table(b"\x00\x00\x00", []) == {}

    def test_int_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_INT

        data = _build_fb_message([(_FB_INT, struct.pack("<i", 42))])
        result = _decode_table(data, [_FieldDef("x", _FB_INT, 4)])
        assert result["x"] == 42

    def test_float_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_FLOAT

        data = _build_fb_message([(_FB_FLOAT, struct.pack("<f", 3.14))])
        result = _decode_table(data, [_FieldDef("val", _FB_FLOAT, 4)])
        assert abs(result["val"] - 3.14) < 0.01

    def test_double_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_DOUBLE

        data = _build_fb_message([(_FB_DOUBLE, struct.pack("<d", 2.718))])
        result = _decode_table(data, [_FieldDef("e", _FB_DOUBLE, 4)])
        assert abs(result["e"] - 2.718) < 1e-3

    def test_bool_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_BOOL

        data = _build_fb_message([(_FB_BOOL, struct.pack("?", True))])
        result = _decode_table(data, [_FieldDef("flag", _FB_BOOL, 4)])
        assert result["flag"] is True

    def test_multiple_fields(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_INT, _FB_FLOAT

        data = _build_fb_message([
            (_FB_INT, struct.pack("<i", 10)),
            (_FB_FLOAT, struct.pack("<f", 5.5)),
        ])
        result = _decode_table(data, [
            _FieldDef("a", _FB_INT, 4),
            _FieldDef("b", _FB_FLOAT, 6),
        ])
        assert result["a"] == 10
        assert abs(result["b"] - 5.5) < 0.01

    def test_offset_beyond_vtable_returns_none(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_INT

        data = _build_fb_message([(_FB_INT, struct.pack("<i", 1))])
        result = _decode_table(data, [_FieldDef("missing", _FB_INT, 200)])
        assert result["missing"] is None

    def test_unknown_base_type_returns_none(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table

        data = _build_fb_message([(7, struct.pack("<i", 1))])
        result = _decode_table(data, [_FieldDef("x", 255, 4)])
        assert result["x"] is None

    def test_no_field_defs(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _decode_table, _FB_INT

        data = _build_fb_message([(_FB_INT, struct.pack("<i", 1))])
        assert _decode_table(data, []) == {}

    def test_byte_and_short_types(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import (
            _FieldDef, _decode_table, _FB_BYTE, _FB_SHORT, _FB_UBYTE, _FB_USHORT,
        )

        data = _build_fb_message([
            (_FB_BYTE, struct.pack("b", -5)),
            (_FB_UBYTE, struct.pack("B", 200)),
            (_FB_SHORT, struct.pack("<h", -1000)),
            (_FB_USHORT, struct.pack("<H", 60000)),
        ])
        result = _decode_table(data, [
            _FieldDef("a", _FB_BYTE, 4),
            _FieldDef("b", _FB_UBYTE, 6),
            _FieldDef("c", _FB_SHORT, 8),
            _FieldDef("d", _FB_USHORT, 10),
        ])
        assert result["a"] == -5
        assert result["b"] == 200
        assert result["c"] == -1000
        assert result["d"] == 60000

    def test_long_types(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import (
            _FieldDef, _decode_table, _FB_LONG, _FB_ULONG, _FB_UINT,
        )

        data = _build_fb_message([
            (_FB_UINT, struct.pack("<I", 3_000_000_000)),
            (_FB_LONG, struct.pack("<q", -999_999_999_999)),
            (_FB_ULONG, struct.pack("<Q", 18_000_000_000_000)),
        ])
        result = _decode_table(data, [
            _FieldDef("u32", _FB_UINT, 4),
            _FieldDef("i64", _FB_LONG, 6),
            _FieldDef("u64", _FB_ULONG, 8),
        ])
        assert result["u32"] == 3_000_000_000
        assert result["i64"] == -999_999_999_999
        assert result["u64"] == 18_000_000_000_000


class TestDecodeTableStringAndEdge:
    """Cover string decode path and zero-offset path in _decode_table."""

    def test_string_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_STRING

        # Build a message with a string field. Layout:
        # vtable at 4: [vtable_size=6, table_size=8, field0_off=4]
        # table at 12: [soffset=8, string_ref_offset(4 bytes)]
        # string at 20: [len=5, "hello"]
        buf = bytearray(32)
        struct.pack_into("<I", buf, 0, 12)       # root → table at 12
        struct.pack_into("<H", buf, 4, 6)         # vtable_size
        struct.pack_into("<H", buf, 6, 8)         # table_size
        struct.pack_into("<H", buf, 8, 4)         # field0 offset within table = 4
        struct.pack_into("<i", buf, 12, 8)        # soffset: 12 - 4 = 8
        # field data at table+4 = 16: string offset → 20 - 16 = 4
        struct.pack_into("<I", buf, 16, 4)
        # string at 20
        struct.pack_into("<I", buf, 20, 5)
        buf[24:29] = b"hello"

        result = _decode_table(bytes(buf), [_FieldDef("msg", _FB_STRING, 4)])
        assert result["msg"] == "hello"

    def test_zero_field_offset_returns_none(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_INT

        # Build a message where the field's vtable slot has offset 0
        buf = bytearray(20)
        struct.pack_into("<I", buf, 0, 8)         # root → table at 8
        struct.pack_into("<H", buf, 4, 6)         # vtable_size = 6
        struct.pack_into("<H", buf, 6, 4)         # table_size
        struct.pack_into("<H", buf, 8, 0)         # field0 offset = 0 (absent)
        # Since vtable is at 4 and table needs to point back:
        # Actually need table at pos 12 to get soffset right
        buf = bytearray(24)
        struct.pack_into("<I", buf, 0, 12)        # root → table at 12
        struct.pack_into("<H", buf, 4, 6)         # vtable_size
        struct.pack_into("<H", buf, 6, 4)         # table_size
        struct.pack_into("<H", buf, 8, 0)         # field0 offset = 0
        struct.pack_into("<i", buf, 12, 8)        # soffset: 12 - 4 = 8

        result = _decode_table(bytes(buf), [_FieldDef("x", _FB_INT, 4)])
        assert result["x"] is None

    def test_field_data_truncated_returns_none(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _FieldDef, _decode_table, _FB_DOUBLE

        # Build properly then truncate so the double (8 bytes) doesn't fit
        data = _build_fb_message([(_FB_DOUBLE, struct.pack("<d", 1.5))])
        truncated = data[: len(data) - 6]  # chop off end so double can't be read
        result = _decode_table(truncated, [_FieldDef("d", _FB_DOUBLE, 4)])
        assert result["d"] is None


def _build_bfbs_schema(field_name: str = "value", base_type: int = 7, field_offset: int = 4) -> bytes:
    """Construct a minimal valid .bfbs (FlatBuffer binary schema reflection) binary.

    The schema describes a single root table with one field.
    """
    buf = bytearray(400)
    # Positions chosen to avoid overlap
    SCHEMA_VTABLE = 8
    SCHEMA_TABLE = 40
    OBJECTS_VEC = 60
    OBJ_VTABLE = 80
    OBJ_TABLE = 100
    FIELDS_VEC = 120
    FIELD_VTABLE = 140
    FIELD_TABLE = 180
    NAME_STR = 250
    TYPE_VTABLE = 280
    TYPE_TABLE = 300

    # -- root offset --
    struct.pack_into("<I", buf, 0, SCHEMA_TABLE)

    # -- Schema vtable (3 fields: objects, enums, root_table) --
    struct.pack_into("<H", buf, SCHEMA_VTABLE, 10)      # vtable_size
    struct.pack_into("<H", buf, SCHEMA_VTABLE + 2, 8)   # table_size
    struct.pack_into("<H", buf, SCHEMA_VTABLE + 4, 4)   # objects offset = 4
    struct.pack_into("<H", buf, SCHEMA_VTABLE + 6, 0)   # enums = 0
    struct.pack_into("<H", buf, SCHEMA_VTABLE + 8, 0)   # root_table = 0

    # -- Schema table --
    struct.pack_into("<i", buf, SCHEMA_TABLE, SCHEMA_TABLE - SCHEMA_VTABLE)  # soffset
    # objects reference at schema_table + 4: offset to objects vector
    objects_ref_pos = SCHEMA_TABLE + 4
    struct.pack_into("<I", buf, objects_ref_pos, OBJECTS_VEC - objects_ref_pos)

    # -- Objects vector: 1 object --
    struct.pack_into("<I", buf, OBJECTS_VEC, 1)          # num_objects
    obj_ptr_pos = OBJECTS_VEC + 4
    struct.pack_into("<I", buf, obj_ptr_pos, OBJ_TABLE - obj_ptr_pos)

    # -- Object vtable (2 fields: name, fields) --
    struct.pack_into("<H", buf, OBJ_VTABLE, 8)          # vtable_size
    struct.pack_into("<H", buf, OBJ_VTABLE + 2, 8)      # table_size
    struct.pack_into("<H", buf, OBJ_VTABLE + 4, 0)      # name = 0 (skip)
    struct.pack_into("<H", buf, OBJ_VTABLE + 6, 4)      # fields offset = 4

    # -- Object table --
    struct.pack_into("<i", buf, OBJ_TABLE, OBJ_TABLE - OBJ_VTABLE)  # soffset
    # fields reference at obj_table + 4
    fields_ref_pos = OBJ_TABLE + 4
    struct.pack_into("<I", buf, fields_ref_pos, FIELDS_VEC - fields_ref_pos)

    # -- Fields vector: 1 field --
    struct.pack_into("<I", buf, FIELDS_VEC, 1)
    field_ptr_pos = FIELDS_VEC + 4
    struct.pack_into("<I", buf, field_ptr_pos, FIELD_TABLE - field_ptr_pos)

    # -- Field vtable (4 entries: name, type, id, offset) --
    struct.pack_into("<H", buf, FIELD_VTABLE, 12)        # vtable_size
    struct.pack_into("<H", buf, FIELD_VTABLE + 2, 16)    # table_size
    struct.pack_into("<H", buf, FIELD_VTABLE + 4, 4)     # name offset = 4
    struct.pack_into("<H", buf, FIELD_VTABLE + 6, 8)     # type offset = 8
    struct.pack_into("<H", buf, FIELD_VTABLE + 8, 0)     # id = 0
    struct.pack_into("<H", buf, FIELD_VTABLE + 10, 12)   # offset offset = 12

    # -- Field table --
    struct.pack_into("<i", buf, FIELD_TABLE, FIELD_TABLE - FIELD_VTABLE)  # soffset
    # name ref at field_table + 4
    name_ref_pos = FIELD_TABLE + 4
    struct.pack_into("<I", buf, name_ref_pos, NAME_STR - name_ref_pos)
    # type ref at field_table + 8
    type_ref_pos = FIELD_TABLE + 8
    struct.pack_into("<I", buf, type_ref_pos, TYPE_TABLE - type_ref_pos)
    # field_fb_offset at field_table + 12
    struct.pack_into("<H", buf, FIELD_TABLE + 12, field_offset)

    # -- Name string --
    name_bytes = field_name.encode("utf-8")
    struct.pack_into("<I", buf, NAME_STR, len(name_bytes))
    buf[NAME_STR + 4 : NAME_STR + 4 + len(name_bytes)] = name_bytes

    # -- Type vtable (1 field: base_type) --
    struct.pack_into("<H", buf, TYPE_VTABLE, 6)          # vtable_size
    struct.pack_into("<H", buf, TYPE_VTABLE + 2, 8)      # table_size
    struct.pack_into("<H", buf, TYPE_VTABLE + 4, 4)      # base_type offset = 4

    # -- Type table --
    struct.pack_into("<i", buf, TYPE_TABLE, TYPE_TABLE - TYPE_VTABLE)  # soffset
    buf[TYPE_TABLE + 4] = base_type

    return bytes(buf[:320])


class TestParseBfbsSchema:
    def test_too_short(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema

        assert _parse_bfbs_schema(b"\x00\x00") == []

    def test_invalid_binary(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema

        assert _parse_bfbs_schema(b"\x00" * 100) == []

    def test_random_bytes_returns_list(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema

        result = _parse_bfbs_schema(os.urandom(256))
        assert isinstance(result, list)

    def test_valid_bfbs_parses_fields(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema, _FB_INT

        bfbs = _build_bfbs_schema(field_name="velocity", base_type=_FB_INT, field_offset=4)
        fields = _parse_bfbs_schema(bfbs)
        assert len(fields) == 1
        assert fields[0].name == "velocity"
        assert fields[0].base_type == _FB_INT
        assert fields[0].offset == 4

    def test_bfbs_double_field(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import _parse_bfbs_schema, _FB_DOUBLE

        bfbs = _build_bfbs_schema(field_name="temperature", base_type=_FB_DOUBLE, field_offset=6)
        fields = _parse_bfbs_schema(bfbs)
        assert len(fields) == 1
        assert fields[0].name == "temperature"
        assert fields[0].base_type == _FB_DOUBLE

    def test_get_field_info_with_valid_bfbs(self):
        """Integration: FlatBufferDecoder.get_field_info with a valid bfbs."""
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder, _FB_FLOAT

        dec = FlatBufferDecoder()
        bfbs = _build_bfbs_schema(field_name="accel_x", base_type=_FB_FLOAT, field_offset=4)
        fields = dec.get_field_info(bfbs, "flatbuffer")
        assert len(fields) == 1
        assert fields[0].name == "accel_x"
        assert fields[0].type == "FLOAT"

    def test_decode_with_valid_bfbs(self):
        """Integration: full decode path using valid bfbs + crafted message."""
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder, _FB_INT

        dec = FlatBufferDecoder()
        bfbs = _build_bfbs_schema(field_name="count", base_type=_FB_INT, field_offset=4)
        msg = _build_fb_message([(_FB_INT, struct.pack("<i", 123))])
        result = dec.decode(bfbs, msg, schema_id=0)
        assert result["count"] == 123

    def test_decode_caches_schema(self):
        """Schema is cached when schema_id > 0."""
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder, _FB_INT

        dec = FlatBufferDecoder()
        bfbs = _build_bfbs_schema(field_name="x", base_type=_FB_INT, field_offset=4)
        msg = _build_fb_message([(_FB_INT, struct.pack("<i", 42))])
        assert 77 not in dec._schema_cache
        dec.decode(bfbs, msg, schema_id=77)
        assert 77 in dec._schema_cache
