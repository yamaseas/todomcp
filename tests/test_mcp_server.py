from collections.abc import AsyncGenerator

import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_todo.server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client_session(tmp_path, monkeypatch) -> AsyncGenerator[ClientSession, None]:
    monkeypatch.setenv("MCP_TODO_DB", str(tmp_path / "mcp-todos.db"))
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as session:
        yield session


@pytest.mark.anyio
async def test_server_advertises_expected_primitives(client_session):
    tools = await client_session.list_tools()
    resources = await client_session.list_resources()
    prompts = await client_session.list_prompts()

    assert {tool.name for tool in tools.tools} == {
        "add_todo",
        "list_todos",
        "complete_todo",
        "delete_todo",
    }
    assert [str(resource.uri) for resource in resources.resources] == ["todo://stats"]
    assert [prompt.name for prompt in prompts.prompts] == ["daily_review"]


@pytest.mark.anyio
async def test_tool_calls_round_trip_through_mcp(client_session):
    created = await client_session.call_tool(
        "add_todo", {"title": "Integration test", "priority": "high"}
    )
    todo_id = created.structuredContent["id"]

    listed = await client_session.call_tool("list_todos", {"status": "pending"})
    assert listed.isError is False
    assert listed.structuredContent["result"][0]["title"] == "Integration test"

    completed = await client_session.call_tool(
        "complete_todo", {"todo_id": todo_id}
    )
    assert completed.structuredContent["status"] == "completed"

    stats = await client_session.read_resource("todo://stats")
    assert stats.contents[0].text == '{"total": 1, "pending": 0, "completed": 1}'


@pytest.mark.anyio
async def test_invalid_tool_arguments_are_protocol_errors(client_session):
    result = await client_session.call_tool(
        "add_todo", {"title": "Task", "priority": "urgent"}
    )

    assert result.isError is True

