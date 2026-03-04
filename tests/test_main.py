"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mcap_mcp_server.__main__ import main, parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.data_dir is None
        assert args.transport is None
        assert args.port is None
        assert args.config is None
        assert args.log_level is None

    def test_all_flags(self, tmp_path: Path):
        args = parse_args([
            "--data-dir", str(tmp_path),
            "--transport", "sse",
            "--port", "9090",
            "--config", "my.toml",
            "--log-level", "DEBUG",
        ])
        assert args.data_dir == tmp_path
        assert args.transport == "sse"
        assert args.port == 9090
        assert args.config == Path("my.toml")
        assert args.log_level == "DEBUG"

    def test_partial_flags(self):
        args = parse_args(["--transport", "stdio", "--log-level", "WARNING"])
        assert args.transport == "stdio"
        assert args.log_level == "WARNING"
        assert args.data_dir is None


class TestMain:
    @patch("mcap_mcp_server.__main__.create_server")
    def test_main_stdio(self, mock_create, tmp_path: Path):
        mock_server = MagicMock()
        mock_create.return_value = mock_server
        main(["--data-dir", str(tmp_path)])
        mock_create.assert_called_once()
        mock_server.run.assert_called_once_with(transport="stdio")

    @patch("mcap_mcp_server.__main__.create_server")
    def test_main_sse(self, mock_create, tmp_path: Path):
        mock_server = MagicMock()
        mock_create.return_value = mock_server
        main(["--data-dir", str(tmp_path), "--transport", "sse", "--port", "9999"])
        mock_server.run.assert_called_once_with(
            transport="sse", host="0.0.0.0", port=9999
        )

    @patch("mcap_mcp_server.__main__.create_server")
    def test_main_with_all_overrides(self, mock_create, tmp_path: Path):
        mock_server = MagicMock()
        mock_create.return_value = mock_server
        main([
            "--data-dir", str(tmp_path),
            "--transport", "sse",
            "--port", "7777",
            "--log-level", "ERROR",
        ])
        config = mock_create.call_args[0][0]
        assert config.data_dir == tmp_path
        assert config.transport == "sse"
        assert config.sse_port == 7777
        assert config.log_level == "ERROR"
