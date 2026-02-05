# -*- coding: utf-8 -*-
"""
core.event_stream.event_stream_manager.

Event stream manager that manages, stores, return concurrent event streams 
running under several active tasks.

"""


from __future__ import annotations
from core.event_stream.event_stream import EventStream
from core.llm import LLMInterface
from core.logger import logger

class EventStreamManager:
    def __init__(self, llm: LLMInterface) -> None:
        # active event streams, keyed by session_id (string)
        self.event_stream: EventStream = EventStream(llm=llm, temp_dir=None)
        self.llm = llm

    # ───────────────────────────── lifecycle ─────────────────────────────

    def get_stream(self) -> EventStream:
        """Return the event stream for this session, or None if missing."""
        return self.event_stream

    def clear_all(self) -> None:
        """Remove all event streams."""
        self.event_stream.clear()

    # ───────────────────────────── utilities ─────────────────────────────

    def log(
        self,
        kind: str,
        message: str,
        severity: str = "INFO",
        *,
        display_message: str | None = None,
        action_name: str | None = None,
    ) -> int:
        """
        Log directly to a session's event stream, creating it on demand.

        The manager records debug breadcrumbs around stream creation to aid in
        tracing concurrent tasks. Returned indices match those produced by
        :meth:`core.event_stream.event_stream.EventStream.log` and can be used
        to correlate updates.

        Args:
            session_id: Target stream identifier; a new stream is created when
                none exists.
            kind: Event family such as ``"action_start"`` or ``"warn"``.
            message: Main event text.
            severity: Importance level, defaulting to ``"INFO"``.
            display_message: Optional trimmed message for UI surfaces.
            action_name: Optional action label for file-based externalization.

        Returns:
            Index of the logged event within the target stream's tail.
        """
        logger.debug(f"Process Started - Logging event to stream: [{severity}] {kind} - {message}")
        stream = self.get_stream()
        return stream.log(
            kind,
            message,
            severity,
            display_message=display_message,
            action_name=action_name,
        )

    def snapshot(self, include_summary: bool = True) -> str:
        """Return a prompt snapshot of a specific session, or '(no events)' if not found."""
        stream = self.get_stream()
        if not stream:
            return "(no events)"
        return stream.to_prompt_snapshot(include_summary=include_summary)
