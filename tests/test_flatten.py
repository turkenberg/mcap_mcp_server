"""Tests for nested dict flattening."""

import json

from mcap_mcp_server.flatten import flatten_dict


class TestFlattenDict:
    def test_flat_dict_unchanged(self):
        d = {"x": 1, "y": 2, "z": 3}
        assert flatten_dict(d) == d

    def test_single_level_nesting(self):
        d = {"position": {"x": 1.0, "y": 2.0}}
        assert flatten_dict(d) == {"position_x": 1.0, "position_y": 2.0}

    def test_two_level_nesting(self):
        d = {"pose": {"position": {"x": 1.0, "y": 2.0}}}
        result = flatten_dict(d, max_depth=3)
        assert result == {"pose_position_x": 1.0, "pose_position_y": 2.0}

    def test_max_depth_serialises_deep_nesting(self):
        d = {"a": {"b": {"c": {"d": 42}}}}
        result = flatten_dict(d, max_depth=2)
        assert result["a_b"] == json.dumps({"c": {"d": 42}})

    def test_arrays_serialised_as_json(self):
        d = {"values": [1, 2, 3], "name": "test"}
        result = flatten_dict(d)
        assert result["values"] == json.dumps([1, 2, 3])
        assert result["name"] == "test"

    def test_mixed_nesting(self):
        d = {
            "header": {"stamp": {"sec": 10, "nsec": 500}},
            "value": 42.0,
            "tags": ["a", "b"],
        }
        result = flatten_dict(d, max_depth=3)
        assert result["header_stamp_sec"] == 10
        assert result["header_stamp_nsec"] == 500
        assert result["value"] == 42.0
        assert result["tags"] == json.dumps(["a", "b"])

    def test_custom_separator(self):
        d = {"a": {"b": 1}}
        result = flatten_dict(d, separator=".")
        assert result == {"a.b": 1}

    def test_empty_dict(self):
        assert flatten_dict({}) == {}

    def test_none_values_preserved(self):
        d = {"x": None, "y": 1}
        result = flatten_dict(d)
        assert result == {"x": None, "y": 1}
