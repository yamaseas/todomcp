"""MCP server exposing SQLite todo operations."""

from __future__ import annotations

import json
import os
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


def main() -> None:
    """Run the MCP server over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

