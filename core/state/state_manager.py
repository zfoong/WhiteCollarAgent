import json
from datetime import datetime
from typing import Dict, List, Literal, Optional
from core.state.types import AgentProperties, ConversationMessage
from core.state.agent_state import STATE
from core.event_stream.event_stream_manager import EventStreamManager
from core.task.task import Task
from core.logger import logger


class StateManager:
    """Manages conversation snapshots, task state, and runtime session data."""

    def __init__(self, event_stream_manager: EventStreamManager):

        # We have two types of state, persistant and session state
        # Persistant state are state that will not be changed frequently,
        # e.g. agent properties
        # Session state are states that is short-termed, one time used
        # e.g. current conversation, conversation state, action state
        self.task: Optional[Task] = None
        self.event_stream_manager = event_stream_manager
        self._conversation: List[ConversationMessage] = []

    async def start_session(self, gui_mode: bool = False):

        conversation_state = await self.get_conversation_state()
        event_stream = self.get_event_stream_snapshot()
        current_task = self.get_current_task_state()

        logger.debug(f"[CURRENT TASK]: this is the current_task: {current_task}")

        STATE.refresh(
            conversation_state=conversation_state,
            current_task=current_task,
            event_stream=event_stream,
            gui_mode=gui_mode
        )

    
    def clean_state(self):
        """
        End the session, clearing session context so the next user input starts fresh.
        """
        STATE.refresh()

    def clear_conversation_history(self) -> None:
        """Drop all stored conversation messages for the active user."""
        self._conversation.clear()
        self._update_session_conversation_state()

    def reset(self) -> None:
        """Fully reset runtime state, including tasks and session context."""
        self.task = None
        STATE.agent_properties: AgentProperties = AgentProperties(current_task_id="", action_count=0, token_count=0)
        self.clear_conversation_history()
        if self.event_stream_manager:
            self.event_stream_manager.clear_all()
        self.clean_state()
        
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
        STATE.update_conversation_state(self._format_conversation_state())

    def record_user_message(self, content: str) -> None:
        self._append_conversation_message("user", content)
        self._update_session_conversation_state()

    def record_agent_message(self, content: str) -> None:
        self._append_conversation_message("agent", content)
        self._update_session_conversation_state()
    
    def get_current_step(self) -> Optional[dict]:
        wf = self.task
        if not wf:
            return None
        for st in wf["steps"]:
            if st["status"] == "current":
                return st
        for st in wf["steps"]:
            if st["status"] == "pending":
                return st
        return None
    
    def get_event_stream_snapshot(self, *, max_events: int = 60) -> str:
        return self.event_stream_manager.snapshot(max_events=max_events)
        
    def get_current_task_state(self) -> Optional[str]:
        wf = self.task

        logger.debug(f"[TASK] wf in StateManager: {wf}")

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

    def bump_task_state(self) -> None:
        STATE.update_current_task(
                self.get_current_task_state()
            )
            
    def bump_event_stream(self) -> None:
        STATE.update_event_stream(self.get_event_stream_snapshot())
        
    def is_running_task(self) -> bool:
        if self.task:
            return True
        else:
            return False
    
    def add_to_active_task(self, task: dict):
        self.set_active_task(task)

    # TODO remove duplicate
    def set_active_task(self, task: dict):
        self.task = task
        self.bump_task_state()

    def remove_active_task(self) -> None:
        self.task = None
        STATE.update_current_task(None) 
