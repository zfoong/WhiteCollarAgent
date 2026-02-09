from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from core.state.types import AgentProperties
from core.state.agent_state import STATE
from core.event_stream.event_stream_manager import EventStreamManager
from core.task.task import Task
from core.todo.todo import TodoItem
from core.logger import logger
from core.config import AGENT_FILE_SYSTEM_PATH


class StateManager:
    """Manages task state and runtime session data."""

    def __init__(
        self,
        event_stream_manager: EventStreamManager,
    ):
        # We have two types of state, persistant and session state
        # Persistant state are state that will not be changed frequently,
        # e.g. agent properties
        # Session state are states that is short-termed, one time used
        # e.g. current task, event stream, action state
        self.task: Optional[Task] = None
        self.event_stream_manager = event_stream_manager

    async def start_session(self, gui_mode: bool = False):
        event_stream = self.get_event_stream_snapshot()
        current_task: Optional[Task] = self.get_current_task_state()

        logger.debug(f"[CURRENT TASK]: this is the current_task: {current_task}")

        STATE.refresh(
            current_task=current_task,
            event_stream=event_stream,
            gui_mode=gui_mode
        )

    def clean_state(self):
        """
        End the session, clearing session context so the next user input starts fresh.
        """
        STATE.refresh()

    def reset(self) -> None:
        """Fully reset runtime state, including tasks and session context."""
        self.task = None
        STATE.agent_properties: AgentProperties = AgentProperties(
            current_task_id="", action_count=0
        )
        if self.event_stream_manager:
            self.event_stream_manager.clear_all()
        self.clean_state()

    def _append_to_conversation_history(self, sender: str, content: str) -> None:
        """
        Append a message to CONVERSATION_HISTORY.md with timestamp.

        Format: [YYYY/MM/DD HH:MM:SS] [sender]: message

        Args:
            sender: Either "user" or "agent"
            content: The message content
        """
        try:
            conversation_file = Path(AGENT_FILE_SYSTEM_PATH) / "CONVERSATION_HISTORY.md"
            timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            entry = f"[{timestamp}] [{sender}]: {content}\n"

            with open(conversation_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"[STATE] Failed to append to conversation history: {e}")

    def record_user_message(self, content: str) -> None:
        """Record a user message to the event stream and conversation history."""
        self.event_stream_manager.log(
            "user message",
            content,
            display_message=content
        )
        self.bump_event_stream()
        self._append_to_conversation_history("user", content)

    def record_agent_message(self, content: str) -> None:
        """Record an agent message to the event stream and conversation history."""
        self.event_stream_manager.log(
            "agent message",
            content,
            display_message=content
        )
        self.bump_event_stream()
        self._append_to_conversation_history("agent", content)

    def get_current_todo(self) -> Optional[TodoItem]:
        """Get the current todo item from the active task."""
        task: Optional[Task] = self.task
        if not task:
            return None
        return task.get_current_todo()

    def get_event_stream_snapshot(self) -> str:
        return self.event_stream_manager.snapshot()

    def get_current_task_state(self) -> Optional[Task]:
        """Get the current task state for context."""
        task: Optional[Task] = self.task

        logger.debug(f"[TASK] task in StateManager: {task}")

        if not task:
            logger.debug("[TASK] task not found in StateManager")
            return None

        return task

    def bump_task_state(self) -> None:
        STATE.update_current_task(self.get_current_task_state())

    def bump_event_stream(self) -> None:
        STATE.update_event_stream(self.get_event_stream_snapshot())

    def is_running_task(self) -> bool:
        return self.task is not None

    def add_to_active_task(self, task: Optional[Task]) -> None:
        if task is None:
            self.task = None
            STATE.update_current_task(None)
        else:
            self.task = task
            self.bump_task_state()

    def remove_active_task(self) -> None:
        self.task = None
        STATE.update_current_task(None)
