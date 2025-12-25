# -*- coding: utf-8 -*-
"""State management utilities for single-user, single-session agents."""


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