"""
core.internal_action_interface

This interface contains all the agent actions calling to the agent
framework internal functions.
"""

from typing import Dict, Any, Optional, List, TYPE_CHECKING
from core.llm_interface import LLMInterface, LLMCallType
from core.vlm_interface import VLMInterface
from core.task.task_manager import TaskManager
from core.task.task import Task
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from datetime import datetime
from core.logger import logger
from pathlib import Path
from core.config import AGENT_WORKSPACE_ROOT
import mss, mss.tools, os

if TYPE_CHECKING:
    from core.context_engine import ContextEngine


class InternalActionInterface:
    """
    Provides static/class methods so it can be used without instantiation.
    Allow agent to access internal functions of the WhiteCollarAgent framework
    via actions.
    """

    # Class-level references
    llm_interface: Optional[LLMInterface] = None
    task_manager: Optional[TaskManager] = None
    state_manager: Optional[StateManager] = None
    vlm_interface: Optional[VLMInterface] = None
    context_engine: Optional["ContextEngine"] = None

    @classmethod
    def initialize(
        cls,
        llm_interface: LLMInterface,
        task_manager: TaskManager,
        state_manager: StateManager,
        vlm_interface: Optional[VLMInterface] = None,
        context_engine: Optional["ContextEngine"] = None,
    ):
        """
        Register the shared interfaces that actions depend on.

        This must be called once at application startup so later static calls can
        access the language model, task manager, state manager, and optional
        vision model without creating new instances.
        """
        cls.llm_interface = llm_interface
        cls.task_manager = task_manager
        cls.state_manager = state_manager
        cls.vlm_interface = vlm_interface
        cls.context_engine = context_engine

    # ─────────────────────── LLM Access for Actions ───────────────────────

    @classmethod
    def use_llm(cls, prompt: str, system_message: Optional[str] = None) -> Dict[str, Any]:
        """Generate a response from the configured LLM."""
        if cls.llm_interface is None:
            raise RuntimeError("InternalActionInterface not initialized with LLMInterface.")
        response = cls.llm_interface.generate_response(prompt, system_message)
        return {"llm_response": response}

    @classmethod
    def describe_image(cls, image_path: str, prompt: Optional[str] = None) -> str:
        """Produce a textual description for an image using the VLM."""
        if cls.vlm_interface is None:
            raise RuntimeError("InternalActionInterface not initialized with VLMInterface.")
        return cls.vlm_interface.describe_image(image_path, user_prompt=prompt)

    # ─────────────────────── GUI Actions ───────────────────────

    @classmethod
    def describe_screen(cls) -> Dict[str, str]:
        """Capture the current virtual desktop and describe it with the VLM."""
        if cls.vlm_interface is None:
            raise RuntimeError("InternalActionInterface not initialised with VLMInterface.")

        temp_dir = Path(AGENT_WORKSPACE_ROOT)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        img_path = os.path.join(temp_dir, f"viewscreen_{ts}.png")

        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            mss.tools.to_png(shot.rgb, shot.size, output=img_path)

        description = cls.describe_image(img_path)
        return {"description": description, "file_path": img_path}

    @staticmethod
    async def do_chat(message: str) -> None:
        """Record an agent-authored chat message to the event stream."""
        if InternalActionInterface.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with StateManager.")
        InternalActionInterface.state_manager.record_agent_message(message)

    @staticmethod
    def do_ignore():
        """Note that the agent chose to ignore the latest user input."""
        logger.debug("[Agent Action] Ignoring user message.")

    # ───────────────── CLI and GUI mode ─────────────────

    @staticmethod
    def switch_to_CLI_mode():
        STATE.update_gui_mode(False)

    @staticmethod
    def switch_to_GUI_mode():
        STATE.update_gui_mode(True)

    # ───────────────── Task Management ─────────────────

    @classmethod
    def do_create_task(cls, task_name: str, task_description: str, task_mode: str = "complex") -> str:
        """
        Create a new task.

        Args:
            task_name: Short name for the task.
            task_description: Detailed description of the work to perform.
            task_mode: Task execution mode - "simple" for quick tasks, "complex" for multi-step work.

        Returns:
            The created task identifier.
        """
        if cls.task_manager is None or cls.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with Task/State managers.")

        task_id = cls.task_manager.create_task(task_name, task_description, mode=task_mode)
        task: Optional[Task] = cls.task_manager.get_task()
        cls.state_manager.add_to_active_task(task)

        # Create session caches for complex tasks only (expensive operation, skip for simple tasks)
        if task_mode == "complex" and cls.llm_interface and cls.context_engine:
            try:
                # Generate the static system prompt for the session
                system_prompt, _ = cls.context_engine.make_prompt(
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
                    cache_id = cls.llm_interface.create_session_cache(task_id, call_type, system_prompt)
                    if cache_id:
                        logger.debug(f"[TASK] Created session cache {cache_id} for task {task_id}:{call_type}")
            except Exception as e:
                logger.warning(f"[TASK] Failed to create session caches for task {task_id}: {e}")

        return task_id

    @classmethod
    def update_todos(cls, todos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update the todo list for the current task.

        Args:
            todos: List of todo dictionaries with content, status, and
                   optional active_form.

        Returns:
            Status and the updated todo list.
        """
        if cls.task_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with TaskManager.")

        updated_todos = cls.task_manager.update_todos(todos)
        return {"status": "ok", "todos": updated_todos}

    @classmethod
    async def mark_task_completed(cls, message: Optional[str] = None) -> Dict[str, Any]:
        """Mark the current session task as completed."""
        try:
            # Get task_id before marking as completed (task will be cleared)
            task_id = cls._get_current_task_id()
            ok = await cls.task_manager.mark_task_completed(message=message)
            # End session cache if task was successfully completed
            if ok and task_id:
                cls._end_task_session_cache(task_id)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_completed failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def mark_task_cancel(cls, reason: Optional[str] = None) -> Dict[str, Any]:
        """Cancel the current session task."""
        try:
            # Get task_id before marking as cancelled (task will be cleared)
            task_id = cls._get_current_task_id()
            ok = await cls.task_manager.mark_task_cancel(reason=reason)
            # End session cache if task was successfully cancelled
            if ok and task_id:
                cls._end_task_session_cache(task_id)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_cancel failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def mark_task_error(cls, message: Optional[str] = None) -> Dict[str, Any]:
        """Mark the current session task as failed."""
        try:
            # Get task_id before marking as error (task will be cleared)
            task_id = cls._get_current_task_id()
            ok = await cls.task_manager.mark_task_error(message=message)
            # End session cache if task was successfully marked as error
            if ok and task_id:
                cls._end_task_session_cache(task_id)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_error failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    def _get_current_task_id(cls) -> Optional[str]:
        """Get the current task ID from the task manager."""
        if cls.task_manager:
            task = cls.task_manager.get_task()
            if task:
                return task.id
        return None

    @classmethod
    def _end_task_session_cache(cls, task_id: str) -> None:
        """End ALL session caches for a task (all call types)."""
        if cls.llm_interface:
            try:
                cls.llm_interface.end_all_session_caches(task_id)
                logger.debug(f"[TASK] Ended all session caches for task {task_id}")
            except Exception as e:
                logger.warning(f"[TASK] Failed to end session caches for task {task_id}: {e}")
