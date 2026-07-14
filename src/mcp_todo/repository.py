"""SQLite persistence for todo items.

This module deliberately knows nothing about MCP. Keeping persistence separate
makes the domain logic easy to test and lets the MCP server remain a thin
protocol adapter.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Priority = Literal["low", "medium", "high"]
TodoStatus = Literal["pending", "completed"]


class Todo(BaseModel):
    """A todo item returned to MCP clients."""

    id: int
    title: str
    description: str
    priority: Priority
    status: TodoStatus
    created_at: str
    completed_at: str | None


class TodoStats(BaseModel):
    """Aggregate todo counts."""

    total: int
    pending: int
    completed: int


class TodoRepository:
    """Small repository backed by one SQLite database file."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

    @staticmethod
    def _row_to_todo(row: sqlite3.Row) -> Todo:
        return Todo.model_validate(dict(row))

    def add(self, title: str, description: str = "", priority: Priority = "medium") -> Todo:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title must not be empty")

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO todos (title, description, priority, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (clean_title, description.strip(), priority, now),
            )
            row = connection.execute(
                "SELECT * FROM todos WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        assert row is not None
        return self._row_to_todo(row)

    def list(self, status: Literal["all", "pending", "completed"] = "all") -> list[Todo]:
        query = "SELECT * FROM todos"
        parameters: tuple[str, ...] = ()
        if status != "all":
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY id"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_todo(row) for row in rows]

    def complete(self, todo_id: int) -> Todo:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE todos
                SET status = 'completed', completed_at = ?
                WHERE id = ?
                """,
                (now, todo_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"todo {todo_id} does not exist")
            row = connection.execute(
                "SELECT * FROM todos WHERE id = ?", (todo_id,)
            ).fetchone()
        assert row is not None
        return self._row_to_todo(row)

    def delete(self, todo_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"todo {todo_id} does not exist")
        return True

    def stats(self) -> TodoStats:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
                FROM todos
                """
            ).fetchone()
        assert row is not None
        return TodoStats(
            total=row["total"],
            pending=row["pending"] or 0,
            completed=row["completed"] or 0,
        )

