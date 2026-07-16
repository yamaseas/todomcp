"""MCP server exposing SQLite todo operations."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from mcp_todo.repository import Priority, Todo, TodoRepository, TodoStats

DEFAULT_DATABASE = Path.cwd() / "data" / "todos.db"

mcp = FastMCP(
    "SQLite Todo Demo",
    instructions=(
        "Manage a local todo list. Use list_todos before changing an existing item "
        "so that you have its numeric id."
    ),
    json_response=True,
)


def get_repository() -> TodoRepository:
    """Create a repository using the environment-selected database."""
    return TodoRepository(os.environ.get("MCP_TODO_DB", str(DEFAULT_DATABASE)))


@mcp.tool()
def add_todo(
    title: str,
    description: str = "",
    priority: Priority = "medium",
) -> Todo:
    """Create a todo item and return the stored item with its generated id."""
    return get_repository().add(title, description, priority)


@mcp.tool()
def list_todos(
    status: Literal["all", "pending", "completed"] = "all",
) -> list[Todo]:
    """List todo items, optionally filtered by completion status."""
    return get_repository().list(status)


@mcp.tool()
def complete_todo(todo_id: int) -> Todo:
    """Mark one todo item as completed."""
    return get_repository().complete(todo_id)


@mcp.tool()
def delete_todo(todo_id: int) -> bool:
    """Permanently delete one todo item."""
    return get_repository().delete(todo_id)


@mcp.resource("todo://stats")
def todo_stats() -> str:
    """Return todo counts as a JSON resource."""
    return json.dumps(get_repository().stats().model_dump(), ensure_ascii=False)


@mcp.prompt()
def daily_review(focus: str = "today") -> str:
    """Create a reusable prompt for reviewing the todo list."""
    return (
        f"Review my {focus} tasks. First call list_todos with status='pending', "
        "then group the results by priority and propose an execution order."
    )


def valid_port(value: str) -> int:
    """Parse and validate a TCP port for the command line."""
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def parse_args(
    argv: Sequence[str] | None = None,
    *,
    default_transport: Literal["stdio", "streamable-http"] = "stdio",
) -> argparse.Namespace:
    """Parse server options without starting the MCP transport."""
    parser = argparse.ArgumentParser(description="Run the SQLite Todo MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=default_transport,
        help="MCP transport to use (default: %(default)s)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_TODO_HOST", "127.0.0.1"),
        help="HTTP bind address (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=valid_port,
        default=os.environ.get("MCP_TODO_PORT", "8000"),
        help="HTTP port (default: %(default)s)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="SQLite database path (overrides MCP_TODO_DB)",
    )
    return parser.parse_args(argv)


def run_server(
    argv: Sequence[str] | None = None,
    *,
    default_transport: Literal["stdio", "streamable-http"] = "stdio",
) -> None:
    """Configure and run the selected MCP transport."""
    args = parse_args(argv, default_transport=default_transport)
    if args.db is not None:
        os.environ["MCP_TODO_DB"] = str(args.db.expanduser().resolve())

    if args.transport == "streamable-http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    try:
        mcp.run(transport=args.transport)
    except KeyboardInterrupt:
        # Ctrl+C is the normal way to stop a foreground HTTP development server.
        pass


def main() -> None:
    """Run the server; stdio remains the default for MCP hosts."""
    run_server()


def http_main() -> None:
    """Run the server with Streamable HTTP as the default transport."""
    run_server(default_transport="streamable-http")


if __name__ == "__main__":
    main()
