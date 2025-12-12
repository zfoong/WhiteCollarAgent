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
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import re
from pathlib import Path
from typing import List, Optional, Tuple
from core.event_stream.event import Event, EventRecord
from core.llm_interface import LLMInterface
from core.prompt import EVENT_STREAM_SUMMARIZATION_PROMPT
from sklearn.feature_extraction.text import TfidfVectorizer
from core.logger import logger

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
        session_id: str,
        llm: LLMInterface,
        summarize_at: int = 30,
        tail_keep_after_summarize: int = 15,
        max_events: int = 60,
        temp_dir: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.head_summary: Optional[str] = None
        self.llm = llm
        self.tail_events: List[EventRecord] = []
        self.summarize_at = summarize_at
        self.tail_keep_after_summarize = tail_keep_after_summarize
        self.max_events = max_events
        self.temp_dir = temp_dir

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
        if severity not in SEVERITIES:
            severity = "INFO"
        msg = self._externalize_message(message.strip(), action_name=action_name)
        display = display_message.strip() if display_message is not None else None
        ev = Event(message=msg, kind=kind.strip(), severity=severity, display_message=display)
        rec = EventRecord(event=ev)

        self.tail_events.append(rec)
        self._check_repeated_actions(rec, action_name=action_name)
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
            print("1 [ISSUE]")
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            print("2 [ISSUE]")
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")
            suffix = "action"
            
            if action_name:
                suffix = re.sub(r"[^A-Za-z0-9._-]", "_", action_name).strip("._-") or "action"
            print("3 [ISSUE]")
            file_path = self.temp_dir / f"event_{suffix}_{ts}.txt"
            print("4 [ISSUE]")
            file_path.write_text(message, encoding="utf-8")
            keywords = ", ".join(self._extract_keywords(message)) or "n/a"
            print("5 [ISSUE]")
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
        if len(self.tail_events) >= self.summarize_at:
            self.summarize_by_LLM()

    def summarize_by_rule(self) -> None:
        """Summarize the oldest chunk of tail_events into head_summary."""
        if not self.tail_events:
            return

        # Select chunk to roll up (older events)
        cutoff = max(0, len(self.tail_events) - self.tail_keep_after_summarize)
        chunk = self.tail_events[:cutoff]
        self.tail_events = self.tail_events[cutoff:]

        # Build a compact textual summary by kind/severity
        counts_by_kind = {}
        counts_by_sev = {}
        repeats = 0
        first_ts = chunk[0].ts if chunk else None
        last_ts = chunk[-1].ts if chunk else None

        for rec in chunk:
            k = rec.event.kind
            s = rec.event.severity
            counts_by_kind[k] = counts_by_kind.get(k, 0) + rec.repeat_count
            counts_by_sev[s] = counts_by_sev.get(s, 0) + rec.repeat_count
            if rec.repeat_count > 1:
                repeats += (rec.repeat_count - 1)

        def _fmt_counts(d: dict) -> str:
            return ", ".join(f"{k}={v}" for k, v in sorted(d.items()))

        window = ""
        if first_ts and last_ts:
            window = f"{first_ts.strftime('%H:%M:%S')}–{last_ts.strftime('%H:%M:%S')}"

        summary_line = (
            f"Rolled up {sum(counts_by_kind.values())} events [{window}] — "
            f"kinds: {_fmt_counts(counts_by_kind)}; severities: {_fmt_counts(counts_by_sev)}"
        )
        if repeats:
            summary_line += f"; collapsed repeats={repeats}"

        if self.head_summary:
            self.head_summary = self.head_summary + "\n" + summary_line
        else:
            self.head_summary = summary_line
            
    async def summarize_by_LLM(self) -> None:
        """
        Force summarization of the oldest chunk using the LLM.
        Rolls the previous head_summary + oldest tail_events chunk into a new head_summary.
        """
        if not self.tail_events:
            return

        # Select the chunk to roll up (oldest events), same policy as rule-based
        cutoff = max(0, len(self.tail_events) - self.tail_keep_after_summarize)
        if cutoff <= 0:
            # Nothing old enough to summarize
            return

        chunk = self.tail_events[:cutoff]
        remaining = self.tail_events[cutoff:]

        # Prepare context for the LLM
        first_ts = chunk[0].ts if chunk else None
        last_ts = chunk[-1].ts if chunk else None
        window = ""
        if first_ts and last_ts:
            window = f"{first_ts.isoformat()} to {last_ts.isoformat()}"

        # Compact lines to keep prompt small
        compact_lines = "\n".join(r.compact_line() for r in chunk)

        previous_summary = self.head_summary or "(none)"

        # Build a focused prompt for durable, operation-oriented summarization
        prompt = EVENT_STREAM_SUMMARIZATION_PROMPT(self.session_id, window, previous_summary, compact_lines)

        # Ask the LLM to synthesize the new head summary
        try:
            llm_output = await self.llm.generate_response_async(user_prompt=prompt)
            new_summary = (llm_output or "").strip()
            if new_summary:
                self.head_summary = new_summary
                # Drop the summarized events from the tail, keep only the recent ones
                self.tail_events = remaining
        except Exception:
            # If LLM fails, do not lose data—fallback to rule-based roll-up
            self.summarize_by_rule()
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

    def to_prompt_snapshot(self, max_events: int = 60, include_summary: bool = True) -> str:
        """
        Returns a compact snapshot suitable for LLM context.
        """
        lines: List[str] = []
        if include_summary and self.head_summary:
            lines.append("EARLIER (summary): " + self.head_summary)

        recent = self.tail_events[-max_events:]
        if recent:
            lines.append("RECENT EVENTS:")
            lines.extend(r.compact_line() for r in recent)

        return "\n".join(lines) if lines else "(no events)"

    # ─────────────────────────── util / export ───────────────────────────

    def as_list(self, limit: Optional[int] = None) -> List[Event]:
        items = self.tail_events if limit is None else self.tail_events[-limit:]
        return [r.event for r in items]

    def clear(self) -> None:
        self.head_summary = None
        self.tail_events.clear()

    # ──────────────────────────── warnings ─────────────────────────────

    def _check_repeated_actions(self, rec: EventRecord, *, action_name: str | None) -> None:
        """Detect repeated action attempts with identical parameters.

        If the same action with the same parameters is logged three times
        consecutively, emit a warning event to alert that the agent may be
        stuck in a loop.
        """

        if rec.event.kind != "action" or not action_name:
            return

        repeated_count = 0
        for prev in reversed(self.tail_events):
            if prev.event.kind != "action":
                break
            if prev.event.message != rec.event.message:
                break
            repeated_count += prev.repeat_count

        if repeated_count >= 3:
            warning_message = (
                "You have repeated the same action with the same parameters 3 times. "
                "This is a warning to remind you that you might be stuck in the same action loop due to errors. "
                "You should perform other actions to complete the task or abort the task. "
                "However, if this is intended, please proceed as usual."
            )

            # Avoid duplicate warnings back-to-back.
            last_event = self.tail_events[-1] if self.tail_events else None
            if not last_event or last_event.event.message != warning_message:
                self.log(
                    "warning",
                    warning_message,
                    severity="WARN",
                    display_message=None,
                )
