"""Tests for the built-in JSON message decoder."""

import json

from mcap_mcp_server.decoders.json_decoder import JsonDecoder


class TestJsonDecoder:
    def setup_method(self):
        self.decoder = JsonDecoder(flatten_depth=3)

    def test_can_decode_json(self):
        assert self.decoder.can_decode("json", "jsonschema")
        assert self.decoder.can_decode("json", "json")
        assert self.decoder.can_decode("json", "")

    def test_cannot_decode_protobuf(self):
        assert not self.decoder.can_decode("protobuf", "protobuf")
        assert not self.decoder.can_decode("cdr", "ros2msg")

    def test_decode_flat_message(self):
        data = json.dumps({"voltage": 24.1, "current": -2.0}).encode()
        result = self.decoder.decode(b"", data)
        assert result == {"voltage": 24.1, "current": -2.0}

    def test_decode_nested_message(self):
        data = json.dumps({"pose": {"position": {"x": 1.0, "y": 2.0}}}).encode()
        result = self.decoder.decode(b"", data)
        assert result["pose_position_x"] == 1.0
        assert result["pose_position_y"] == 2.0

    def test_decode_non_dict_returns_value(self):
        data = json.dumps(42).encode()
        result = self.decoder.decode(b"", data)
        assert result == {"value": 42}

    def test_get_field_info_from_schema(self):
        schema = json.dumps(
            {
                "type": "object",
                "properties": {
                    "voltage": {"type": "number", "description": "Volts"},
                    "active": {"type": "boolean"},
                    "name": {"type": "string"},
                },
            }
        ).encode()
        fields = self.decoder.get_field_info(schema, "jsonschema")
        names = {f.name for f in fields}
        assert names == {"voltage", "active", "name"}

        voltage_field = next(f for f in fields if f.name == "voltage")
        assert voltage_field.type == "DOUBLE"
        assert voltage_field.description == "Volts"

        bool_field = next(f for f in fields if f.name == "active")
        assert bool_field.type == "BOOLEAN"

    def test_get_field_info_nested_schema(self):
        schema = json.dumps(
            {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                        },
                    },
                },
            }
        ).encode()
        fields = self.decoder.get_field_info(schema, "jsonschema")
        names = {f.name for f in fields}
        assert "position_x" in names
        assert "position_y" in names

    def test_get_field_info_empty_schema(self):
        assert self.decoder.get_field_info(b"", "jsonschema") == []

    def test_get_field_info_invalid_schema(self):
        assert self.decoder.get_field_info(b"not json", "jsonschema") == []
