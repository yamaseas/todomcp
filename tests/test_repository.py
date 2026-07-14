import pytest

from mcp_todo.repository import TodoRepository


@pytest.fixture
def repository(tmp_path):
    return TodoRepository(tmp_path / "todos.db")


def test_add_and_list_todos(repository):
    first = repository.add("  Learn MCP  ", "Read the specification", "high")
    second = repository.add("Write tests")

    assert first.id == 1
    assert first.title == "Learn MCP"
    assert first.priority == "high"
    assert [todo.id for todo in repository.list()] == [first.id, second.id]
    assert len(repository.list("pending")) == 2
    assert repository.list("completed") == []


def test_complete_and_stats(repository):
    todo = repository.add("Ship demo")

    completed = repository.complete(todo.id)

    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert repository.stats().model_dump() == {
        "total": 1,
        "pending": 0,
        "completed": 1,
    }


def test_delete_todo(repository):
    todo = repository.add("Temporary task")

    assert repository.delete(todo.id) is True
    assert repository.list() == []


@pytest.mark.parametrize("action", ["complete", "delete"])
def test_missing_todo_is_rejected(repository, action):
    with pytest.raises(ValueError, match="does not exist"):
        getattr(repository, action)(999)


def test_empty_title_is_rejected(repository):
    with pytest.raises(ValueError, match="must not be empty"):
        repository.add("   ")

