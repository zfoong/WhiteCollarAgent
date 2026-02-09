# -*- coding: utf-8 -*-
"""
Simplified TaskManager for todo-based task tracking.

This replaces the complex step-based workflow with a simple todo list
mechanism. The agent manages todos directly without LLM-based planning.
"""

import uuid
import shutil
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
import re

from core.task.task import Task
from core.todo.todo import TodoItem
from core.logger import logger
from core.database_interface import DatabaseInterface
from core.event_stream.event_stream_manager import EventStreamManager
from core.config import AGENT_WORKSPACE_ROOT, AGENT_FILE_SYSTEM_PATH
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from core.llm import LLMCallType

if TYPE_CHECKING:
    from core.llm import LLMInterface
    from core.context_engine import ContextEngine


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
        llm_interface: Optional["LLMInterface"] = None,
        context_engine: Optional["ContextEngine"] = None,
    ):
        """
        Initialize the task manager.

        Args:
            db_interface: Persistence layer for task logging.
            event_stream_manager: Event stream for user-visible progress.
            state_manager: State tracker for sharing task context.
            llm_interface: LLM interface for creating session caches (optional).
            context_engine: Context engine for generating system prompts (optional).
        """
        self.db_interface = db_interface
        self.event_stream_manager = event_stream_manager
        self.state_manager = state_manager
        self.llm_interface = llm_interface
        self.context_engine = context_engine
        self.active: Optional[Task] = None
        self.workspace_root = Path(AGENT_WORKSPACE_ROOT)

    def reset(self) -> None:
        """Clear active task state."""
        self.active = None

    # ─────────────────────── Task Creation ───────────────────────────────────

    def create_task(
        self,
        task_name: str,
        task_instruction: str,
        mode: str = "complex",
        action_sets: Optional[List[str]] = None,
        selected_skills: Optional[List[str]] = None
    ) -> str:
        """
        Create a new task without LLM planning.

        Args:
            task_name: Human-readable identifier for the task.
            task_instruction: Description of the work to be done.
            mode: Task execution mode - "simple" for quick tasks, "complex" for multi-step work.
            action_sets: List of action set names to enable for this task
                         (e.g., ["file_operations", "web_research"]).
                         The "core" set is always included automatically.
            selected_skills: List of skill names selected for this task.
                             Their instructions will be injected into context.

        Returns:
            The unique task identifier.
        """
        task_id = self._sanitize_task_id(f"{task_name}_{uuid.uuid4().hex[:6]}")
        temp_dir = self._prepare_task_temp_dir(task_id)

        # Compile action list from selected sets
        compiled_actions: List[str] = []
        selected_sets = action_sets or []
        if selected_sets:
            from core.action.action_set import action_set_manager
            # Determine mode for action visibility filtering
            visibility_mode = "GUI" if STATE.gui_mode else "CLI"
            compiled_actions = action_set_manager.compile_action_list(
                selected_sets, mode=visibility_mode
            )
            logger.debug(f"[TaskManager] Compiled {len(compiled_actions)} actions from sets: {selected_sets}")

        task = Task(
            id=task_id,
            name=task_name,
            instruction=task_instruction,
            mode=mode,
            temp_dir=str(temp_dir),
            action_sets=selected_sets,
            compiled_actions=compiled_actions,
            selected_skills=selected_skills or [],
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

        # Create session caches for all tasks (enables efficient multi-turn execution)
        if self.llm_interface and self.context_engine:
            self._create_session_caches(task_id)

        logger.debug(f"[TaskManager] Task {task_id} created")
        return task_id

    def _create_session_caches(self, task_id: str) -> None:
        """
        Create session caches for a task.

        Session caches enable efficient multi-turn LLM interactions by caching
        the static parts of prompts. Each call type gets its own session to
        prevent KV cache pollution. Used for both simple and complex tasks.

        Args:
            task_id: The task ID to create caches for.
        """
        try:
            # Generate the static system prompt for the session
            system_prompt, _ = self.context_engine.make_prompt(
                user_flags={"query": False, "expected_output": False},
                system_flags={"policy": False},
            )
            # Create a session cache for EACH call type so they don't pollute each other's KV cache
            for call_type in [
                LLMCallType.REASONING,
                LLMCallType.ACTION_SELECTION,
                LLMCallType.GUI_REASONING,
                LLMCallType.GUI_ACTION_SELECTION,
            ]:
                cache_id = self.llm_interface.create_session_cache(task_id, call_type, system_prompt)
                if cache_id:
                    logger.debug(f"[TaskManager] Created session cache {cache_id} for task {task_id}:{call_type}")
        except Exception as e:
            logger.warning(f"[TaskManager] Failed to create session caches for task {task_id}: {e}")

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

    async def mark_task_completed(
        self,
        message: Optional[str] = None,
        summary: Optional[str] = None,
        errors: Optional[List[str]] = None
    ) -> bool:
        """Mark the current task as completed."""
        if not self.active:
            return False
        await self._end_task(self.active, "completed", message, summary, errors)
        return True

    async def mark_task_error(
        self,
        message: Optional[str] = None,
        summary: Optional[str] = None,
        errors: Optional[List[str]] = None
    ) -> bool:
        """Mark the current task as failed with an error."""
        if not self.active:
            return False
        await self._end_task(self.active, "error", message, summary, errors)
        return True

    async def mark_task_cancel(
        self,
        reason: Optional[str] = None,
        summary: Optional[str] = None,
        errors: Optional[List[str]] = None
    ) -> bool:
        """Cancel the current task."""
        if not self.active:
            return False
        await self._end_task(self.active, "cancelled", reason, summary, errors)
        return True

    def get_task(self) -> Optional[Task]:
        """Get the currently active task."""
        return self.active

    def is_simple_task(self) -> bool:
        """Check if current task is in simple mode."""
        return self.active is not None and self.active.mode == "simple"

    # ─────────────────────── Action Set Management ───────────────────────────

    def add_action_sets(self, sets_to_add: List[str]) -> Dict[str, Any]:
        """
        Add action sets to the current task and recompile the action list.

        Args:
            sets_to_add: List of action set names to add.

        Returns:
            Dictionary with success status, current sets, and added actions.
        """
        if not self.active:
            return {"success": False, "error": "No active task"}

        from core.action.action_set import action_set_manager

        # Add new sets (deduplicate)
        current_sets = set(self.active.action_sets)
        new_sets = set(sets_to_add) - current_sets
        self.active.action_sets = list(current_sets | new_sets)

        # Recompile action list
        visibility_mode = "GUI" if STATE.gui_mode else "CLI"
        old_actions = set(self.active.compiled_actions)
        self.active.compiled_actions = action_set_manager.compile_action_list(
            self.active.action_sets, mode=visibility_mode
        )
        new_actions = set(self.active.compiled_actions) - old_actions

        # Sync state
        self._sync_state_manager(self.active)

        logger.debug(f"[TaskManager] Added action sets {sets_to_add}, now have {len(self.active.compiled_actions)} actions")
        return {
            "success": True,
            "current_sets": self.active.action_sets,
            "added_actions": list(new_actions),
            "total_actions": len(self.active.compiled_actions),
        }

    def remove_action_sets(self, sets_to_remove: List[str]) -> Dict[str, Any]:
        """
        Remove action sets from the current task and recompile the action list.

        Args:
            sets_to_remove: List of action set names to remove.
                            The "core" set cannot be removed.

        Returns:
            Dictionary with success status and current sets.
        """
        if not self.active:
            return {"success": False, "error": "No active task"}

        from core.action.action_set import action_set_manager

        # Remove sets (but never remove 'core')
        sets_to_remove_filtered = [s for s in sets_to_remove if s != "core"]
        current_sets = set(self.active.action_sets)
        self.active.action_sets = list(current_sets - set(sets_to_remove_filtered))

        # Recompile action list
        visibility_mode = "GUI" if STATE.gui_mode else "CLI"
        old_actions = set(self.active.compiled_actions)
        self.active.compiled_actions = action_set_manager.compile_action_list(
            self.active.action_sets, mode=visibility_mode
        )
        removed_actions = old_actions - set(self.active.compiled_actions)

        # Sync state
        self._sync_state_manager(self.active)

        logger.debug(f"[TaskManager] Removed action sets {sets_to_remove_filtered}, now have {len(self.active.compiled_actions)} actions")
        return {
            "success": True,
            "current_sets": self.active.action_sets,
            "removed_actions": list(removed_actions),
            "total_actions": len(self.active.compiled_actions),
        }

    def get_action_sets(self) -> List[str]:
        """Get the current action sets for the active task."""
        if not self.active:
            return []
        return self.active.action_sets.copy()

    def get_compiled_actions(self) -> List[str]:
        """Get the compiled action list for the active task."""
        if not self.active:
            return []
        return self.active.compiled_actions.copy()

    # ─────────────────────── Internal Helpers ────────────────────────────────

    async def _end_task(
        self,
        task: Task,
        status: str,
        note: Optional[str],
        summary: Optional[str] = None,
        errors: Optional[List[str]] = None
    ) -> None:
        """Finalize a task with the given status."""
        from datetime import datetime

        task.status = status
        task.ended_at = datetime.utcnow().isoformat()
        task.final_summary = summary
        task.errors = errors or []

        self.db_interface.log_task(task)
        self._sync_state_manager(task)

        self.event_stream_manager.log(
            "task_end",
            f"Task ended with status '{status}'. {note or ''}",
            display_message=task.name,
        )

        # Log to TASK_HISTORY.md
        self._log_to_task_history(task, note)

        # Reset skip_unprocessed_logging flag (may have been set during memory processing)
        if hasattr(self.event_stream_manager, 'set_skip_unprocessed_logging'):
            self.event_stream_manager.set_skip_unprocessed_logging(False)

        # Reset agent state
        STATE.set_agent_property("current_task_id", "")
        STATE.set_agent_property("action_count", 0)
        STATE.set_agent_property("token_count", 0)

        # Clear active task
        self.active = None
        if self.state_manager:
            self.state_manager.remove_active_task()

        # Cleanup temp directory on task end (completed, error, or cancelled)
        self._cleanup_task_temp_dir(task)

    def _sync_state_manager(self, task: Optional[Task]) -> None:
        """Sync task state to the state manager."""
        if self.state_manager:
            self.state_manager.add_to_active_task(task=task)

    def _log_to_task_history(self, task: Task, note: Optional[str] = None) -> None:
        """
        Log completed task to TASK_HISTORY.md.

        Appends task information including ID, status, timestamps, errors, and summary
        to the agent file system's TASK_HISTORY.md file.

        Args:
            task: The completed task to log.
            note: Optional note/reason for task completion.
        """
        try:
            task_history_path = AGENT_FILE_SYSTEM_PATH / "TASK_HISTORY.md"

            if not task_history_path.exists():
                logger.warning(f"[TaskManager] TASK_HISTORY.md not found at {task_history_path}")
                return

            # Format the task history entry
            entry_lines = [
                f"### Task: {task.name}",
                f"- **Task ID:** `{task.id}`",
                f"- **Status:** {task.status}",
                f"- **Created:** {task.created_at}",
                f"- **Ended:** {task.ended_at}",
            ]

            # Add errors if any
            if task.errors:
                entry_lines.append("- **Errors:**")
                for error in task.errors:
                    entry_lines.append(f"  - {error}")

            # Add summary
            if task.final_summary:
                entry_lines.append(f"- **Summary:** {task.final_summary}")
            elif note:
                entry_lines.append(f"- **Summary:** {note}")

            # Add instruction for context
            if task.instruction:
                entry_lines.append(f"- **Instruction:** {task.instruction}")

            # Add skills used
            if task.selected_skills:
                entry_lines.append(f"- **Skills:** {', '.join(task.selected_skills)}")

            # Add action sets used
            if task.action_sets:
                entry_lines.append(f"- **Action Sets:** {', '.join(task.action_sets)}")

            entry_lines.append("")  # Empty line separator

            # Append to file
            with open(task_history_path, "a", encoding="utf-8") as f:
                f.write("\n".join(entry_lines) + "\n")

            logger.debug(f"[TaskManager] Logged task {task.id} to TASK_HISTORY.md")

        except Exception as e:
            logger.warning(f"[TaskManager] Failed to log task to TASK_HISTORY.md: {e}")

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

    def cleanup_all_temp_dirs(self) -> int:
        """
        Remove all temporary directories in workspace/tmp/.

        This should be called on agent startup to clean up any leftover
        temp directories from tasks that ended unexpectedly (e.g., due to
        crashes or forced termination).

        Returns:
            Number of directories cleaned up.
        """
        temp_root = self.workspace_root / "tmp"
        if not temp_root.exists():
            return 0

        cleaned_count = 0
        try:
            for item in temp_root.iterdir():
                if item.is_dir():
                    try:
                        shutil.rmtree(item, ignore_errors=True)
                        cleaned_count += 1
                        logger.debug(f"[TaskManager] Cleaned up leftover temp dir: {item.name}")
                    except Exception:
                        logger.warning(f"[TaskManager] Failed to clean leftover temp dir: {item.name}", exc_info=True)

            if cleaned_count > 0:
                logger.info(f"[TaskManager] Cleaned up {cleaned_count} leftover temp directories on startup")
        except Exception:
            logger.warning("[TaskManager] Failed to enumerate temp directories", exc_info=True)

        return cleaned_count

    def _sanitize_task_id(self, s: str) -> str:
        """Sanitize a string for use as a task ID."""
        s = s.strip()
        s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
        s = re.sub(r"_+", "_", s)
        return s.strip("._-") or "task"
