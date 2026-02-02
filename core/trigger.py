# -*- coding: utf-8 -*-
"""
core.trigger

Trigger in this framework is the entry point of ALL reactions by the agent.
"""
from __future__ import annotations

import asyncio
import heapq
import json
import time
from dataclasses import dataclass, field
from collections import defaultdict, OrderedDict
from typing import Dict, List, Optional, Any
from core.logger import logger
from core.llm_interface import LLMInterface
from core.state.agent_state import STATE
from core.prompt import CHECK_TRIGGERS_STATE_PROMPT
from decorators.profiler import profile, OperationCategory

# ─────────────────────────── Data class ─────────────────────────────
@dataclass(order=True)
class Trigger:
    fire_at: float
    priority: int
    next_action_description: str
    payload: Dict[str, Any] = field(default_factory=dict, compare=False)
    session_id: Optional[str] = field(default=None, compare=False)


# ───────────────────────── Trigger Queue ─────────────────────────────
class TriggerQueue:
    """
    Concurrency-safe priority queue for Trigger.
    """

    def __init__(self, llm: LLMInterface) -> None:
        """
        Initialize a concurrency-safe trigger queue.

        The queue manages incoming :class:`Trigger` objects using a heap to
        preserve ordering by ``fire_at`` timestamp and priority. A shared
        :class:`asyncio.Condition` coordinates producers and consumers so agent
        loops can await triggers without busy waiting.

        Args:
            llm: Interface used to resolve conflicts between competing triggers
                for the same session.
        """
        self._heap: List[Trigger] = []
        self._cv = asyncio.Condition()
        self.llm = llm
    # =================================================================
    # Pretty Printer for Debugging
    # =================================================================
    def _print_queue(self, label: str) -> None:
        logger.debug("=" * 70)
        logger.debug(f"[TRIGGER QUEUE] {label}")
        logger.debug("=" * 70)

        if not self._heap:
            logger.debug("(empty)")
            return

        now = time.time()
        for i, t in enumerate(sorted(self._heap, key=lambda x: (x.fire_at, x.priority))):
            logger.debug(
                f"{i+1}. session_id={t.session_id} | "
                f"prio={t.priority} | "
                f"fire_at={t.fire_at:.6f} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t.fire_at))}) | "
                f"delta={t.fire_at - now:.2f}s\n"
                f"   desc={t.next_action_description}"
            )
        logger.debug("=" * 70 + "\n")

    def create_event_stream_state(self):
        """Return formatted event stream content for trigger comparison."""
        event_stream = STATE.event_stream
        if event_stream:
            return (
                "Use the event stream to understand the current situation, past agent actions to craft the input parameters:\nEvent stream (oldest to newest):"
                f"\n{event_stream}"
            )
        return ""

    def create_task_state(self):
        """Return formatted task/plan context for trigger comparison."""
        current_task: Optional[Task] = STATE.current_task
        if current_task:
            # Format task in LLM-friendly way (matching context_engine format)
            lines = [
                "<current_task>",
                f"Task: {current_task.name}",
                f"Instruction: {current_task.instruction}",
                "",
                "Todos:",
            ]

            if current_task.todos:
                for todo in current_task.todos:
                    if todo.status == "completed":
                        checkbox = "[x]"
                    elif todo.status == "in_progress":
                        checkbox = "[>]"
                    else:
                        checkbox = "[ ]"
                    lines.append(f"{checkbox} {todo.content}")
            else:
                lines.append("(no todos yet)")

            lines.append("</current_task>")
            return "\n".join(lines)
        return ""

    async def clear(self) -> None:
        """
        Remove all pending triggers from the queue.

        The queue is cleared under the protection of the condition variable so
        waiting consumers are notified immediately that the queue state has
        changed.
        """
        async with self._cv:
            self._heap.clear()
            self._cv.notify_all()
        
    # =================================================================
    # PUT
    # =================================================================
    @profile("trigger_queue_put", OperationCategory.TRIGGER)
    async def put(self, trig: Trigger) -> None:
        """
        Insert a trigger into the queue, merging with existing session triggers.

        When a trigger arrives for a session that already has queued work, the
        method consults the LLM to generate a new session identifier that
        represents the preferred trigger. Existing triggers for that session
        are removed so the freshest trigger wins.

        Args:
            trig: Trigger instance describing when and why the agent should act.
        """
        logger.debug(f"\n[PUT] Incoming trigger for session={trig.session_id}")
        self._print_queue("BEFORE PUT")

        existing_triggers: List[Trigger] = self._heap

        if len(existing_triggers) > 0:

            # KV CACHING: System prompt is now minimal/static
            # Dynamic context moved to user prompt
            sys_msg = "You are a trigger management system."

            # If heap empty → push directly
            if not existing_triggers:
                existing_triggers.append(trig)
            else:
                logger.debug("[TRIGGER QUEUE] Heap not empty → ignoring new trigger for LLM comparison")

            # KV CACHING: Add dynamic context to user prompt
            usr_msg = CHECK_TRIGGERS_STATE_PROMPT.format(
                event_stream=self.create_event_stream_state(),
                task_state=self.create_task_state(),
                context=trig,
                existing_triggers=existing_triggers,
            )

            new_trigger_id = await self.llm.generate_response_async(sys_msg, usr_msg)
            logger.debug(f"[PUT] New trigger value: {new_trigger_id}")

            # Update the incoming trigger's ID
            trig.session_id = new_trigger_id

        async with self._cv:
            # find all triggers in heap with same session_id
            same = [t for t in self._heap if t.session_id == trig.session_id]

            if same:
                logger.debug("[PUT] Existing trigger(s) found → PREFER NEW TRIGGER")
                self._print_queue("BEFORE REPLACE (PUT)")

                # Remove ALL old triggers for this session
                self._heap = [t for t in self._heap if t.session_id != trig.session_id]

                # NEW BEHAVIOUR: prefer new → push new trigger only
                heapq.heappush(self._heap, trig)

                logger.debug("[PUT] REPLACED old triggers with NEW trigger")
                self._print_queue("AFTER REPLACE (PUT)")

            else:
                logger.debug("[PUT] No existing session trigger → pushing normally")
                heapq.heappush(self._heap, trig)

            heapq.heapify(self._heap)

            self._print_queue("AFTER PUT")
            self._cv.notify()

    # =================================================================
    # GET
    # =================================================================
    @profile("trigger_queue_get", OperationCategory.TRIGGER)
    async def get(self) -> Trigger:
        """
        Retrieve the next trigger to execute, waiting until one is ready.

        The method drains all triggers that are ready to fire, merges triggers
        belonging to the same session, and returns the highest-priority
        combined trigger. If no trigger is ready, it waits until either the
        earliest trigger's ``fire_at`` time arrives or a producer notifies the
        condition.

        Returns:
            The next merged :class:`Trigger` ready for execution.
        """
        logger.debug("\n[GET] CALLED")
        self._print_queue("QUEUE BEFORE GET")

        async with self._cv:
            while True:
                now = time.time()

                # collect ready triggers
                ready: List[Trigger] = []
                while self._heap and self._heap[0].fire_at <= now:
                    ready.append(heapq.heappop(self._heap))

                if ready:
                    logger.debug(f"[GET] {len(ready)} trigger(s) are ready")
                    self._print_queue("READY BEFORE MERGE (GET)")

                    merged_ready = self._merge_ready_triggers(ready)
                    merged_ready.sort(key=lambda t: (t.priority, t.fire_at))

                    trig = merged_ready.pop(0)
                    logger.info(
                        f"[TRIGGER FIRED] session={trig.session_id} | desc={trig.next_action_description}"
                    )

                    # requeue leftover
                    for t in merged_ready:
                        heapq.heappush(self._heap, t)

                    self._print_queue("QUEUE AFTER GET (POST-MERGE)")
                    return trig

                # wait for next trigger
                if self._heap:
                    next_fire = self._heap[0].fire_at
                    delay = next_fire - now
                    if delay <= 0:
                        continue
                    try:
                        await asyncio.wait_for(self._cv.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        continue
                else:
                    await self._cv.wait()

    # =================================================================
    # SIZE / LIST
    # =================================================================
    async def size(self) -> int:
        """
        Count how many triggers are currently queued.

        Returns:
            The number of triggers stored in the heap.
        """
        async with self._cv:
            return len(self._heap)

    async def list_triggers(self) -> List[Trigger]:
        """
        List the triggers currently in the queue without altering order.

        Returns:
            A shallow copy of the internal trigger heap contents.
        """
        async with self._cv:
            return list(self._heap)

    # =================================================================
    # FIRE NOW
    # =================================================================
    async def fire(self, session_id: str) -> bool:
        """
        Mark a trigger for a given session as ready to fire immediately.

        The ``fire_at`` timestamp for matching triggers is updated to the
        current time, and waiting consumers are notified.

        Args:
            session_id: Identifier of the session whose trigger should fire
                now.

        Returns:
            ``True`` if at least one trigger was updated, otherwise ``False``.
        """
        async with self._cv:
            found = False
            for t in self._heap:
                if t.session_id == session_id:
                    t.fire_at = time.time()
                    found = True
            if found:
                self._cv.notify()
            return found

    # =================================================================
    # REMOVE SESSIONS
    # =================================================================
    async def remove_sessions(self, session_ids: list[str]) -> None:
        """
        Remove all triggers that belong to the provided session identifiers.

        Args:
            session_ids: Sessions whose queued triggers should be discarded.
                An empty list leaves the queue unchanged.
        """
        if not session_ids:
            return
        async with self._cv:
            self._heap = [t for t in self._heap if t.session_id not in session_ids]
            heapq.heapify(self._heap)
            self._cv.notify_all()

    # =================================================================
    # MERGE HELPERS
    # =================================================================
    def _merge_ready_triggers(self, ready: List[Trigger]) -> List[Trigger]:
        grouped = defaultdict(list)
        for trig in ready:
            grouped[trig.session_id].append(trig)

        result = []
        for session_id, triggers in grouped.items():
            logger.debug(f"[MERGE READY] Merging {len(triggers)} triggers for session={session_id}")
            result.append(self._merge_trigger_group(session_id, triggers))

        return result

    def _merge_trigger_group(self, session_id: Optional[str], triggers: List[Trigger]) -> Trigger:
        logger.debug(f"[MERGE GROUP] session={session_id}, count={len(triggers)}")
        triggers.sort(key=lambda t: (t.priority, t.fire_at))

        combined_payload = {}
        combined_desc = OrderedDict()
        priority = triggers[0].priority
        fire_at = triggers[0].fire_at

        for trig in triggers:
            priority = min(priority, trig.priority)
            fire_at = min(fire_at, trig.fire_at)

            desc = (trig.next_action_description or "").strip()
            if desc and desc not in combined_desc:
                combined_desc[desc] = None

            combined_payload.update(trig.payload)

        merged_desc = "\n\n".join(combined_desc.keys()) or triggers[0].next_action_description

        merged = Trigger(
            fire_at=fire_at,
            priority=priority,
            next_action_description=merged_desc,
            payload=combined_payload,
            session_id=session_id,
        )

        logger.debug(f"[MERGE RESULT] session={session_id}, fire_at={fire_at}, priority={priority}")
        return merged
