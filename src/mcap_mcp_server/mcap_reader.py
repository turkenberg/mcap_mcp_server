"""MCAP file reading: summary extraction, schema info, and message iteration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from mcap.reader import make_reader
from mcap.records import Channel, Message, Schema

from mcap_mcp_server.decoder_registry import DecoderRegistry
from mcap_mcp_server.decoders.base import FieldInfo

logger = logging.getLogger(__name__)


@dataclass
class ChannelSummary:
    topic: str
    schema_name: str
    message_encoding: str
    schema_encoding: str
    message_count: int
    schema_id: int
    channel_id: int


@dataclass
class RecordingSummary:
    path: str
    size_bytes: int
    start_time_ns: int
    end_time_ns: int
    message_count: int
    channels: list[ChannelSummary] = field(default_factory=list)
    metadata: dict[str, dict[str, str]] = field(default_factory=dict)
    attachment_names: list[dict[str, Any]] = field(default_factory=list)
    library: str = ""

    @property
    def duration_s(self) -> float:
        if self.end_time_ns <= self.start_time_ns:
            return 0.0
        return (self.end_time_ns - self.start_time_ns) / 1e9

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def start_time_us(self) -> int:
        return self.start_time_ns // 1000

    @property
    def end_time_us(self) -> int:
        return self.end_time_ns // 1000


@dataclass
class TopicSchema:
    table_name: str
    message_count: int
    schema_name: str
    message_encoding: str
    fields: list[FieldInfo]


def _topic_to_table_name(topic: str) -> str:
    """Convert an MCAP topic name to a valid SQL table name."""
    name = topic.lstrip("/").replace("/", "_")
    if not name:
        name = "unknown"
    return name


def get_summary(path: str | Path) -> RecordingSummary:
    """Read the summary section of an MCAP file (fast, no message decoding)."""
    path = Path(path)
    size_bytes = path.stat().st_size

    with open(path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()

        if summary is None:
            return RecordingSummary(
                path=str(path),
                size_bytes=size_bytes,
                start_time_ns=0,
                end_time_ns=0,
                message_count=0,
            )

        stats = summary.statistics
        start_time_ns = stats.message_start_time if stats else 0
        end_time_ns = stats.message_end_time if stats else 0
        message_count = stats.message_count if stats else 0

        channel_message_counts = stats.channel_message_counts if stats else {}

        channels: list[ChannelSummary] = []
        for ch_id, channel in summary.channels.items():
            schema = summary.schemas.get(channel.schema_id)
            channels.append(
                ChannelSummary(
                    topic=channel.topic,
                    schema_name=schema.name if schema else "",
                    message_encoding=channel.message_encoding,
                    schema_encoding=schema.encoding if schema else "",
                    message_count=channel_message_counts.get(ch_id, 0),
                    schema_id=channel.schema_id,
                    channel_id=ch_id,
                )
            )

        metadata: dict[str, dict[str, str]] = {}
        for md in reader.iter_metadata():
            metadata[md.name] = dict(md.metadata)

        header = reader.get_header()
        library = header.library if header else ""

        attachments: list[dict[str, Any]] = []
        for ai in summary.attachment_indexes:
            attachments.append(
                {
                    "name": ai.name,
                    "size_bytes": ai.length,
                    "media_type": ai.media_type,
                }
            )

    return RecordingSummary(
        path=str(path),
        size_bytes=size_bytes,
        start_time_ns=start_time_ns,
        end_time_ns=end_time_ns,
        message_count=message_count,
        channels=channels,
        metadata=metadata,
        attachment_names=attachments,
        library=library,
    )


def get_schema_info(
    path: str | Path,
    registry: DecoderRegistry,
    topic: str | None = None,
) -> dict[str, TopicSchema]:
    """Extract per-topic field info suitable for SQL query planning."""
    path = Path(path)
    summary = get_summary(path)
    result: dict[str, TopicSchema] = {}

    with open(path, "rb") as f:
        reader = make_reader(f)
        file_summary = reader.get_summary()
        if file_summary is None:
            return result

        for ch_summary in summary.channels:
            if topic and ch_summary.topic != topic:
                continue

            decoder = registry.get_decoder(
                ch_summary.message_encoding, ch_summary.schema_encoding
            )
            fields = [
                FieldInfo(
                    name="timestamp_us",
                    type="BIGINT",
                    description="Message timestamp (microseconds, from MCAP log_time)",
                )
            ]
            if decoder:
                schema_obj = file_summary.schemas.get(ch_summary.schema_id)
                schema_data = schema_obj.data if schema_obj else b""
                try:
                    fields.extend(
                        decoder.get_field_info(schema_data, ch_summary.schema_encoding)
                    )
                except Exception:
                    logger.warning(
                        "Failed to extract field info for %s", ch_summary.topic, exc_info=True
                    )

            result[ch_summary.topic] = TopicSchema(
                table_name=_topic_to_table_name(ch_summary.topic),
                message_count=ch_summary.message_count,
                schema_name=ch_summary.schema_name,
                message_encoding=ch_summary.message_encoding,
                fields=fields,
            )

    return result


def iter_messages(
    path: str | Path,
    topics: list[str] | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
) -> Iterator[tuple[Schema | None, Channel, Message]]:
    """Iterate over raw MCAP messages, optionally filtered by topic and time range.

    Time parameters are in nanoseconds (matching MCAP's internal representation).
    """
    path = Path(path)
    with open(path, "rb") as f:
        reader = make_reader(f)
        yield from reader.iter_messages(
            topics=topics,
            start_time=start_time,
            end_time=end_time,
            log_time_order=True,
        )


def topic_to_table_name(topic: str, alias: str | None = None) -> str:
    """Build a DuckDB table name from topic, with optional alias prefix."""
    table = _topic_to_table_name(topic)
    if alias:
        return f"{alias}_{table}"
    return table
