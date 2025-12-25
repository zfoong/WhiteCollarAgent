# -*- coding: utf-8 -*-
"""Global runtime state for a single-user, single-agent process."""

from dataclasses import dataclass
from typing import Optional
from core.state.types import AgentProperties

@dataclass
class AgentState:
    """Authoritative runtime state for the agent."""

    session_id: Optional[str] = None
    conversation_state: Optional[str] = None
    current_task: Optional[str] = None
    event_stream: Optional[str] = None
    gui_mode: bool = False
    agent_properties: AgentProperties = AgentProperties(current_task_id="", action_count=0)

    def update_conversation_state(self, new_state: str) -> None:
        self.conversation_state = new_state

    def update_current_task(self, new_task: Optional[str]) -> None:
        self.current_task = new_task

    def update_event_stream(self, new_event_stream: Optional[str]) -> None:
        self.event_stream = new_event_stream

    def update_gui_mode(self, gui_mode: bool) -> None:
        self.gui_mode = gui_mode

    def refresh(
        self,
        *,
        session_id: Optional[str] = None,
        conversation_state: Optional[str] = None,
        current_task: Optional[str] = None,
        event_stream: Optional[str] = None,
        gui_mode: Optional[bool] = None,
    ) -> None:
        """Update only fields that changed."""
        self.conversation_state = conversation_state
        self.current_task = current_task
        self.event_stream = event_stream
        self.gui_mode = gui_mode


# ---- Global runtime state ----
STATE = AgentState()
