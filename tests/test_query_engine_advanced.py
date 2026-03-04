"""Tests for QueryEngine LRU eviction, timeout, and memory tracking."""

from __future__ import annotations

import pandas as pd
import pytest

from mcap_mcp_server.query_engine import QueryEngine


class TestLRUEviction:
    def test_total_memory_tracked(self):
        engine = QueryEngine(max_memory_mb=100)
        df = pd.DataFrame({"x": list(range(100))})
        engine.register_dataframe("t1", df, group="g1")
        assert engine.total_memory_bytes > 0
        engine.close()

    def test_eviction_triggers_on_limit(self):
        engine = QueryEngine(max_memory_mb=0)  # 0 MB budget
        df = pd.DataFrame({"x": list(range(100))})
        engine.register_dataframe("t1", df, group="g1")
        # g1 should have been evicted to make room... but since the budget
        # is 0, the first registration will evict nothing (empty groups),
        # then register. The second registration should evict g1.
        engine.register_dataframe("t2", df, group="g2")
        assert "t1" not in engine.list_tables()
        assert "t2" in engine.list_tables()
        engine.close()

    def test_oldest_group_evicted_first(self):
        engine = QueryEngine(max_memory_mb=0)
        df = pd.DataFrame({"x": list(range(100))})
        engine.register_dataframe("a", df, group="first")
        engine.register_dataframe("b", df, group="second")
        # Adding a third group must evict the oldest ("first") first
        engine.register_dataframe("c", df, group="third")
        assert "a" not in engine.list_tables()
        # "b" may also be evicted depending on size, but "c" must survive
        assert "c" in engine.list_tables()
        engine.close()

    def test_group_tracks_multiple_tables(self):
        engine = QueryEngine(max_memory_mb=100)
        engine.register_dataframe("g1_a", pd.DataFrame({"x": [1]}), group="g1")
        engine.register_dataframe("g1_b", pd.DataFrame({"x": [2]}), group="g1")
        assert "g1_a" in engine.list_tables()
        assert "g1_b" in engine.list_tables()
        engine.close()

    def test_unregister_removes_from_group(self):
        engine = QueryEngine(max_memory_mb=100)
        engine.register_dataframe("t1", pd.DataFrame({"x": [1]}), group="g")
        engine.unregister("t1")
        assert "t1" not in engine.list_tables()
        assert engine._table_memory.get("t1") is None
        engine.close()

    def test_unregister_nonexistent_safe(self):
        engine = QueryEngine(max_memory_mb=100)
        engine.unregister("does_not_exist")
        engine.close()

    def test_drop_tables_with_prefix(self):
        engine = QueryEngine(max_memory_mb=100)
        engine.register_dataframe("r1_a", pd.DataFrame({"x": [1]}), group="r1")
        engine.register_dataframe("r1_b", pd.DataFrame({"x": [2]}), group="r1")
        engine.register_dataframe("r2_a", pd.DataFrame({"x": [3]}), group="r2")
        dropped = engine.drop_tables_with_prefix("r1_")
        assert set(dropped) == {"r1_a", "r1_b"}
        assert "r2_a" in engine.list_tables()
        engine.close()


class TestQueryTimeout:
    def test_fast_query_succeeds(self):
        engine = QueryEngine(query_timeout_s=10)
        engine.register_dataframe("t", pd.DataFrame({"x": [1, 2, 3]}))
        result = engine.execute("SELECT * FROM t")
        assert result["row_count"] == 3
        engine.close()

    def test_timeout_returns_error(self):
        engine = QueryEngine(query_timeout_s=1)
        engine.register_dataframe("t", pd.DataFrame({"x": list(range(10))}))
        # generate_series with a cross join to simulate a slow query
        result = engine.execute(
            "SELECT count(*) FROM generate_series(1, 100000000) s1, "
            "generate_series(1, 100000000) s2"
        )
        assert "error" in result
        assert "timed out" in result["error"]
        assert "execution_time_ms" in result
        engine.close()


class TestMemoryProperty:
    def test_memory_increases(self):
        engine = QueryEngine(max_memory_mb=100)
        before = engine.total_memory_bytes
        engine.register_dataframe("t", pd.DataFrame({"x": list(range(1000))}))
        after = engine.total_memory_bytes
        assert after > before
        engine.close()

    def test_memory_decreases_on_unregister(self):
        engine = QueryEngine(max_memory_mb=100)
        engine.register_dataframe("t", pd.DataFrame({"x": list(range(1000))}))
        after_reg = engine.total_memory_bytes
        engine.unregister("t")
        assert engine.total_memory_bytes < after_reg
        engine.close()
