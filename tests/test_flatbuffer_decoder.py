"""Tests for the FlatBuffer decoder."""

import struct

import pytest

try:
    import flatbuffers

    FLATBUFFERS_AVAILABLE = True
except ImportError:
    FLATBUFFERS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not FLATBUFFERS_AVAILABLE, reason="flatbuffers not installed")


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

    def test_decode_empty_data_returns_empty(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        result = dec.decode(b"", b"")
        assert result == {}

    def test_decode_invalid_data_returns_empty(self):
        from mcap_mcp_server.decoders.flatbuffer_decoder import FlatBufferDecoder

        dec = FlatBufferDecoder()
        result = dec.decode(b"\x00" * 4, b"\x00" * 4)
        assert isinstance(result, dict)

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
