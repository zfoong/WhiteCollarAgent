"""
core.internal_action_interface

This interface contains all the agent actions calling to the agent
framework internal functions. Most functions are not implemented yet.
"""

from typing import Dict, Any, Optional
from core.llm_interface import LLMInterface
from core.vlm_interface import VLMInterface
from core.task.task_manager import TaskManager
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from datetime import datetime
from core.logger import logger
from pathlib import Path
from core.config import AGENT_WORKSPACE_ROOT
import asyncio
import mss, mss.tools, os
import shutil
import urllib.request
from urllib.parse import urlparse
from uuid import uuid4

class InternalActionInterface:
    """
    Provides static/class methods so it can be used without instantiation.
    Calls that need the LLM references can do so via class-level variables.
    Allow agent to access core functions
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
        cls.llm_interface = llm_interface
        cls.task_manager = task_manager
        cls.state_manager = state_manager
        cls.vlm_interface = vlm_interface

    # ─────────────────────── LLM Access for Actions ───────────────────────
    @classmethod
    def use_llm(cls, prompt: str, system_message: Optional[str] = None) -> Dict[str, Any]:
        if cls.llm_interface is None:
            raise RuntimeError("InternalActionInterface not initialized with LLMInterface.")
        response = cls.llm_interface.generate_response(prompt, system_message)
        return {"llm_response": response}
    
    @classmethod
    def describe_image(cls, image_path: str, prompt: str | None = None) -> str:
        if cls.vlm_interface is None:
            raise RuntimeError("InternalActionInterface not initialized with VLMInterface.")
        return cls.vlm_interface.describe_image(image_path, user_prompt=prompt)
    
    # ─────────────────────── GUI Actions ───────────────────────
    
    @classmethod
    def describe_screen(cls) -> dict[str, str]:
        """
        Capture the entire virtual desktop and return:
          { 'description': markdown_text, 'file_path': absolute_png_path }
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
        logger.debug("[Agent Action] Ignoring user message.")

    @staticmethod
    async def do_ask_question(question: str) -> None:
        if InternalActionInterface.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with StateManager.")

        InternalActionInterface.state_manager.record_agent_message(question)

        event_stream_manager = InternalActionInterface.state_manager.event_stream_manager
        event_stream_manager.log(
            "agent_question",
            question,
            display_message=question
        )
        InternalActionInterface.state_manager.bump_event_stream()

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
        
        if cls.task_manager is None or cls.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with Task/State managers.")
            
        task_id = await cls.task_manager.create_task(task_name, task_description)

        await cls.task_manager.start_task()
        wf_dict = cls.task_manager.get_task()
        cls.state_manager.add_to_active_task(wf_dict)
        return task_id

    @classmethod
    async def mark_task_completed(cls, message: Optional[str] = None) -> Dict[str, Any]:
        """
        End the task as 'completed'. If task_id is None, tries the active one for this session.
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
        End the task as 'cancelled' (aborted by user). If task_id is None, tries the active one for this session.
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
        End the task as 'error'. If task_id is None, tries the active one for this session.
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
        Advance to the next step. If update_plan=True, request the planner
        to update the plan and advance to the next (possibly newly created) step.
        """
        try:
            result = await cls.task_manager.start_next_step(
                replan=update_plan,
            )
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.error(f"[InternalActions] start_next_step failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    # ─────────────────────── Self-initiative goals ───────────────────────
    @classmethod
    def _get_goal_store(cls) -> Dict[str, Dict[str, Any]]:
        if cls.state_manager is None:
            raise RuntimeError("InternalActionInterface not initialized with StateManager.")

        goals = cls.state_manager.get_agent_property("self_initiative_goals") or {}
        if not isinstance(goals, dict):
            goals = {}
        cls.state_manager.set_agent_property("self_initiative_goals", goals)
        return goals

    @classmethod
    async def upsert_self_initiative_goal(
        cls,
        *,
        op: str = "upsert",
        goal_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        execution_interval: str | None = None,
        journal: str | None = None,
    ) -> Dict[str, Any]:
        """Create, update, delete, or upsert a self-initiative goal in memory."""

        goals = cls._get_goal_store()
        normalized_op = (op or "upsert").lower()
        now = datetime.utcnow().isoformat()

        if normalized_op not in {"create", "update", "delete", "upsert"}:
            return {"status": "error", "error": f"invalid_operation: {op}"}

        if normalized_op == "delete":
            if not goal_id:
                return {"status": "error", "error": "goal_id_required"}
            goal = goals.get(goal_id)
            if not goal:
                return {"status": "error", "error": "goal_not_found"}
            goal["deleted_at"] = now
            goal["updated_at"] = now
            cls.state_manager.set_agent_property("self_initiative_goals", goals)
            return {"status": "ok", "goal": goal}

        if normalized_op in {"create", "upsert"} and goal_id:
            # Prevent accidental reuse of IDs for create/upsert without lookup.
            goal = goals.get(goal_id)
        else:
            goal = goals.get(goal_id) if goal_id else None

        if normalized_op == "update" and not goal_id:
            return {"status": "error", "error": "goal_id_required"}

        if normalized_op == "update" and goal is None:
            return {"status": "error", "error": "goal_not_found"}

        if goal is None:
            # create a new goal document
            new_goal_id = goal_id or str(uuid4())
            goal = {
                "goal_id": new_goal_id,
                "title": title or "",
                "description": description or "",
                "execution_interval": execution_interval or "",
                "journal": journal or "",
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
            goals[new_goal_id] = goal
        else:
            # update existing goal fields when provided
            if title is not None:
                goal["title"] = title
            if description is not None:
                goal["description"] = description
            if execution_interval is not None:
                goal["execution_interval"] = execution_interval
            if journal is not None:
                goal["journal"] = journal
            goal["updated_at"] = now
            goal.setdefault("created_at", now)
            goal.setdefault("deleted_at", None)

        cls.state_manager.set_agent_property("self_initiative_goals", goals)
        return {"status": "ok", "goal": goal}

    @classmethod
    async def update_self_initiative_goal_journal(
        cls,
        *,
        goal_id: str,
        new_information: str,
    ) -> Dict[str, Any]:
        goals = cls._get_goal_store()

        goal = goals.get(goal_id)
        if goal is None:
            return {"status": "error", "error": "goal_not_found"}

        now = datetime.utcnow().isoformat()
        existing_journal = goal.get("journal") or ""
        addition = new_information.strip()
        if addition:
            stamped_entry = f"\n\n## Update {now}\n{addition}\n"
        else:
            stamped_entry = f"\n\n## Update {now}\n(no additional information provided)\n"
        goal["journal"] = (existing_journal + stamped_entry).strip()
        goal["updated_at"] = now
        goal.setdefault("created_at", now)
        goal.setdefault("deleted_at", None)

        cls.state_manager.set_agent_property("self_initiative_goals", goals)
        return {"status": "ok", "goal": goal}
