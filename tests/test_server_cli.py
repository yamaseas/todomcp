import argparse

import pytest

from mcp_todo.server import parse_args


def test_server_cli_defaults_to_stdio():
    args = parse_args([])

    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.db is None


def test_http_entrypoint_defaults_to_streamable_http(tmp_path):
    database = tmp_path / "todos.db"

    args = parse_args(
        ["--host", "0.0.0.0", "--port", "9000", "--db", str(database)],
        default_transport="streamable-http",
    )

    assert args.transport == "streamable-http"
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.db == database


@pytest.mark.parametrize("port", ["0", "65536"])
def test_server_cli_rejects_invalid_ports(port):
    with pytest.raises(SystemExit):
        parse_args(["--port", port])
