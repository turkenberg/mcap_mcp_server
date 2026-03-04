"""Tests for the decoder registry."""


from mcap_mcp_server.decoder_registry import DecoderRegistry
from mcap_mcp_server.decoders.json_decoder import JsonDecoder


class TestDecoderRegistry:
    def test_json_decoder_registered_by_default(self):
        reg = DecoderRegistry()
        decoder = reg.get_decoder("json", "jsonschema")
        assert decoder is not None
        assert isinstance(decoder, JsonDecoder)

    def test_unknown_encoding_returns_none(self):
        reg = DecoderRegistry()
        assert reg.get_decoder("totally_unknown", "unknown_schema") is None

    def test_register_custom_decoder(self):
        reg = DecoderRegistry()

        class FakeDecoder:
            def can_decode(self, msg_enc, schema_enc):
                return msg_enc == "fake"

            def decode(self, schema, data, **kwargs):
                return {}

            def get_field_info(self, schema, schema_encoding):
                return []

        reg.register(FakeDecoder())
        assert reg.get_decoder("fake", "any") is not None

    def test_available_encodings(self):
        reg = DecoderRegistry()
        encodings = reg.available_encodings
        assert "JsonDecoder" in encodings

    def test_optional_decoders_registered_when_available(self):
        reg = DecoderRegistry()
        encodings = reg.available_encodings
        # These should be auto-registered since the packages are installed
        assert "ProtobufDecoder" in encodings
        assert "Ros1Decoder" in encodings
        assert "Ros2Decoder" in encodings
        assert "FlatBufferDecoder" in encodings

    def test_protobuf_encoding_found(self):
        reg = DecoderRegistry()
        assert reg.get_decoder("protobuf", "protobuf") is not None

    def test_ros1_encoding_found(self):
        reg = DecoderRegistry()
        assert reg.get_decoder("ros1", "ros1msg") is not None

    def test_ros2_encoding_found(self):
        reg = DecoderRegistry()
        assert reg.get_decoder("cdr", "ros2msg") is not None

    def test_flatbuffer_encoding_found(self):
        reg = DecoderRegistry()
        assert reg.get_decoder("flatbuffer", "flatbuffer") is not None

    def test_discover_does_not_crash(self):
        reg = DecoderRegistry()
        reg.discover()

    def test_flatten_depth_passed_to_json_decoder(self):
        reg = DecoderRegistry(flatten_depth=5)
        decoder = reg.get_decoder("json", "jsonschema")
        assert isinstance(decoder, JsonDecoder)
        assert decoder._flatten_depth == 5
