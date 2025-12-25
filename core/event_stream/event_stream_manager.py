# -*- coding: utf-8 -*-
"""
core.event_stream.event_stream_manager.

Event stream manager that manages, stores, return concurrent event streams 
running under several active tasks.

"""


from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional
from core.event_stream.event_stream import EventStream
from core.llm_interface import LLMInterface
from core.logger import logger

class EventStreamManager:
    def __init__(self, llm: LLMInterface) -> None:
        # active event streams, keyed by session_id (string)
        self.active: Dict[str, EventStream] = {}
        self.llm = llm

    # ───────────────────────────── lifecycle ─────────────────────────────

    def create_stream(self, session_id: str, *, temp_dir: Path | None = None) -> EventStream:
        """
        Construct and register a new :class:`EventStream` for the session.

        If a stream already exists for the session, it is replaced with a fresh
        instance to guarantee a clean slate. A temporary directory can be
        provided to allow the underlying stream to externalize oversized events
        to disk.

        Args:
            session_id: Unique identifier for the session or task being tracked.
            temp_dir: Optional directory used by the stream to store large
                messages that should not be embedded directly in prompts.

        Returns:
            The newly created event stream instance.
        """
        stream = EventStream(session_id=session_id, llm=self.llm, temp_dir=temp_dir)
        self.active[session_id] = stream
        return stream

    def get_stream(self, session_id: str) -> Optional[EventStream]:
        """
        Retrieve the event stream associated with ``session_id``.

        Args:
            session_id: Identifier for the desired stream.

        Returns:
            The event stream if present, otherwise ``None``.
        """
        return self.active.get(session_id)

    def remove_stream(self, session_id: str) -> None:
        """
        Delete the event stream for a session if it exists.

        Args:
            session_id: Identifier of the stream to remove.
        """
        self.active.pop(session_id, None)

    def clear_all(self) -> None:
        """
        Remove every active stream and release their references.

        This is useful when resetting the manager between tests or sessions to
        avoid reusing state accidentally.
        """
        self.active.clear()

    # ───────────────────────────── utilities ─────────────────────────────

    def log(
        self,
        session_id: str,
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
        logger.debug(f"Process Started - Logging event to stream {session_id}: [{severity}] {kind} - {message}")
        stream = self.get_stream(session_id)
        if not stream:
            logger.debug(f"No existing stream for {session_id}. Creating new stream.")
            stream = self.create_stream(session_id)
            logger.debug(f"Created new stream: {stream}")
        return stream.log(
            kind,
            message,
            severity,
            display_message=display_message,
            action_name=action_name,
        )

    def snapshot(self, session_id: str, max_events: int = 60, include_summary: bool = True) -> str:
        """
        Produce a prompt-ready snapshot for a single session.

        Args:
            session_id: Identifier for the stream to snapshot.
            max_events: Maximum number of tail events to include.
            include_summary: Whether to prepend the stream's head summary.

        Returns:
            A compact history string, or ``"(no events)"`` when the session is
            not managed.
        """
        stream = self.get_stream(session_id)
        if not stream:
            return "(no events)"
        return stream.to_prompt_snapshot(max_events=max_events, include_summary=include_summary)

    def snapshot_all(self, max_events: int = 30) -> Dict[str, str]:
        """
        Generate prompt snapshots for every active stream in the manager.

        Args:
            max_events: Maximum events to include from each stream's tail.

        Returns:
            A mapping from session identifiers to their snapshot strings. Useful
            for dashboards and consolidated logging.
        """
        return {sid: s.to_prompt_snapshot(max_events=max_events) for sid, s in self.active.items()}
