"""Tests for recording directory scanning and caching."""

from datetime import datetime, timezone
from pathlib import Path

from mcap_mcp_server.recording_index import RecordingIndex


class TestRecordingIndex:
    def test_scan_finds_mcap_files(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        results = idx.scan(tmp_mcap_dir)
        assert len(results) == 2
        filenames = {Path(r.path).name for r in results}
        assert filenames == {"session_001.mcap", "session_002.mcap"}

    def test_scan_caches_results(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        r1 = idx.scan(tmp_mcap_dir)
        r2 = idx.scan(tmp_mcap_dir)
        assert len(r1) == len(r2)

    def test_scan_empty_dir(self, tmp_path: Path):
        idx = RecordingIndex()
        results = idx.scan(tmp_path)
        assert results == []

    def test_scan_nonexistent_dir(self, tmp_path: Path):
        idx = RecordingIndex()
        results = idx.scan(tmp_path / "does_not_exist")
        assert results == []

    def test_get_by_path(self, simple_mcap: Path):
        idx = RecordingIndex()
        summary = idx.get(simple_mcap)
        assert summary is not None
        assert summary.message_count == 100

    def test_get_nonexistent(self, tmp_path: Path):
        idx = RecordingIndex()
        assert idx.get(tmp_path / "nope.mcap") is None

    def test_invalidate_clears_cache(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        idx.scan(tmp_mcap_dir)
        idx.invalidate()
        assert idx._cache == {}

    def test_to_json_format(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        summaries = idx.scan(tmp_mcap_dir)
        data = idx.to_json(summaries)
        assert len(data) == 2
        for item in data:
            assert "file" in item
            assert "path" in item
            assert "size_mb" in item
            assert "channels" in item
            assert "message_count" in item

    def test_filter_by_after(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        # All test files have timestamps around 2023-11-14, so filtering after 2024 should exclude them
        after = datetime(2024, 1, 1, tzinfo=timezone.utc)
        results = idx.scan(tmp_mcap_dir, after=after)
        assert len(results) == 0

    def test_filter_by_before(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        # Filtering before 2020 should exclude all test files
        before = datetime(2020, 1, 1, tzinfo=timezone.utc)
        results = idx.scan(tmp_mcap_dir, before=before)
        assert len(results) == 0

    def test_filter_includes_matching(self, tmp_mcap_dir: Path):
        idx = RecordingIndex()
        # Filtering with wide range should include everything
        after = datetime(2020, 1, 1, tzinfo=timezone.utc)
        before = datetime(2030, 1, 1, tzinfo=timezone.utc)
        results = idx.scan(tmp_mcap_dir, after=after, before=before)
        assert len(results) == 2
