"""Tests for configuration loading (env vars, TOML, CLI overrides)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mcap_mcp_server.config import ServerConfig, _bool_env, _load_toml, load_config


class TestServerConfigDefaults:
    def test_defaults(self):
        cfg = ServerConfig()
        assert cfg.data_dir == Path(".")
        assert cfg.recursive is True
        assert cfg.max_memory_mb == 2048
        assert cfg.query_timeout_s == 30
        assert cfg.default_row_limit == 1000
        assert cfg.max_row_limit == 10000
        assert cfg.log_level == "INFO"
        assert cfg.transport == "stdio"
        assert cfg.sse_port == 8080
        assert cfg.flatten_depth == 3

    def test_configure_logging(self):
        cfg = ServerConfig(log_level="DEBUG")
        cfg.configure_logging()


class TestBoolEnv:
    @pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "Yes"])
    def test_truthy(self, val: str):
        assert _bool_env(val) is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "nope", ""])
    def test_falsy(self, val: str):
        assert _bool_env(val) is False


class TestLoadToml:
    def test_missing_file(self, tmp_path: Path):
        result = _load_toml(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_valid_toml(self, tmp_path: Path):
        toml_file = tmp_path / "test.toml"
        toml_file.write_text(textwrap.dedent("""\
            [server]
            data_dir = "/recordings"
            recursive = false
            transport = "sse"

            [limits]
            max_memory_mb = 4096
            query_timeout_s = 60

            [decoder]
            flatten_depth = 5

            [logging]
            level = "DEBUG"
        """))
        result = _load_toml(toml_file)
        assert result["server"]["data_dir"] == "/recordings"
        assert result["limits"]["max_memory_mb"] == 4096
        assert result["decoder"]["flatten_depth"] == 5
        assert result["logging"]["level"] == "DEBUG"

    def test_invalid_toml(self, tmp_path: Path):
        toml_file = tmp_path / "bad.toml"
        toml_file.write_bytes(b"\x00\x01\x02\xff")
        result = _load_toml(toml_file)
        assert result == {}


class TestLoadConfig:
    def test_defaults_no_toml(self, tmp_path: Path):
        cfg = load_config(toml_path=tmp_path / "nope.toml")
        assert cfg.data_dir == Path(".")
        assert cfg.query_timeout_s == 30

    def test_toml_overrides_defaults(self, tmp_path: Path):
        toml_file = tmp_path / "cfg.toml"
        toml_file.write_text(textwrap.dedent("""\
            [server]
            data_dir = "/data"
            recursive = false

            [limits]
            query_timeout_s = 120
            max_row_limit = 50000

            [decoder]
            flatten_depth = 5

            [logging]
            level = "WARNING"
        """))
        cfg = load_config(toml_path=toml_file)
        assert cfg.data_dir == Path("/data")
        assert cfg.recursive is False
        assert cfg.query_timeout_s == 120
        assert cfg.max_row_limit == 50000
        assert cfg.flatten_depth == 5
        assert cfg.log_level == "WARNING"

    def test_env_vars_override_toml(self, tmp_path: Path, monkeypatch):
        toml_file = tmp_path / "cfg.toml"
        toml_file.write_text('[limits]\nquery_timeout_s = 120\n')
        monkeypatch.setenv("MCAP_QUERY_TIMEOUT_S", "5")
        monkeypatch.setenv("MCAP_DATA_DIR", "/env/data")
        monkeypatch.setenv("MCAP_RECURSIVE", "false")
        monkeypatch.setenv("MCAP_MAX_MEMORY_MB", "512")
        monkeypatch.setenv("MCAP_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("MCAP_TRANSPORT", "sse")
        monkeypatch.setenv("MCAP_SSE_PORT", "9090")
        monkeypatch.setenv("MCAP_FLATTEN_DEPTH", "2")
        monkeypatch.setenv("MCAP_DEFAULT_ROW_LIMIT", "500")
        monkeypatch.setenv("MCAP_MAX_ROW_LIMIT", "5000")

        cfg = load_config(toml_path=toml_file)
        assert cfg.query_timeout_s == 5
        assert cfg.data_dir == Path("/env/data")
        assert cfg.recursive is False
        assert cfg.max_memory_mb == 512
        assert cfg.log_level == "ERROR"
        assert cfg.transport == "sse"
        assert cfg.sse_port == 9090
        assert cfg.flatten_depth == 2
        assert cfg.default_row_limit == 500
        assert cfg.max_row_limit == 5000

    def test_invalid_env_var_ignored(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("MCAP_QUERY_TIMEOUT_S", "not_a_number")
        cfg = load_config(toml_path=tmp_path / "nope.toml")
        assert cfg.query_timeout_s == 30  # default preserved

    def test_cli_overrides_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("MCAP_QUERY_TIMEOUT_S", "60")
        cfg = load_config(
            toml_path=tmp_path / "nope.toml",
            cli_overrides={"query_timeout_s": 5, "data_dir": Path("/cli")},
        )
        assert cfg.query_timeout_s == 5
        assert cfg.data_dir == Path("/cli")

    def test_cli_overrides_ignores_none(self, tmp_path: Path):
        cfg = load_config(
            toml_path=tmp_path / "nope.toml",
            cli_overrides={"query_timeout_s": None},
        )
        assert cfg.query_timeout_s == 30

    def test_default_toml_path_when_none(self):
        cfg = load_config(toml_path=None)
        assert isinstance(cfg, ServerConfig)
