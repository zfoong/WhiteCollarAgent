# -*- coding: utf-8 -*-
"""
core.event_stream.event_stream_manager.

Event stream manager that manages, stores, return concurrent event streams
running under several active tasks.

Also handles file-based event logging to:
- EVENT.md: Complete event history
- EVENT_UNPROCESSED.md: Events pending memory processing

"""


from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import threading

from core.event_stream.event_stream import EventStream
from core.llm import LLMInterface
from core.logger import logger

# Task names that should not log to EVENT_UNPROCESSED.md (to prevent infinite loops)
SKIP_UNPROCESSED_TASK_NAMES = {"Process Memory Events"}

# Event types that should not be logged to EVENT_UNPROCESSED.md
# These are routine events that the memory processor always discards anyway
# Filtering them at write time saves processing and keeps the file smaller
SKIP_UNPROCESSED_EVENT_TYPES = {
    # Action lifecycle events
    "action_start",
    "action_end",
    # GUI action events
    "gui_action",
    "GUI action start",
    "GUI action end",
    # Reasoning and observation
    "agent reasoning",
    "screen_description",
    # Task lifecycle events
    # "task_start",
    # "task_end",
    # System events
    "waiting_for_user",
}


class EventStreamManager:
    def __init__(
        self,
        llm: LLMInterface,
        agent_file_system_path: Optional[Path] = None
    ) -> None:
        # active event streams, keyed by session_id (string)
        self.event_stream: EventStream = EventStream(llm=llm, temp_dir=None)
        self.llm = llm

        # File-based event logging
        self._agent_file_system_path = agent_file_system_path
        self._skip_unprocessed_logging = False
        self._file_lock = threading.Lock()

    # ───────────────────────────── lifecycle ─────────────────────────────

    def get_stream(self) -> EventStream:
        """Return the event stream for this session, or None if missing."""
        return self.event_stream

    def clear_all(self) -> None:
        """Remove all event streams."""
        self.event_stream.clear()

    # ───────────────────────── file-based logging ─────────────────────────

    def set_skip_unprocessed_logging(self, skip: bool) -> None:
        """
        Enable or disable logging to EVENT_UNPROCESSED.md.

        Used during memory processing tasks to prevent infinite loops where
        events generated during processing would be added to the unprocessed
        queue.

        Args:
            skip: If True, events will NOT be written to EVENT_UNPROCESSED.md
                  (but will still be written to EVENT.md for complete history).
        """
        self._skip_unprocessed_logging = skip
        # Log at INFO level so we can trace when flag changes
        logger.info(f"[EventStreamManager] skip_unprocessed_logging set to {skip}")

    def _should_skip_unprocessed(self) -> bool:
        """
        Check if logging to EVENT_UNPROCESSED.md should be skipped.

        This uses both the explicit flag AND checks if the current task
        is a memory processing task (by name). This provides a robust
        fallback in case the flag isn't properly set.

        Returns:
            True if logging to EVENT_UNPROCESSED.md should be skipped.
        """
        # Check explicit flag first
        if self._skip_unprocessed_logging:
            return True

        # Fallback: check current task name from STATE
        try:
            from core.state.agent_state import STATE
            current_task = STATE.current_task
            if current_task and current_task.name in SKIP_UNPROCESSED_TASK_NAMES:
                logger.debug(f"[EventStreamManager] Skipping unprocessed logging for task: {current_task.name}")
                return True
        except Exception:
            # If we can't check STATE, fall back to flag only
            pass

        return False

    def _should_skip_event_type(self, kind: str) -> bool:
        """
        Check if this event type should be skipped for EVENT_UNPROCESSED.md.

        Routine events like action_start, action_end, reasoning, etc. are always
        discarded by the memory processor, so we filter them at write time.

        Args:
            kind: Event category to check

        Returns:
            True if this event type should not be written to EVENT_UNPROCESSED.md
        """
        return kind in SKIP_UNPROCESSED_EVENT_TYPES

    def _log_to_files(self, kind: str, message: str) -> None:
        """
        Append an event to EVENT.md and optionally EVENT_UNPROCESSED.md.

        This method is thread-safe and handles file I/O errors gracefully.
        Events are written in the format: [YYYY/MM/DD HH:MM:SS] [kind]: message

        Args:
            kind: Event category (e.g., "action", "trigger", "task")
            message: Event message content
        """
        if not self._agent_file_system_path:
            return

        # Format: [YYYY/MM/DD HH:MM:SS] [kind]: message
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S")
        event_line = f"[{timestamp}] [{kind}]: {message}\n"

        with self._file_lock:
            # Always write to EVENT.md (create if doesn't exist)
            try:
                event_file = self._agent_file_system_path / "EVENT.md"
                with open(event_file, "a", encoding="utf-8") as f:
                    f.write(event_line)
            except Exception as e:
                logger.warning(f"[EventStreamManager] Failed to write to EVENT.md: {e}")

            # Write to EVENT_UNPROCESSED.md unless:
            # 1. Task-level skip is active (memory processing task)
            # 2. Event type is in the skip list (routine events)
            if not self._should_skip_unprocessed() and not self._should_skip_event_type(kind):
                try:
                    unprocessed_file = self._agent_file_system_path / "EVENT_UNPROCESSED.md"
                    with open(unprocessed_file, "a", encoding="utf-8") as f:
                        f.write(event_line)
                except Exception as e:
                    logger.warning(f"[EventStreamManager] Failed to write to EVENT_UNPROCESSED.md: {e}")

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
        idx = stream.log(
            kind,
            message,
            severity,
            display_message=display_message,
            action_name=action_name,
        )

        # Also log to markdown files for persistence
        self._log_to_files(kind, message)

        return idx

    def snapshot(self, include_summary: bool = True) -> str:
        """Return a prompt snapshot of a specific session, or '(no events)' if not found."""
        stream = self.get_stream()
        if not stream:
            return "(no events)"
        return stream.to_prompt_snapshot(include_summary=include_summary)
