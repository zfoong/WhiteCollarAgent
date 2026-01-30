# -*- coding: utf-8 -*-
"""
Task dataclass for simple task management.

This simplified version removes the complex Step-based workflow
and uses a simple todo list mechanism instead.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.todo.todo import TodoItem


@dataclass
class Task:
    """
    A task representing work to be done by the agent.

    Attributes:
        id: Unique identifier for the task
        name: Human-readable name for the task
        instruction: The original user instruction/request
        todos: List of todo items for tracking progress
        temp_dir: Temporary workspace directory for the task
        created_at: ISO timestamp when the task was created
        status: Current state - running, completed, error, paused, or cancelled
    """
    id: str
    name: str
    instruction: str
    todos: List[TodoItem] = field(default_factory=list)
    temp_dir: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Allowed: running | completed | error | paused | cancelled
    status: str = "running"

    def get_current_todo(self) -> Optional[TodoItem]:
        """
        Return the todo item that should be worked on next.

        First looks for any todo marked as in_progress, then falls back
        to the first pending todo. Returns None if all todos are completed.
        """
        # Prefer explicitly marked in_progress
        for todo in self.todos:
            if todo.status == "in_progress":
                return todo
        # Fallback to first pending
        for todo in self.todos:
            if todo.status == "pending":
                return todo
        return None

    def all_todos_completed(self) -> bool:
        """Check if all todos are completed."""
        if not self.todos:
            return True
        return all(t.status == "completed" for t in self.todos)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the task."""
        return {
            "id": self.id,
            "name": self.name,
            "instruction": self.instruction,
            "status": self.status,
            "todos": [todo.to_dict() for todo in self.todos],
        }
