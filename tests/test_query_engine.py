"""Tests for the DuckDB query engine."""

import pandas as pd
import pytest

from mcap_mcp_server.query_engine import QueryEngine


@pytest.fixture
def engine():
    e = QueryEngine(query_timeout_s=10, default_row_limit=100, max_row_limit=500)
    yield e
    e.close()


@pytest.fixture
def engine_with_data(engine: QueryEngine):
    df = pd.DataFrame(
        {
            "timestamp_us": [1000, 2000, 3000, 4000, 5000],
            "voltage": [24.0, 23.9, 23.8, 23.5, 23.0],
            "current": [-2.0, -2.1, -2.0, -1.9, -2.2],
        }
    )
    engine.register_dataframe("battery", df)
    return engine


class TestQueryEngine:
    def test_register_and_query(self, engine_with_data: QueryEngine):
        result = engine_with_data.execute("SELECT * FROM battery")
        assert result["row_count"] == 5
        assert "voltage" in result["columns"]

    def test_filter_query(self, engine_with_data: QueryEngine):
        result = engine_with_data.execute("SELECT * FROM battery WHERE voltage < 23.8")
        assert result["row_count"] == 2

    def test_aggregation(self, engine_with_data: QueryEngine):
        result = engine_with_data.execute(
            "SELECT AVG(voltage) as avg_v, MIN(voltage) as min_v FROM battery"
        )
        assert result["row_count"] == 1
        assert len(result["columns"]) == 2

    def test_row_limit_enforced(self, engine: QueryEngine):
        df = pd.DataFrame({"x": list(range(200))})
        engine.register_dataframe("big", df)
        result = engine.execute("SELECT * FROM big")
        assert result["row_count"] == 100  # default limit
        assert result["truncated"] is True

    def test_custom_limit(self, engine_with_data: QueryEngine):
        result = engine_with_data.execute("SELECT * FROM battery", limit=2)
        assert result["row_count"] == 2
        assert result["truncated"] is True

    def test_max_row_limit(self, engine: QueryEngine):
        df = pd.DataFrame({"x": list(range(1000))})
        engine.register_dataframe("big", df)
        result = engine.execute("SELECT * FROM big", limit=999)
        assert result["row_count"] == 500  # capped at max_row_limit

    def test_list_tables(self, engine_with_data: QueryEngine):
        tables = engine_with_data.list_tables()
        assert "battery" in tables
        assert tables["battery"] == 5

    def test_unregister_table(self, engine_with_data: QueryEngine):
        engine_with_data.unregister("battery")
        assert "battery" not in engine_with_data.list_tables()

    def test_drop_tables_with_prefix(self, engine: QueryEngine):
        engine.register_dataframe("r1_imu", pd.DataFrame({"x": [1]}))
        engine.register_dataframe("r1_battery", pd.DataFrame({"x": [2]}))
        engine.register_dataframe("r2_imu", pd.DataFrame({"x": [3]}))
        dropped = engine.drop_tables_with_prefix("r1_")
        assert set(dropped) == {"r1_imu", "r1_battery"}
        assert "r2_imu" in engine.list_tables()

    def test_blocked_keyword_rejected(self, engine_with_data: QueryEngine):
        with pytest.raises(ValueError, match="Blocked SQL keyword"):
            engine_with_data.execute("COPY battery TO '/tmp/out.csv'")

    def test_blocked_function_rejected(self, engine_with_data: QueryEngine):
        with pytest.raises(ValueError, match="Blocked SQL function"):
            engine_with_data.execute("SELECT * FROM read_csv('/etc/passwd')")

    def test_invalid_sql_returns_error(self, engine_with_data: QueryEngine):
        result = engine_with_data.execute("SELECT * FROM nonexistent_table")
        assert "error" in result
