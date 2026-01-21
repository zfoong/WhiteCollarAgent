"""
core.internal_action_interface

This interface contains all the agent actions calling to the agent
framework internal functions. Most functions are not implemented yet.
"""

from typing import Dict, Any, Optional
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

    # Class-level references for LLM
    llm_interface: Optional[LLMInterface] = None
    task_manager: Optional[TaskManager] = None
    state_manager: Optional[StateManager] = None
    vlm_interface: Optional[VLMInterface] = None

    @classmethod
    def initialize(cls, llm_interface: LLMInterface,
                   task_manager: TaskManager, state_manager: StateManager,
                   vlm_interface: VLMInterface | None = None):
        """
        Register the shared interfaces that actions depend on.

        This must be called once at application startup so later static calls can
        access the language model, task manager, state manager, and optional
        vision model without creating new instances.

        Args:
            llm_interface: Core large language model interface for text
                generation and reasoning.
            task_manager: Orchestrates task creation, execution, and state
                updates.
            state_manager: Persists session state and provides access to event
                streams and agent properties.
            vlm_interface: Optional vision-language model interface used for
                image understanding and screen descriptions.
        """
        cls.llm_interface = llm_interface
        cls.task_manager = task_manager
        cls.state_manager = state_manager
        cls.vlm_interface = vlm_interface

    # ─────────────────────── LLM Access for Actions ───────────────────────
    @classmethod
    def use_llm(cls, prompt: str, system_message: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a response from the configured LLM.

        Args:
            prompt: User or agent prompt sent to the language model.
            system_message: Optional system instructions to steer the response
                style or constraints.

        Returns:
            A mapping containing the key ``"llm_response"`` with the model
            output.

        Raises:
            RuntimeError: If the interface has not been initialised with an
                :class:`LLMInterface`.
        """
        if cls.llm_interface is None:
            raise RuntimeError("InternalActionInterface not initialized with LLMInterface.")
        response = cls.llm_interface.generate_response(prompt, system_message)
        return {"llm_response": response}
    
    @classmethod
    def describe_image(cls, image_path: str, prompt: str | None = None) -> str:
        """
        Produce a textual description for an image using the VLM.

        Args:
            image_path: Absolute path to the image to describe.
            prompt: Optional user prompt to guide the vision-language model.

        Returns:
            A natural-language description returned by the VLM.

        Raises:
            RuntimeError: If no :class:`VLMInterface` was configured during
                initialization.
        """
        if cls.vlm_interface is None:
            raise RuntimeError("InternalActionInterface not initialized with VLMInterface.")
        return cls.vlm_interface.describe_image(image_path, user_prompt=prompt)
    
    # ─────────────────────── GUI Actions ───────────────────────
    
    @classmethod
    def describe_screen(cls) -> dict[str, str]:
        """
        Capture the current virtual desktop and describe it with the VLM.

        The screen is saved to a timestamped PNG inside the agent workspace and
        then passed to the vision model for summarisation.

        Returns:
            A mapping with the VLM description under ``"description"`` and the
            saved screenshot path under ``"file_path"``.

        Raises:
            RuntimeError: If no :class:`VLMInterface` is available.
        """
        if cls.vlm_interface is None:
            raise RuntimeError("InternalActionInterface not initialised with VLMInterface.")
    
        temp_dir = Path(AGENT_WORKSPACE_ROOT)
        ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        img_path = os.path.join(temp_dir, f"viewscreen_{ts}.png")
    
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])          # full virtual desktop
            mss.tools.to_png(shot.rgb, shot.size, output=img_path)
    
        description = cls.describe_image(img_path)    # default VLM prompt
        return {"description": description, "file_path": img_path}

    @staticmethod
    async def do_chat(
        message: str,
    ) -> None:
        """
        Record an agent-authored chat message and publish it to the event stream.

        Args:
            message: Text content the agent wants to send to the user or log.

        Raises:
            RuntimeError: If the state manager has not been configured.
        """
        if InternalActionInterface.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with StateManager.")

        InternalActionInterface.state_manager.record_agent_message(message)

        event_stream_manager = InternalActionInterface.state_manager.event_stream_manager
        event_stream_manager.log(
            "agent",
            message,
            display_message=message
        )
        InternalActionInterface.state_manager.bump_event_stream()

    @staticmethod
    def do_ignore():
        """
        Note that the agent chose to ignore the latest user input.
        """
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
    async def do_create_and_run_task(cls, task_name: str, task_description: str) -> str:
        """
        Create a new task and immediately start it.

        The task metadata is persisted and registered as the active task for the
        current session.

        Args:
            task_name: Short name for the task.
            task_description: Detailed description of the work to perform.

        Returns:
            The created task identifier.

        Raises:
            RuntimeError: If task or state managers have not been initialised.
        """
        if cls.task_manager is None or cls.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with Task/State managers.")
            
        task_id = await cls.task_manager.create_task(task_name, task_description)

        await cls.task_manager.start_task()
        wf: Optional[Task] = cls.task_manager.get_task()
        cls.state_manager.add_to_active_task(wf)
        return task_id

    @classmethod
    async def mark_task_completed(cls, message: Optional[str] = None) -> Dict[str, Any]:
        """
        Mark the current session task as completed.

        If no session is active, returns an error payload instead of raising.

        Args:
            message: Optional completion note to store alongside the task.

        Returns:
            A status dictionary indicating success or failure and the relevant
            task id.
        """
        try:
            ok = await cls.task_manager.mark_task_completed(message=message)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_completed failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def mark_task_cancel(cls, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel the current session task.

        If no session is active, returns an error payload instead of raising.

        Args:
            reason: Optional explanation of why the task was cancelled.

        Returns:
            A status dictionary indicating success or failure and the relevant
            task id.
        """
        try:
            ok = await cls.task_manager.mark_task_cancel(reason=reason)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_cancel failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def mark_task_error(cls, message: Optional[str] = None) -> Dict[str, Any]:
        """
        Mark the current session task as failed.

        If no session is active, returns an error payload instead of raising.

        Args:
            message: Optional error detail to store alongside the task.

        Returns:
            A status dictionary indicating success or failure and the relevant
            task id.
        """
        try:
            ok = await cls.task_manager.mark_task_error(message=message)
            return {"status": "ok" if ok else "error"}
        except Exception as e:
            logger.error(f"[InternalActions] mark_task_error failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @classmethod
    async def start_next_step(
        cls,
        *,
        update_plan: bool = False,
    ) -> Dict[str, Any]:
        """
        Advance the active task to its next step.

        When ``update_plan`` is True, the planner is asked to refresh the plan
        before moving forward.

        Args:
            update_plan: Whether to replan the task before starting the next
                step.

        Returns:
            A status dictionary indicating success and the planner result, or an
            error payload when no task is active.
        """
        try:
            result = await cls.task_manager.start_next_step(
                replan=update_plan,
            )
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.error(f"[InternalActions] start_next_step failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}