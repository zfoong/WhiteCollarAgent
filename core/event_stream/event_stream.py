# -*- coding: utf-8 -*-
"""
core.event_stream.event_stream

The event stream maintains:
- head_summary (str | None): a compact summary of older events
- tail_events (List[EventRecord]): recent full-fidelity events

APIs:
  log(kind, message, severity="INFO") -> int (event index)
  to_prompt_snapshot(max_events=60, include_summary=True) -> str
  summarize_if_needed()  # auto-rollup when thresholds exceeded
  summarize_by_rule()        # force summarization of oldest chunk
  summarize_by_LLM()        # force summarization of oldest chunk
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import re
from pathlib import Path
from typing import List, Optional, Tuple
from core.event_stream.event import Event, EventRecord
from core.llm_interface import LLMInterface
from core.prompt import EVENT_STREAM_SUMMARIZATION_PROMPT
from sklearn.feature_extraction.text import TfidfVectorizer
from core.logger import logger
import threading

SEVERITIES = ("DEBUG", "INFO", "WARN", "ERROR") # TODO duplicated declare in event and event stream
MAX_EVENT_INLINE_CHARS = 8000

class EventStream:
    """
    Per-session event stream.
    - Keep recent events verbatim (tail_events)
    - Roll older events into head_summary when hitting thresholds
    """

    def __init__(
        self,
        *,
        llm: LLMInterface,
        summarize_at: int = 30,
        tail_keep_after_summarize: int = 15,
        temp_dir: Path | None = None,
    ) -> None:
        self.head_summary: Optional[str] = None
        self.llm = llm
        self.tail_events: List[EventRecord] = []
        self.summarize_at = summarize_at
        self.tail_keep_after_summarize = tail_keep_after_summarize
        self.temp_dir = temp_dir
        
        MINIMUM_BUFFER_BEFORE_NEXT_SUMMARIZATION= 10
        if tail_keep_after_summarize + MINIMUM_BUFFER_BEFORE_NEXT_SUMMARIZATION > summarize_at:
            logger.warning(f"Value for tail_keep_after_summarize is larger than summarize_at. Resetting tail_keep_after_summarize to {summarize_at - MINIMUM_BUFFER_BEFORE_NEXT_SUMMARIZATION}")
            tail_keep_after_summarize = summarize_at - MINIMUM_BUFFER_BEFORE_NEXT_SUMMARIZATION
           
        self._summarize_task: asyncio.Task | None = None
        self._lock = threading.RLock()

    # ────────────────────────────── logging ──────────────────────────────

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
        Append a new event to the stream and trigger summarization if needed.

        Messages are optionally externalized to disk when they exceed the inline
        threshold to keep prompt context lean. The returned index reflects the
        event's position in the current tail buffer, which can help correlate
        follow-up updates with prior logs.

        Args:
            kind: Category describing the event family (e.g., ``"action_start"``).
            message: Full event message that may be externalized if too long.
            severity: Importance level; defaults to ``"INFO"`` if unrecognized.
            display_message: Optional alternative string for UI display.
            action_name: Action identifier used when generating externalized
                file names and contextual hints.

        Returns:
            The zero-based index of the event within ``tail_events``.
        """
        if severity not in SEVERITIES:
            severity = "INFO"
        msg = self._externalize_message(message.strip(), action_name=action_name)
        display = display_message.strip() if display_message is not None else None
        ev = Event(message=msg, kind=kind.strip(), severity=severity, display_message=display)
        rec = EventRecord(event=ev)

        self.tail_events.append(rec)
        self.summarize_if_needed()
        return len(self.tail_events) - 1

    # Convenience wrappers for common event families (optional use)
    def log_action_start(self, name: str) -> int:
        return self.log("action_start", f"{name}")

    def log_action_end(self, name: str, status: str, extra: str = "") -> int:
        msg = f"{name} -> {status}"
        if extra:
            msg += f" ({extra})"
        return self.log("action_end", msg)

    # ───────────────────── summarization & pruning ───────────────────────

    def _externalize_message(self, message: str, *, action_name: str | None = None) -> str:
        """Persist overly long messages to a temp file and return a pointer event."""
        if len(message) <= MAX_EVENT_INLINE_CHARS or self.temp_dir is None:
            return message
        
        if action_name == "stream read" or action_name == "grep":
            return message

        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")
            suffix = "action"
            
            if action_name:
                suffix = re.sub(r"[^A-Za-z0-9._-]", "_", action_name).strip("._-") or "action"
            file_path = self.temp_dir / f"event_{suffix}_{ts}.txt"
            file_path.write_text(message, encoding="utf-8")
            keywords = ", ".join(self._extract_keywords(message)) or "n/a"
            return (
                f"Action {action_name} completed. The output is too long therefore is saved in {file_path} to save token. | keywords: {keywords} | To retrieve the content, agent MUST use the 'grep' action to extract the context with keywords or use 'stream read' to read the content line by line in file."
            )
        except Exception:
            logger.exception(
                "[EventStream] Failed to externalize long event message "
                f"(action={action_name or 'n/a'}, temp_dir={self.temp_dir})",
            )
            return message

    def summarize_if_needed(self) -> None:
        """
        Trigger summarization when the tail exceeds the configured threshold.

        Uses asyncio.create_task to schedule summarize_by_LLM() without requiring
        callers of log() to be async/await.
        """
        if len(self.tail_events) < self.summarize_at:
            return

        if self._summarize_task is not None and not self._summarize_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[EventStream] No running event loop; cannot schedule summarization.")
            return

        self._summarize_task = loop.create_task(self.summarize_by_LLM(), name="eventstream_summarize")
        self._summarize_task.add_done_callback(self._on_summarize_done)
            
    def _on_summarize_done(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[EventStream] summarize_by_LLM task crashed unexpectedly")        

    async def summarize_by_LLM(self) -> None:
        """
        Summarize the oldest tail events using the language model.

        This version is concurrency-safe with synchronous log() calls:
        - Snapshot the chunk under a lock
        - Release lock while awaiting the LLM
        - Re-acquire lock to apply summary + prune using the *current* tail
          so events appended during the await are not lost.
        """
        with self._lock:
            if not self.tail_events:
                return

            cutoff = max(0, len(self.tail_events) - self.tail_keep_after_summarize)

            if cutoff <= 0:
                # Nothing old enough to summarize
                return

            chunk = list(self.tail_events[:cutoff]) 
            first_ts = chunk[0].ts if chunk else None
            last_ts = chunk[-1].ts if chunk else None
            window = ""
            if first_ts and last_ts:
                window = f"{first_ts.isoformat()} to {last_ts.isoformat()}"

            compact_lines = "\n".join(r.compact_line() for r in chunk)
            previous_summary = self.head_summary or "(none)"

        prompt = EVENT_STREAM_SUMMARIZATION_PROMPT.format(window=window, previous_summary=previous_summary, compact_lines=compact_lines)

        try:
            llm_output = await self.llm.generate_response_async(user_prompt=prompt)
            new_summary = (llm_output or "").strip()
            # timestamp can be added here. For example: (from 'start time' to 'end time')
            
            logger.debug(f"[EVENT STREAM SUMMARIZATION] llm_output_len={len(llm_output or '')}")

            if not new_summary:
                logger.warning("[EVENT STREAM SUMMARIZATION] LLM returned empty summary; not updating.")
                return

            # Apply + prune under lock
            with self._lock:
                self.head_summary = new_summary
                if cutoff >= len(self.tail_events):
                    self.tail_events = []
                else:
                    self.tail_events = self.tail_events[cutoff:]

        except Exception:
            logger.exception("[EventStream] LLM summarization failed. Keeping all events without summarization.")
            return

    # ───────────────────── utilities ─────────────────────

    @staticmethod
    def _extract_keywords(message: str, top_n: int = 5) -> List[str]:
        text = (message or "").strip()
        if not text:
            return []

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        try:
            tfidf_matrix = vectorizer.fit_transform([text])
        except ValueError:
            return []

        scores = tfidf_matrix.toarray()[0]
        terms = vectorizer.get_feature_names_out()
        sorted_terms = sorted(zip(scores, terms), key=lambda kv: kv[0], reverse=True)

        keywords: List[str] = []
        for _, term in sorted_terms:
            if term and not term.isspace():
                keywords.append(term)
            if len(keywords) >= top_n:
                break
        return keywords


    # ───────────────────────── prompt accessors ──────────────────────────

    def to_prompt_snapshot(self, include_summary: bool = True) -> str:
        """
        Build a compact, human-readable history for inclusion in LLM prompts.

        The snapshot optionally includes the accumulated ``head_summary`` and
        then appends up to ``max_events`` of the most recent tail events in
        their compact string form. An empty stream returns ``"(no events)"`` to
        make absence explicit.

        Args:
            include_summary: Whether to prepend the rolled-up ``head_summary``.

        Returns:
            A newline-delimited string ready to embed in an LLM request.
        """
        lines: List[str] = []
        if include_summary and self.head_summary:
            lines.append("Summary of folded event stream: \n" + self.head_summary)

        recent = self.tail_events
        if recent:
            lines.append("Recent Event: ")
            lines.extend(r.compact_line() for r in recent)

        return "\n".join(lines) if lines else "(no events)"

    # ─────────────────────────── util / export ───────────────────────────

    def as_list(self, limit: Optional[int] = None) -> List[Event]:
        items = self.tail_events if limit is None else self.tail_events[-limit:]
        return [r.event for r in items]

    def clear(self) -> None:
        """
        Reset the stream by removing all summaries and tail events.

        This is typically used in tests or when reusing a session identifier for
        a new task to ensure no stale context leaks between runs.
        """
        self.head_summary = None
        self.tail_events.clear()
