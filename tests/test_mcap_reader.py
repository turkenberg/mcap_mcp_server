"""Tests for MCAP file reading."""

from pathlib import Path

from mcap_mcp_server.decoder_registry import DecoderRegistry
from mcap_mcp_server.mcap_reader import (
    get_schema_info,
    get_summary,
    iter_messages,
    topic_to_table_name,
)


class TestGetSummary:
    def test_reads_summary(self, simple_mcap: Path):
        summary = get_summary(simple_mcap)
        assert summary.message_count == 100
        assert summary.size_bytes > 0
        assert len(summary.channels) == 1
        assert summary.channels[0].topic == "/battery"
        assert summary.channels[0].schema_name == "BatteryState"
        assert summary.channels[0].message_encoding == "json"
        assert summary.duration_s > 0

    def test_reads_metadata(self, simple_mcap: Path):
        summary = get_summary(simple_mcap)
        assert "session_info" in summary.metadata
        assert summary.metadata["session_info"]["session_id"] == "test-001"

    def test_multi_topic_summary(self, multi_topic_mcap: Path):
        summary = get_summary(multi_topic_mcap)
        topics = {ch.topic for ch in summary.channels}
        assert topics == {"/imu", "/cmd_vel"}
        assert len(summary.metadata) == 2


class TestGetSchemaInfo:
    def test_returns_field_info(self, simple_mcap: Path):
        registry = DecoderRegistry()
        schemas = get_schema_info(simple_mcap, registry)
        assert "/battery" in schemas
        battery = schemas["/battery"]
        assert battery.table_name == "battery"
        field_names = {f.name for f in battery.fields}
        assert "timestamp_us" in field_names
        assert "voltage" in field_names
        assert "current" in field_names

    def test_filter_by_topic(self, multi_topic_mcap: Path):
        registry = DecoderRegistry()
        schemas = get_schema_info(multi_topic_mcap, registry, topic="/imu")
        assert "/imu" in schemas
        assert "/cmd_vel" not in schemas


class TestIterMessages:
    def test_iterates_all_messages(self, simple_mcap: Path):
        msgs = list(iter_messages(simple_mcap))
        assert len(msgs) == 100
        schema, channel, message = msgs[0]
        assert channel.topic == "/battery"
        assert message.log_time > 0

    def test_filter_by_topic(self, multi_topic_mcap: Path):
        msgs = list(iter_messages(multi_topic_mcap, topics=["/imu"]))
        for _, ch, _ in msgs:
            assert ch.topic == "/imu"
        assert len(msgs) == 50  # all imu messages


class TestTopicToTableName:
    def test_simple_topic(self):
        assert topic_to_table_name("/battery") == "battery"

    def test_nested_topic(self):
        assert topic_to_table_name("/battery/status") == "battery_status"

    def test_with_alias(self):
        assert topic_to_table_name("/imu", alias="r1") == "r1_imu"

    def test_no_alias(self):
        assert topic_to_table_name("/imu", alias=None) == "imu"
