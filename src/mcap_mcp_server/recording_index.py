"""Directory scanning, caching, and filtering for MCAP recordings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcap_mcp_server.mcap_reader import RecordingSummary, get_summary

logger = logging.getLogger(__name__)


class RecordingIndex:
    """Discovers and caches MCAP file summaries in a directory tree."""

    def __init__(self, recursive: bool = True) -> None:
        self._recursive = recursive
        self._cache: dict[str, RecordingSummary] = {}
        self._dir_mtime: dict[str, float] = {}

    def scan(
        self,
        path: str | Path,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[RecordingSummary]:
        """Scan a directory for MCAP files and return their summaries.

        Results are cached until the directory's mtime changes.
        """
        root = Path(path).resolve()
        if not root.is_dir():
            logger.warning("Data directory does not exist: %s", root)
            return []

        self._refresh_if_needed(root)

        results = list(self._cache.values())

        if after is not None:
            after_ns = int(after.timestamp() * 1e9)
            results = [r for r in results if r.end_time_ns >= after_ns]

        if before is not None:
            before_ns = int(before.timestamp() * 1e9)
            results = [r for r in results if r.start_time_ns <= before_ns]

        results.sort(key=lambda r: r.start_time_ns)
        return results

    def get(self, file_path: str | Path) -> RecordingSummary | None:
        """Get a cached summary by path, or read it on demand."""
        key = str(Path(file_path).resolve())
        if key in self._cache:
            return self._cache[key]
        p = Path(file_path)
        if p.is_file() and p.suffix == ".mcap":
            summary = _safe_get_summary(p)
            if summary:
                self._cache[key] = summary
            return summary
        return None

    def invalidate(self) -> None:
        self._cache.clear()
        self._dir_mtime.clear()

    def _refresh_if_needed(self, root: Path) -> None:
        root_key = str(root)
        try:
            current_mtime = root.stat().st_mtime
        except OSError:
            return

        if root_key in self._dir_mtime and self._dir_mtime[root_key] == current_mtime:
            return

        self._dir_mtime[root_key] = current_mtime
        glob_pattern = "**/*.mcap" if self._recursive else "*.mcap"
        found_paths: set[str] = set()

        for mcap_path in root.glob(glob_pattern):
            key = str(mcap_path.resolve())
            found_paths.add(key)
            if key not in self._cache:
                summary = _safe_get_summary(mcap_path)
                if summary:
                    self._cache[key] = summary

        stale = [k for k in self._cache if k.startswith(root_key) and k not in found_paths]
        for k in stale:
            del self._cache[k]

    def to_json(self, summaries: list[RecordingSummary]) -> list[dict[str, Any]]:
        """Serialise a list of summaries to the JSON shape from the spec."""
        result = []
        for s in summaries:
            result.append(
                {
                    "file": Path(s.path).name,
                    "path": s.path,
                    "size_mb": round(s.size_mb, 1),
                    "start_time": _ns_to_iso(s.start_time_ns),
                    "end_time": _ns_to_iso(s.end_time_ns),
                    "duration_s": round(s.duration_s, 1),
                    "message_count": s.message_count,
                    "channels": [
                        {
                            "topic": ch.topic,
                            "message_count": ch.message_count,
                            "schema": ch.schema_name,
                        }
                        for ch in s.channels
                    ],
                    "metadata_keys": list(
                        {k for md in s.metadata.values() for k in md}
                    ),
                }
            )
        return result


def _safe_get_summary(path: Path) -> RecordingSummary | None:
    try:
        return get_summary(path)
    except Exception:
        logger.warning("Failed to read MCAP summary: %s", path, exc_info=True)
        return None


def _ns_to_iso(ns: int) -> str:
    """Convert nanosecond MCAP timestamp to ISO 8601 string."""
    if ns == 0:
        return ""
    dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds")
