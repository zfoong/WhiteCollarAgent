# -*- coding: utf-8 -*-
"""State management utilities for single-user, single-session agents."""

import json
from datetime import datetime
from typing import Dict, List, Literal, Optional, TypedDict

import mss
import mss.tools

from core.event_stream.event_stream_manager import EventStreamManager
from core.logger import logger


class ConversationMessage(TypedDict):
    role: Literal["user", "agent"]
    content: str
    timestamp: str

class StateSession:
    """Singleton-like container for the *current* agent session state."""

    _instance = None

    def __init__(self):
        self.session_id: str | None = "default"
        self.conversation_state: str | None = None
        self.current_task: str | None = None
        self.event_stream: str | None = None
        self.gui_mode: bool = False

    @classmethod
    def start(
        cls,
        *,
        session_id: str,
        conversation_state: str | None,
        current_task: str | None,
        event_stream: str | None,
        gui_mode: bool,
    ) -> None:
        """Initialise a fresh session with the minimal runtime state."""

        cls._instance = cls()
        inst = cls._instance
        
        # Normalise session identifiers that may arrive quoted from upstream
        # payloads (e.g. JSON-encoded task ids). Quoted IDs fail lookups in
        # TaskManager.active, leading to spurious "task_not_found" errors when
        # running follow-up actions such as start_next_step.
        # Need a better method in the future.
        if isinstance(session_id, str):
            session_id = session_id.strip().strip('"')
        
        inst.session_id = session_id
        inst.conversation_state = conversation_state
        inst.current_task = current_task
        inst.event_stream = event_stream
        inst.gui_mode = gui_mode

    @classmethod
    def get(cls):
        """
        Access the current session object. Raises RuntimeError if no session is started.
        """
        if cls._instance is None:
            raise RuntimeError("State Session not started.")
        return cls._instance

    @classmethod
    def get_or_none(cls):
        """
        Like get(), but returns None if no session is active.
        """
        return cls._instance

    @classmethod
    def end(cls):
        """
        End the current session. Session data is cleared.
        """
        cls._instance = None

    def update_conversation_state(self, new_state: str) -> None:
        self.conversation_state = new_state

    def update_current_task(self, new_task: str | None) -> None:
        self.current_task = new_task

    def update_event_stream(self, new_event_stream: str | None) -> None:
        self.event_stream = new_event_stream

    def update_gui_mode(self, gui_mode: bool) -> None:
        self.gui_mode = gui_mode

    def refresh(
        self,
        *,
        conversation_state: str | None = None,
        current_task: str | None = None,
        event_stream: str | None = None,
    ) -> None:
        """Convenience wrapper – pass only what changed."""
        if conversation_state is not None:
            self.conversation_state = conversation_state
        if current_task is not None:
            self.current_task = current_task
        if event_stream is not None:
            self.event_stream = event_stream


