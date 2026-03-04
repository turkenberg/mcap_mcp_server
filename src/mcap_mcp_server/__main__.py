"""CLI entry point for mcap-mcp-server."""

from __future__ import annotations

import argparse
from pathlib import Path

from mcap_mcp_server.config import load_config
from mcap_mcp_server.server import create_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mcap-mcp-server",
        description="SQL query interface for MCAP robotics data via MCP",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Root directory to scan for MCAP files (overrides MCAP_DATA_DIR)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for SSE transport (default: 8080)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to mcap-mcp-server.toml config file",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Log level",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    cli_overrides: dict = {}
    if args.data_dir is not None:
        cli_overrides["data_dir"] = args.data_dir
    if args.transport is not None:
        cli_overrides["transport"] = args.transport
    if args.port is not None:
        cli_overrides["sse_port"] = args.port
    if args.log_level is not None:
        cli_overrides["log_level"] = args.log_level

    config = load_config(toml_path=args.config, cli_overrides=cli_overrides)
    config.configure_logging()

    server = create_server(config)

    if config.transport == "sse":
        server.run(transport="sse", host="0.0.0.0", port=config.sse_port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
