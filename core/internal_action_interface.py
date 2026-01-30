"""
core.internal_action_interface

This interface contains all the agent actions calling to the agent
framework internal functions.
"""

from typing import Dict, Any, Optional, List
from core.llm_interface import LLMInterface
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

    @classmethod
    def initialize(
        cls,
        llm_interface: LLMInterface,
        task_manager: TaskManager,
        state_manager: StateManager,
        vlm_interface: Optional[VLMInterface] = None,
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
    def do_create_task(cls, task_name: str, task_description: str) -> str:
        """
        Create a new task.

        Args:
            task_name: Short name for the task.
            task_description: Detailed description of the work to perform.

        Returns:
            The created task identifier.
        """
        if cls.task_manager is None or cls.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with Task/State managers.")

        task_id = cls.task_manager.create_task(task_name, task_description)
        task: Optional[Task] = cls.task_manager.get_task()
        cls.state_manager.add_to_active_task(task)
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
            ok = await cls.task_manager.mark_task_completed(message=message)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_completed failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def mark_task_cancel(cls, reason: Optional[str] = None) -> Dict[str, Any]:
        """Cancel the current session task."""
        try:
            ok = await cls.task_manager.mark_task_cancel(reason=reason)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_cancel failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def mark_task_error(cls, message: Optional[str] = None) -> Dict[str, Any]:
        """Mark the current session task as failed."""
        try:
            ok = await cls.task_manager.mark_task_error(message=message)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_error failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
