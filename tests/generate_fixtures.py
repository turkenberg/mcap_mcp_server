#!/usr/bin/env python3
"""Generate static MCAP fixture files for tests.

Run once (or after schema changes) to regenerate:

    python -m tests.generate_fixtures

The resulting files are committed to version control so that
``pytest`` does not require the mcap writer at test-collection time.
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import (
    _get_flatbuffer_bfbs,
    create_flatbuffer_mcap,
    create_multi_topic_mcap,
    create_protobuf_mcap,
    create_ros1_mcap,
    create_ros2_mcap,
    create_simple_mcap,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def main() -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)

    fixtures: list[tuple[str, Path]] = []

    simple = FIXTURES_DIR / "simple.mcap"
    create_simple_mcap(simple, num_messages=10)
    fixtures.append(("JSON (simple)", simple))

    multi = FIXTURES_DIR / "multi_topic.mcap"
    create_multi_topic_mcap(multi, num_messages=50)
    fixtures.append(("JSON (multi-topic)", multi))

    proto = FIXTURES_DIR / "protobuf.mcap"
    create_protobuf_mcap(proto, num_messages=10)
    fixtures.append(("Protobuf", proto))

    ros1 = FIXTURES_DIR / "ros1.mcap"
    create_ros1_mcap(ros1, num_messages=10)
    fixtures.append(("ROS 1", ros1))

    ros2 = FIXTURES_DIR / "ros2.mcap"
    create_ros2_mcap(ros2, num_messages=10)
    fixtures.append(("ROS 2 CDR", ros2))

    # Cache the .bfbs schema for CI environments without flatc
    bfbs_path = FIXTURES_DIR / "battery.bfbs"
    bfbs_path.write_bytes(_get_flatbuffer_bfbs())
    fixtures.append(("FlatBuffer schema (.bfbs)", bfbs_path))

    fb = FIXTURES_DIR / "flatbuffer.mcap"
    create_flatbuffer_mcap(fb, num_messages=10)
    fixtures.append(("FlatBuffers", fb))

    for label, p in fixtures:
        print(f"  {label:30s}  {p.name:30s}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
