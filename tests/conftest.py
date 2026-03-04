"""Shared fixtures for mcap-mcp-server tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcap.writer import Writer

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
