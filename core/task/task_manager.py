# -*- coding: utf-8 -*-
"""
Simplified TaskManager for todo-based task tracking.

This replaces the complex step-based workflow with a simple todo list
mechanism. The agent manages todos directly without LLM-based planning.
"""

import uuid
import shutil
from typing import List, Dict, Any, Optional
from pathlib import Path
import re

from core.task.task import Task
from core.todo.todo import TodoItem
from core.logger import logger
from core.database_interface import DatabaseInterface
from core.event_stream.event_stream_manager import EventStreamManager
from core.config import AGENT_WORKSPACE_ROOT
from core.state.state_manager import StateManager
from core.state.agent_state import STATE


class TaskManager:
    """
    Simplified task manager using todo-based tracking.

    Coordinates task lifecycle without complex step planning or triggers.
    The agent directly manages the todo list via update_todos().
    """

    def __init__(
        self,
        db_interface: DatabaseInterface,
        event_stream_manager: EventStreamManager,
        state_manager: StateManager,
    ):
        """
        Initialize the task manager.

        Args:
            db_interface: Persistence layer for task logging.
            event_stream_manager: Event stream for user-visible progress.
            state_manager: State tracker for sharing task context.
        """
        self.db_interface = db_interface
        self.event_stream_manager = event_stream_manager
        self.state_manager = state_manager
        self.active: Optional[Task] = None
        self.workspace_root = Path(AGENT_WORKSPACE_ROOT)

    def reset(self) -> None:
        """Clear active task state."""
        self.active = None

    # ─────────────────────── Task Creation ───────────────────────────────────

    def create_task(self, task_name: str, task_instruction: str, mode: str = "complex") -> str:
        """
        Create a new task without LLM planning.

        Args:
            task_name: Human-readable identifier for the task.
            task_instruction: Description of the work to be done.
            mode: Task execution mode - "simple" for quick tasks, "complex" for multi-step work.

        Returns:
            The unique task identifier.
        """
        task_id = self._sanitize_task_id(f"{task_name}_{uuid.uuid4().hex[:6]}")
        temp_dir = self._prepare_task_temp_dir(task_id)

        task = Task(
            id=task_id,
            name=task_name,
            instruction=task_instruction,
            mode=mode,
            temp_dir=str(temp_dir),
        )

        self.active = task
        self.db_interface.log_task(task)
        self._sync_state_manager(task)

        self.event_stream_manager.event_stream.temp_dir = temp_dir
        self.event_stream_manager.log(
            "task_start",
            f"Created task: '{task_name}'",
            display_message=task_name,
        )

        STATE.set_agent_property("current_task_id", task_id)
        logger.debug(f"[TaskManager] Task {task_id} created")
        return task_id

    # ─────────────────────── Todo Management ─────────────────────────────────

    def update_todos(self, todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Update the todo list for the active task.

        Called by the agent to add, update, or complete todos.

        Args:
            todos: List of todo dictionaries with content, status, and
                   optional active_form.

        Returns:
            The updated todo list as dictionaries.
        """
        if not self.active:
            logger.warning("[TaskManager] No active task to update todos")
            return []

        self.active.todos = [TodoItem.from_dict(t) for t in todos]
        self.db_interface.log_task(self.active)
        self._sync_state_manager(self.active)

        logger.debug(f"[TaskManager] Updated {len(self.active.todos)} todos")
        return [t.to_dict() for t in self.active.todos]

    def get_todos(self) -> List[Dict[str, Any]]:
        """Get the current todo list as dictionaries."""
        if not self.active:
            return []
        return [t.to_dict() for t in self.active.todos]

    # ─────────────────────── Task Completion ─────────────────────────────────

    async def mark_task_completed(self, message: Optional[str] = None) -> bool:
        """Mark the current task as completed."""
        if not self.active:
            return False
        await self._end_task(self.active, "completed", message)
        return True

    async def mark_task_error(self, message: Optional[str] = None) -> bool:
        """Mark the current task as failed with an error."""
        if not self.active:
            return False
        await self._end_task(self.active, "error", message)
        return True

    async def mark_task_cancel(self, reason: Optional[str] = None) -> bool:
        """Cancel the current task."""
        if not self.active:
            return False
        await self._end_task(self.active, "cancelled", reason)
        return True

    def get_task(self) -> Optional[Task]:
        """Get the currently active task."""
        return self.active

    def is_simple_task(self) -> bool:
        """Check if current task is in simple mode."""
        return self.active is not None and self.active.mode == "simple"

    # ─────────────────────── Internal Helpers ────────────────────────────────

    async def _end_task(self, task: Task, status: str, note: Optional[str]) -> None:
        """Finalize a task with the given status."""
        task.status = status
        self.db_interface.log_task(task)
        self._sync_state_manager(task)

        self.event_stream_manager.log(
            "task_end",
            f"Task ended with status '{status}'. {note or ''}",
            display_message=task.name,
        )

        # Reset agent state
        STATE.set_agent_property("current_task_id", "")
        STATE.set_agent_property("action_count", 0)
        STATE.set_agent_property("token_count", 0)

        # Clear active task
        self.active = None
        if self.state_manager:
            self.state_manager.remove_active_task()

        # Cleanup temp directory on successful completion
        if status == "completed":
            self._cleanup_task_temp_dir(task)

    def _sync_state_manager(self, task: Optional[Task]) -> None:
        """Sync task state to the state manager."""
        if self.state_manager:
            self.state_manager.add_to_active_task(task=task)

    def _prepare_task_temp_dir(self, task_id: str) -> Path:
        """Create a temporary directory for the task."""
        temp_root = self.workspace_root / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        task_temp_dir = temp_root / task_id
        task_temp_dir.mkdir(parents=True, exist_ok=True)
        return task_temp_dir

    def _cleanup_task_temp_dir(self, task: Task) -> None:
        """Remove the task's temporary directory."""
        if not task.temp_dir:
            return
        try:
            shutil.rmtree(task.temp_dir, ignore_errors=True)
            logger.debug(f"[TaskManager] Cleaned up temp dir for task {task.id}")
        except Exception:
            logger.warning(f"[TaskManager] Failed to clean temp dir for {task.id}", exc_info=True)

    def _sanitize_task_id(self, s: str) -> str:
        """Sanitize a string for use as a task ID."""
        s = s.strip()
        s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
        s = re.sub(r"_+", "_", s)
        return s.strip("._-") or "task"
