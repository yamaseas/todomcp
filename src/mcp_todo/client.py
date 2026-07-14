"""Minimal MCP client that launches and talks to the todo server over stdio."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def structured(result: Any) -> Any:
    """Return a call's structured payload across SDK naming conventions."""
    return result.structuredContent


async def run_demo(database: Path) -> None:
    environment = os.environ.copy()
    environment["MCP_TODO_DB"] = str(database)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_todo.server"],
        env=environment,
    )

    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Server tools:", ", ".join(tool.name for tool in tools.tools))

            created = await session.call_tool(
                "add_todo",
                {
                    "title": "Learn MCP",
                    "description": "Run the client and inspect the protocol flow",
                    "priority": "high",
                },
            )
            created_data = structured(created)
            print("Created:", json.dumps(created_data, ensure_ascii=False))

            listed = await session.call_tool("list_todos", {"status": "pending"})
            print("Pending:", json.dumps(structured(listed), ensure_ascii=False))

            todo_id = created_data["id"]
            completed = await session.call_tool("complete_todo", {"todo_id": todo_id})
            print("Completed:", json.dumps(structured(completed), ensure_ascii=False))

            resource = await session.read_resource("todo://stats")
            print("Stats resource:", resource.contents[0].text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MCP todo client demo")
    parser.add_argument(
        "--db",
        type=Path,
        help="SQLite file to use; omitted means a temporary demo database",
    )
    args = parser.parse_args()

    if args.db:
        asyncio.run(run_demo(args.db.resolve()))
    else:
        with tempfile.TemporaryDirectory(prefix="mcp-todo-") as directory:
            asyncio.run(run_demo(Path(directory) / "todos.db"))


if __name__ == "__main__":
    main()

