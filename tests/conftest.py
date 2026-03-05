"""Shared fixtures for mcap-mcp-server tests."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from mcap.writer import Writer

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_mcap_dir(tmp_path: Path) -> Path:
    """Create a temp directory with two JSON-encoded MCAP files."""
    create_simple_mcap(tmp_path / "session_001.mcap")
    create_multi_topic_mcap(tmp_path / "session_002.mcap")
    return tmp_path


@pytest.fixture
def simple_mcap(tmp_path: Path) -> Path:
    """Single-topic JSON MCAP file."""
    p = tmp_path / "simple.mcap"
    create_simple_mcap(p)
    return p


@pytest.fixture
def multi_topic_mcap(tmp_path: Path) -> Path:
    """Multi-topic JSON MCAP file."""
    p = tmp_path / "multi.mcap"
    create_multi_topic_mcap(p)
    return p


@pytest.fixture
def protobuf_mcap(tmp_path: Path) -> Path:
    """Protobuf-encoded MCAP file."""
    p = tmp_path / "proto.mcap"
    create_protobuf_mcap(p)
    return p


@pytest.fixture
def ros1_mcap(tmp_path: Path) -> Path:
    """ROS 1-encoded MCAP file."""
    p = tmp_path / "ros1.mcap"
    create_ros1_mcap(p)
    return p


@pytest.fixture
def ros2_mcap(tmp_path: Path) -> Path:
    """ROS 2 CDR-encoded MCAP file."""
    p = tmp_path / "ros2.mcap"
    create_ros2_mcap(p)
    return p


@pytest.fixture
def flatbuffer_mcap(tmp_path: Path) -> Path:
    """FlatBuffer-encoded MCAP file."""
    p = tmp_path / "flatbuf.mcap"
    create_flatbuffer_mcap(p)
    return p


@pytest.fixture
def fixture_simple_mcap() -> Path:
    """Pre-generated simple.mcap from tests/fixtures/."""
    p = FIXTURES_DIR / "simple.mcap"
    assert p.exists(), f"Fixture missing: {p}. Run: python -m tests.generate_fixtures"
    return p


@pytest.fixture
def fixture_multi_topic_mcap() -> Path:
    """Pre-generated multi_topic.mcap from tests/fixtures/."""
    p = FIXTURES_DIR / "multi_topic.mcap"
    assert p.exists(), f"Fixture missing: {p}. Run: python -m tests.generate_fixtures"
    return p


def create_simple_mcap(path: Path, num_messages: int = 100) -> Path:
    """Write a minimal JSON-encoded MCAP file with a single /battery topic."""
    schema_data = json.dumps(
        {
            "type": "object",
            "properties": {
                "voltage": {"type": "number", "description": "Battery voltage in volts"},
                "current": {"type": "number", "description": "Battery current in amps"},
                "percentage": {"type": "number", "description": "Charge level 0-1"},
            },
        }
    ).encode()

    base_time_ns = 1_700_000_000_000_000_000  # ~2023-11-14

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start()

        schema_id = writer.register_schema(
            name="BatteryState",
            encoding="jsonschema",
            data=schema_data,
        )
        channel_id = writer.register_channel(
            topic="/battery",
            message_encoding="json",
            schema_id=schema_id,
        )

        for i in range(num_messages):
            ts = base_time_ns + i * 20_000_000  # 20 ms intervals
            msg = {
                "voltage": 24.0 - (i * 0.01),
                "current": -2.0 + (i * 0.005),
                "percentage": 1.0 - (i * 0.005),
            }
            writer.add_message(
                channel_id=channel_id,
                log_time=ts,
                data=json.dumps(msg).encode(),
                publish_time=ts,
            )

        writer.add_metadata(
            name="session_info",
            data={"session_id": "test-001", "operator": "pytest"},
        )

        writer.finish()

    return path


def create_multi_topic_mcap(path: Path, num_messages: int = 50) -> Path:
    """Write a JSON-encoded MCAP file with /imu and /cmd_vel topics."""
    imu_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "linear_acceleration_x": {"type": "number"},
                "linear_acceleration_y": {"type": "number"},
                "linear_acceleration_z": {"type": "number"},
                "angular_velocity_x": {"type": "number"},
                "angular_velocity_y": {"type": "number"},
                "angular_velocity_z": {"type": "number"},
            },
        }
    ).encode()

    cmd_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "linear_x": {"type": "number"},
                "linear_y": {"type": "number"},
                "angular_z": {"type": "number"},
            },
        }
    ).encode()

    base_time_ns = 1_700_000_000_000_000_000

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start()

        imu_schema_id = writer.register_schema(
            name="sensor_msgs/Imu", encoding="jsonschema", data=imu_schema
        )
        cmd_schema_id = writer.register_schema(
            name="geometry_msgs/Twist", encoding="jsonschema", data=cmd_schema
        )

        imu_ch = writer.register_channel(
            topic="/imu", message_encoding="json", schema_id=imu_schema_id
        )
        cmd_ch = writer.register_channel(
            topic="/cmd_vel", message_encoding="json", schema_id=cmd_schema_id
        )

        for i in range(num_messages):
            ts = base_time_ns + i * 10_000_000  # 10 ms

            imu_msg = {
                "linear_acceleration_x": 0.1 * i,
                "linear_acceleration_y": 0.0,
                "linear_acceleration_z": 9.81,
                "angular_velocity_x": 0.0,
                "angular_velocity_y": 0.0,
                "angular_velocity_z": 0.01 * i,
            }
            writer.add_message(
                channel_id=imu_ch, log_time=ts, data=json.dumps(imu_msg).encode(), publish_time=ts
            )

            if i % 2 == 0:
                cmd_msg = {"linear_x": 0.5, "linear_y": 0.0, "angular_z": 0.1}
                writer.add_message(
                    channel_id=cmd_ch,
                    log_time=ts,
                    data=json.dumps(cmd_msg).encode(),
                    publish_time=ts,
                )

        writer.add_metadata(
            name="session_info",
            data={"session_id": "test-002", "operator": "pytest"},
        )
        writer.add_metadata(
            name="hardware",
            data={"robot_model": "test_bot", "serial": "SN-001"},
        )

        writer.finish()

    return path


# ---------------------------------------------------------------------------
# Protobuf fixture
# ---------------------------------------------------------------------------


def _build_protobuf_schema_and_class() -> tuple[bytes, type]:
    """Build a Protobuf FileDescriptorSet for BatteryState and return
    (serialized_schema, message_class)."""
    from google.protobuf.descriptor_pb2 import (
        FieldDescriptorProto,
        FileDescriptorProto,
        FileDescriptorSet,
    )
    from google.protobuf.descriptor_pool import DescriptorPool
    from google.protobuf.message_factory import GetMessageClass

    fd = FileDescriptorProto()
    fd.name = "battery.proto"
    fd.package = "test"
    fd.syntax = "proto3"
    msg_type = fd.message_type.add()
    msg_type.name = "BatteryState"

    for idx, (name, ftype) in enumerate(
        [
            ("voltage", FieldDescriptorProto.TYPE_DOUBLE),
            ("current", FieldDescriptorProto.TYPE_DOUBLE),
            ("percentage", FieldDescriptorProto.TYPE_DOUBLE),
        ],
        start=1,
    ):
        f = msg_type.field.add()
        f.name = name
        f.number = idx
        f.type = ftype
        f.label = FieldDescriptorProto.LABEL_OPTIONAL

    fds = FileDescriptorSet()
    fds.file.append(fd)
    schema_bytes = fds.SerializeToString()

    pool = DescriptorPool()
    pool.Add(fd)
    descriptor = pool.FindMessageTypeByName("test.BatteryState")
    msg_class = GetMessageClass(descriptor)
    return schema_bytes, msg_class


def create_protobuf_mcap(path: Path, num_messages: int = 50) -> Path:
    """Write a Protobuf-encoded MCAP file with a /battery topic."""
    schema_bytes, msg_class = _build_protobuf_schema_and_class()
    base_time_ns = 1_700_000_000_000_000_000

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start()
        sid = writer.register_schema(
            name="test.BatteryState", encoding="protobuf", data=schema_bytes
        )
        cid = writer.register_channel(
            topic="/battery", message_encoding="protobuf", schema_id=sid
        )
        for i in range(num_messages):
            ts = base_time_ns + i * 20_000_000
            m = msg_class(
                voltage=24.0 - i * 0.01,
                current=-2.0 + i * 0.005,
                percentage=1.0 - i * 0.005,
            )
            writer.add_message(
                channel_id=cid, log_time=ts, data=m.SerializeToString(), publish_time=ts
            )
        writer.finish()

    return path


# ---------------------------------------------------------------------------
# ROS 1 fixture
# ---------------------------------------------------------------------------

_ROS1_BATTERY_MSG = """\
float64 voltage
float64 current
float64 percentage"""


def create_ros1_mcap(path: Path, num_messages: int = 50) -> Path:
    """Write a ROS 1-encoded MCAP file with a /battery topic."""
    base_time_ns = 1_700_000_000_000_000_000

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start()
        sid = writer.register_schema(
            name="BatteryState", encoding="ros1msg", data=_ROS1_BATTERY_MSG.encode()
        )
        cid = writer.register_channel(
            topic="/battery", message_encoding="ros1", schema_id=sid
        )
        for i in range(num_messages):
            ts = base_time_ns + i * 20_000_000
            voltage = 24.0 - i * 0.01
            current = -2.0 + i * 0.005
            percentage = 1.0 - i * 0.005
            data = struct.pack("<ddd", voltage, current, percentage)
            writer.add_message(channel_id=cid, log_time=ts, data=data, publish_time=ts)
        writer.finish()

    return path


# ---------------------------------------------------------------------------
# ROS 2 CDR fixture
# ---------------------------------------------------------------------------

_ROS2_BATTERY_MSG = """\
float64 voltage
float64 current
float64 percentage"""


def _cdr_encode_doubles(*values: float) -> bytes:
    """Minimal CDR LE encapsulation for a flat message of doubles."""
    header = b"\x00\x01\x00\x00"  # CDR little-endian
    return header + struct.pack(f"<{len(values)}d", *values)


def create_ros2_mcap(path: Path, num_messages: int = 50) -> Path:
    """Write a ROS 2 CDR-encoded MCAP file with a /battery topic."""
    base_time_ns = 1_700_000_000_000_000_000

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start()
        sid = writer.register_schema(
            name="test_msgs/msg/BatteryState",
            encoding="ros2msg",
            data=_ROS2_BATTERY_MSG.encode(),
        )
        cid = writer.register_channel(
            topic="/battery", message_encoding="cdr", schema_id=sid
        )
        for i in range(num_messages):
            ts = base_time_ns + i * 20_000_000
            voltage = 24.0 - i * 0.01
            current = -2.0 + i * 0.005
            percentage = 1.0 - i * 0.005
            data = _cdr_encode_doubles(voltage, current, percentage)
            writer.add_message(channel_id=cid, log_time=ts, data=data, publish_time=ts)
        writer.finish()

    return path


# ---------------------------------------------------------------------------
# FlatBuffers fixture
# ---------------------------------------------------------------------------

_FLATBUFFER_BFBS: bytes | None = None


def _get_flatbuffer_bfbs() -> bytes:
    """Return the .bfbs schema, generating it on-the-fly if flatc is available,
    otherwise falling back to a cached copy in tests/fixtures/."""
    global _FLATBUFFER_BFBS
    if _FLATBUFFER_BFBS is not None:
        return _FLATBUFFER_BFBS

    import shutil
    import subprocess
    import tempfile

    flatc = shutil.which("flatc")
    if flatc:
        with tempfile.TemporaryDirectory() as td:
            fbs = Path(td) / "battery.fbs"
            fbs.write_text(
                "namespace test;\n"
                "table BatteryState {\n"
                "  voltage: double;\n"
                "  current: double;\n"
                "  percentage: double;\n"
                "}\n"
                "root_type BatteryState;\n"
            )
            subprocess.run(
                [flatc, "--binary", "--schema", str(fbs)],
                cwd=td,
                check=True,
                capture_output=True,
            )
            _FLATBUFFER_BFBS = (Path(td) / "battery.bfbs").read_bytes()
    else:
        cached = FIXTURES_DIR / "battery.bfbs"
        if cached.exists():
            _FLATBUFFER_BFBS = cached.read_bytes()
        else:
            raise RuntimeError(
                "flatc not found and no cached battery.bfbs in tests/fixtures/. "
                "Install flatc or run: python -m tests.generate_fixtures"
            )
    return _FLATBUFFER_BFBS


def _flatbuffer_encode_battery(voltage: float, current: float, percentage: float) -> bytes:
    """Encode a BatteryState FlatBuffer message."""
    import flatbuffers

    builder = flatbuffers.Builder(128)
    builder.StartObject(3)
    builder.PrependFloat64Slot(0, voltage, 0.0)
    builder.PrependFloat64Slot(1, current, 0.0)
    builder.PrependFloat64Slot(2, percentage, 0.0)
    root = builder.EndObject()
    builder.Finish(root)
    return bytes(builder.Output())


def create_flatbuffer_mcap(path: Path, num_messages: int = 50) -> Path:
    """Write a FlatBuffer-encoded MCAP file with a /battery topic."""
    bfbs = _get_flatbuffer_bfbs()
    base_time_ns = 1_700_000_000_000_000_000

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start()
        sid = writer.register_schema(
            name="test.BatteryState", encoding="flatbuffer", data=bfbs
        )
        cid = writer.register_channel(
            topic="/battery", message_encoding="flatbuffer", schema_id=sid
        )
        for i in range(num_messages):
            ts = base_time_ns + i * 20_000_000
            voltage = 24.0 - i * 0.01
            current = -2.0 + i * 0.005
            percentage = 1.0 - i * 0.005
            data = _flatbuffer_encode_battery(voltage, current, percentage)
            writer.add_message(channel_id=cid, log_time=ts, data=data, publish_time=ts)
        writer.finish()

    return path