class StateManager:
    """Manages conversation snapshots, task state, and runtime session data."""

    def __init__(self, event_stream_manager: EventStreamManager, vlm_interface=None):

        # We have two types of state, persistant and session state
        # Persistant state are state that will not be changed frequently,
        # e.g. agent properties
        # Session state are states that is short-termed, one time used
        # e.g. current conversation, conversation state, action state
        self.tasks: Dict[str, dict] = {}
        self.event_stream_manager = event_stream_manager
        self.agent_properties = {}
        self.vlm_interface = vlm_interface
        self._conversation: List[ConversationMessage] = []

    async def start_session(self, session_id: str = "default", gui_mode: bool = False):

        conversation_state = await self.get_conversation_state()

        logger.debug(f"[SESSION ID]: this is the session id: {session_id}")

        current_task = self.get_current_task_state(session_id)

        logger.debug(f"[CURRENT TASK]: this is the current_task: {current_task}")

        event_stream = self.get_event_stream_snapshot(session_id)

        StateSession.start(
            session_id=session_id,
            conversation_state=conversation_state,
            current_task=current_task,
            event_stream=event_stream,
            gui_mode=gui_mode
        )

    
    def end_session(self):
        """
        End the session, clearing session context so the next user input starts fresh.
        """
        StateSession.end()

    def clear_conversation_history(self) -> None:
        """Drop all stored conversation messages for the active user."""
        self._conversation.clear()
        self._update_session_conversation_state()

    def reset(self) -> None:
        """Fully reset runtime state, including tasks and session context."""
        self.tasks.clear()
        self.agent_properties = {}
        self.clear_conversation_history()
        if self.event_stream_manager:
            self.event_stream_manager.clear_all()
        self.end_session()
        
    def _format_conversation_state(self) -> str:
        if not self._conversation:
            return ""

        lines: List[str] = []
        for message in self._conversation[-25:]:
            timestamp = message["timestamp"]
            role = message["role"]
            content = message["content"]
            lines.append(f"{timestamp}: {role}: \"{content}\"")

        return "\n".join(lines)

    async def get_conversation_state(self) -> str:
        return self._format_conversation_state()

    def _append_conversation_message(self, role: Literal["user", "agent"], content: str) -> None:
        self._conversation.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def _update_session_conversation_state(self) -> None:
        sess = StateSession.get_or_none()
        if sess:
            sess.update_conversation_state(self._format_conversation_state())

    def record_user_message(self, content: str) -> None:
        self._append_conversation_message("user", content)
        self._update_session_conversation_state()

    def record_agent_message(self, content: str) -> None:
        self._append_conversation_message("agent", content)
        self._update_session_conversation_state()
    
    def get_current_step(self, session_id: str) -> Optional[dict]:
        wf = self.tasks.get(session_id)
        if not wf:
            return None
        for st in wf["steps"]:
            if st["status"] == "current":
                return st
        for st in wf["steps"]:
            if st["status"] == "pending":
                return st
        return None
    
    def get_event_stream_snapshot(self, session_id: str, *, max_events: int = 60) -> str:
        return self.event_stream_manager.snapshot(session_id, max_events=max_events)
        
    def get_current_task_state(self, session_id: str) -> Optional[str]:
        wf = self.tasks.get(session_id)

        logger.debug(f"[TASK] wf in StateManager: {wf}, session id: {session_id}")

        if wf is None:
            logger.debug("[TASK] task not found in StateManager")
            return None

        # Build minimal per-step representation
        steps_summary: List[Dict[str, str]] = []
        for step in wf['steps']:
            item = {
                "step_index": step['step_index'],
                "step_name": step['step_name'],
                "description": step['description'],
                "action_instruction": step['action_instruction'],
                "validation_instruction": step['validation_instruction'],
                "status": step['status'],
            }
            if step['failure_message']:
                item["failure_message"] = step['failure_message']
            steps_summary.append(item)

        payload = {
            "instruction": wf['instruction'],
            "goal": wf['goal'],
            "inputs_params": wf['inputs_params'],
            "context": wf['context'],
            "steps": steps_summary
        }

        # Return prettified JSON string
        return json.dumps(payload, indent=2)

    def get_screen_state(self) -> Optional[str]:
        """
        Capture the primary monitor (or the only monitor if single),
        convert it to PNG bytes in memory, and send to the VLM.
        """
        if self.vlm_interface is None:
            raise RuntimeError("StateManager not initialised with VLMInterface.")
    
        # Capture screen → PNG bytes in memory
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])  # get only primary screen, set index to 0 to get all screens. # TODO, change back to 0
            png_bytes: bytes = mss.tools.to_png(shot.rgb, shot.size, output=None)

        try:
            with mss.mss() as sct:
                monitors = sct.monitors  # List of monitor dicts

                # Always capture primary monitor if it exists, otherwise the only monitor
                primary_index = 1 if len(monitors) > 1 else 0
                shot = sct.grab(monitors[primary_index])

                # Convert to in-memory PNG bytes
                png_bytes = mss.tools.to_png(shot.rgb, shot.size, output=None)

            # Send screenshot bytes to the VLM
            return self.vlm_interface.scan_ui_bytes(png_bytes, use_ocr=False)

        except Exception as e:
            # Log for debugging
            print(f"[ScreenState ERROR] {e}")
            return f"[ScreenState ERROR] {e}"

    def bump_task_state(self, session_id: str) -> None:
        sess = StateSession.get_or_none()
        if sess:
            sess.update_current_task(
                self.get_current_task_state(session_id)
            )
            
    def bump_event_stream(self, session_id: str) -> None:
        logger.debug(f"Process Started - Bump event stream for id: {session_id}")
        sess = StateSession.get_or_none()
        if sess:
            logger.debug(f"Process Started - Found event stream for id: {session_id}")
            sess.update_event_stream(self.get_event_stream_snapshot(session_id))
            
    async def bump_conversation_state(self) -> None:
        sess = StateSession.get_or_none()
        if sess:
            sess.update_conversation_state(await self.get_conversation_state())

    def is_running_task_with_id(self, session_id: str) -> bool:
        wf = self.tasks.get(session_id)
        if not wf:
            return False
        return True
        
    def is_running_task(self) -> bool:
        if self.tasks:
            return True
        else:
            return False
    
    def add_to_active_task(self, task_id: str, task: dict):
        self.set_active_task(task_id, task)

    # TODO remove duplicate
    def set_active_task(self, task_id: str, task: dict):
        self.tasks[task_id] = task
        self.bump_task_state(task_id)

    def remove_active_task(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)
        sess = StateSession.get_or_none()
        if sess and sess.session_id == task_id:
            sess.update_current_task(None)
    
    def get_all_task_state(self) -> List[str]:
        pass    

    def set_agent_property(self, key, value):
        """
        Sets a global agent property (not specific to any task).
        """
        self.agent_properties[key] = value

    def get_agent_property(self, key, default=None):
        """
        Retrieves a global agent property.
        """
        return self.agent_properties.get(key, default)