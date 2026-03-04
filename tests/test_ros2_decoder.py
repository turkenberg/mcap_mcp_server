"""Tests for the ROS 2 decoder."""

from types import SimpleNamespace

import pytest

try:
    import mcap_ros2  # noqa: F401

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False

pytestmark = pytest.mark.skipif(not ROS2_AVAILABLE, reason="mcap-ros2-support not installed")


BATTERY_MSG_DEF = """\
float32 voltage
float32 current
float32 percentage
bool present
"""

IMU_MSG_DEF = """\
# Standard IMU
float64 linear_acceleration_x
float64 linear_acceleration_y
float64 linear_acceleration_z
float64 angular_velocity_x
float64 angular_velocity_y
float64 angular_velocity_z
"""

ARRAY_MSG_DEF = """\
float64[] data
string label
uint32 count
"""


class TestRos2Decoder:
    def test_can_decode(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        assert dec.can_decode("cdr", "ros2msg")
        assert dec.can_decode("cdr", "ros2idl")
        assert not dec.can_decode("json", "jsonschema")
        assert not dec.can_decode("ros1", "ros1msg")

    def test_get_field_info_msg(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        fields = dec.get_field_info(BATTERY_MSG_DEF.encode(), "ros2msg")
        names = {f.name for f in fields}
        assert names == {"voltage", "current", "percentage", "present"}

        voltage = next(f for f in fields if f.name == "voltage")
        assert voltage.type == "FLOAT"

    def test_get_field_info_imu(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        fields = dec.get_field_info(IMU_MSG_DEF.encode(), "ros2msg")
        names = {f.name for f in fields}
        assert "linear_acceleration_x" in names
        assert "angular_velocity_z" in names
        for f in fields:
            assert f.type == "DOUBLE"

    def test_get_field_info_arrays_as_varchar(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        fields = dec.get_field_info(ARRAY_MSG_DEF.encode(), "ros2msg")
        data_field = next(f for f in fields if f.name == "data")
        assert data_field.type == "VARCHAR"

    def test_get_field_info_empty(self):
        from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder

        dec = Ros2Decoder()
        assert dec.get_field_info(b"", "ros2msg") == []

    def test_namespace_to_dict_flat(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        ns = SimpleNamespace(x=1.0, y=2.0, z=3.0)
        result = _namespace_to_dict(ns)
        assert result == {"x": 1.0, "y": 2.0, "z": 3.0}

    def test_namespace_to_dict_nested(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        ns = SimpleNamespace(
            position=SimpleNamespace(x=1.0, y=2.0),
            name="test",
        )
        result = _namespace_to_dict(ns)
        assert result == {"position": {"x": 1.0, "y": 2.0}, "name": "test"}

    def test_namespace_to_dict_with_list(self):
        from mcap_mcp_server.decoders.ros2_decoder import _namespace_to_dict

        ns = SimpleNamespace(values=[1.0, 2.0, 3.0], label="test")
        result = _namespace_to_dict(ns)
        assert result == {"values": [1.0, 2.0, 3.0], "label": "test"}


class TestRos2IdlParsing:
    def test_parse_simple_idl(self):
        from mcap_mcp_server.decoders.ros2_decoder import _parse_ros_idl

        idl = """\
module sensor_msgs {
  module msg {
    struct BatteryState {
      float voltage;
      float current;
      boolean present;
      string label;
    };
  };
};
"""
        fields = _parse_ros_idl(idl, max_depth=3)
        names = {f.name for f in fields}
        assert "voltage" in names
        assert "current" in names
        assert "present" in names
        assert "label" in names

    def test_parse_idl_sequence_as_varchar(self):
        from mcap_mcp_server.decoders.ros2_decoder import _parse_ros_idl

        idl = """\
struct Msg {
  sequence<float> data;
  double value;
};
"""
        fields = _parse_ros_idl(idl, max_depth=3)
        data_field = next(f for f in fields if f.name == "data")
        assert data_field.type == "VARCHAR"
        value_field = next(f for f in fields if f.name == "value")
        assert value_field.type == "DOUBLE"
