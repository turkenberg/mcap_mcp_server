#!/usr/bin/env python3
"""Generate static MCAP fixture files for tests.

Run once (or after schema changes) to regenerate:

    python -m tests.generate_fixtures

The resulting files are committed to version control so that
``pytest`` does not require the mcap writer at test-collection time.
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import create_multi_topic_mcap, create_simple_mcap

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def main() -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)

    simple = FIXTURES_DIR / "simple.mcap"
    create_simple_mcap(simple, num_messages=10)
    print(f"  wrote {simple}  ({simple.stat().st_size} bytes)")

    multi = FIXTURES_DIR / "multi_topic.mcap"
    create_multi_topic_mcap(multi, num_messages=50)
    print(f"  wrote {multi}  ({multi.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
