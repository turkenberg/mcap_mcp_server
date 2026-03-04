"""Tests for the ROS 1 decoder."""

import importlib.util

import pytest

ROS1_AVAILABLE = importlib.util.find_spec("mcap_ros1") is not None

pytestmark = pytest.mark.skipif(not ROS1_AVAILABLE, reason="mcap-ros1-support not installed")


BATTERY_MSG_DEF = """\
float32 voltage
float32 current
float32 percentage
bool present
"""

IMU_MSG_DEF = """\
# Standard IMU message
Header header
===
# Below this line is sub-message definition (ignored by our parser)
uint32 seq
"""


class TestRos1Decoder:
    def test_can_decode(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        assert dec.can_decode("ros1", "ros1msg")
        assert not dec.can_decode("json", "jsonschema")
        assert not dec.can_decode("cdr", "ros2msg")

    def test_get_field_info(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        fields = dec.get_field_info(BATTERY_MSG_DEF.encode(), "ros1msg")
        names = {f.name for f in fields}
        assert names == {"voltage", "current", "percentage", "present"}

        voltage = next(f for f in fields if f.name == "voltage")
        assert voltage.type == "FLOAT"
        present = next(f for f in fields if f.name == "present")
        assert present.type == "BOOLEAN"

    def test_get_field_info_stops_at_separator(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        fields = dec.get_field_info(IMU_MSG_DEF.encode(), "ros1msg")
        names = {f.name for f in fields}
        assert "header" in names
        assert "seq" not in names

    def test_get_field_info_empty(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        assert dec.get_field_info(b"", "ros1msg") == []

    def test_get_field_info_wrong_encoding(self):
        from mcap_mcp_server.decoders.ros1_decoder import Ros1Decoder

        dec = Ros1Decoder()
        assert dec.get_field_info(BATTERY_MSG_DEF.encode(), "protobuf") == []

    def test_ros_msg_to_dict(self):
        from mcap_mcp_server.decoders.ros1_decoder import _ros_msg_to_dict

        class FakeMsg:
            __slots__ = ["voltage", "current"]

            def __init__(self):
                self.voltage = 24.0
                self.current = -2.0

        result = _ros_msg_to_dict(FakeMsg())
        assert result == {"voltage": 24.0, "current": -2.0}

    def test_ros_msg_to_dict_nested(self):
        from mcap_mcp_server.decoders.ros1_decoder import _ros_msg_to_dict

        class Inner:
            __slots__ = ["x", "y"]

            def __init__(self):
                self.x = 1.0
                self.y = 2.0

        class Outer:
            __slots__ = ["position"]

            def __init__(self):
                self.position = Inner()

        result = _ros_msg_to_dict(Outer())
        assert result == {"position": {"x": 1.0, "y": 2.0}}
