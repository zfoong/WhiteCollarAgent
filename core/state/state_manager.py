import json
import asyncio
import threading
from datetime import datetime
from typing import Dict, List, Literal, Optional, Any
from core.state.types import AgentProperties, ConversationMessage
from core.state.agent_state import STATE
from core.event_stream.event_stream_manager import EventStreamManager
from core.task.task import Task, Step
from core.logger import logger
from core.prompt import CONVERSATION_SUMMARIZATION_PROMPT
import tiktoken

# Token counting utility
_tokenizer = None

def _get_tokenizer():
    """Get or create the tiktoken tokenizer (cached for performance)."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer

def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string using tiktoken."""
    if not text:
        return 0
    return len(_get_tokenizer().encode(text))


class StateManager:
    """Manages conversation snapshots, task state, and runtime session data."""

    def __init__(
        self,
        event_stream_manager: EventStreamManager,
        *,
        summarize_at_tokens: int = 8000,
        tail_keep_after_summarize_tokens: int = 4000,
    ):
        # We have two types of state, persistant and session state
        # Persistant state are state that will not be changed frequently,
        # e.g. agent properties
        # Session state are states that is short-termed, one time used
        # e.g. current conversation, conversation state, action state
        self.task: Optional[Task] = None
        self.event_stream_manager = event_stream_manager
        self._conversation: List[ConversationMessage] = []

        self.head_summary: Optional[str] = None
        self.summarize_at_tokens = summarize_at_tokens
        self.tail_keep_after_summarize_tokens = tail_keep_after_summarize_tokens
        self._summarize_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()

        self._total_tokens: int = 0

        MINIMUM_BUFFER_TOKENS_BEFORE_NEXT_SUMMARIZATION = 2000
        if tail_keep_after_summarize_tokens + MINIMUM_BUFFER_TOKENS_BEFORE_NEXT_SUMMARIZATION > summarize_at_tokens:
            logger.warning(
                f"[CONVERSATION SUMMARIZATION] Value for tail_keep_after_summarize_tokens ({tail_keep_after_summarize_tokens}) "
                f"is too large relative to summarize_at_tokens ({summarize_at_tokens}). "
                f"Resetting tail_keep_after_summarize_tokens to {summarize_at_tokens - MINIMUM_BUFFER_TOKENS_BEFORE_NEXT_SUMMARIZATION}"
            )
            self.tail_keep_after_summarize_tokens = summarize_at_tokens - MINIMUM_BUFFER_TOKENS_BEFORE_NEXT_SUMMARIZATION

    async def start_session(self, gui_mode: bool = False):

        conversation_state = await self.get_conversation_state()
        event_stream = self.get_event_stream_snapshot()
        current_task: Optional[Task] = self.get_current_task_state()

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
        with self._lock:
            self._conversation.clear()
            self.head_summary = None
            self._total_tokens = 0
        self._update_session_conversation_state()

    def reset(self) -> None:
        """Fully reset runtime state, including tasks and session context."""
        self.task = None
        STATE.agent_properties: AgentProperties = AgentProperties(current_task_id="", action_count=0, current_step_index=0)
        self.clear_conversation_history()
        if self.event_stream_manager:
            self.event_stream_manager.clear_all()
        self.clean_state()
        
    def _format_conversation_state(self) -> str:
        with self._lock:
            lines: List[str] = []
            
            # Include summary if available
            if self.head_summary:
                lines.append("Summary of previous conversation:")
                lines.append(self.head_summary)
                lines.append("")
            
            # Include recent messages
            if self._conversation:
                lines.append("Recent conversation:")
                for message in self._conversation[-25:]:
                    timestamp = message["timestamp"]
                    role = message["role"]
                    content = message["content"]
                    lines.append(f"{timestamp}: {role}: \"{content}\"")
            
            return "\n".join(lines) if lines else ""

    async def get_conversation_state(self) -> str:
        return self._format_conversation_state()

    def _append_conversation_message(self, role: Literal["user", "agent"], content: str) -> None:
        with self._lock:
            timestamp = datetime.utcnow().isoformat()
            self._conversation.append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                }
            )
            # Increment token count
            text = f"{timestamp}: {role}: \"{content}\""
            self._total_tokens += count_tokens(text)

    def _update_session_conversation_state(self) -> None:
        STATE.update_conversation_state(self._format_conversation_state())

    def record_user_message(self, content: str) -> None:
        self._append_conversation_message("user", content)
        self._update_session_conversation_state()
        self.summarize_if_needed()

    def record_agent_message(self, content: str) -> None:
        self._append_conversation_message("agent", content)
        self._update_session_conversation_state()
        self.summarize_if_needed()
    
    def get_current_step(self) -> Optional[Step]:
        wf: Optional[Task] = self.task
        if not wf:
            return None
        return wf.get_current_step()
    
    def get_event_stream_snapshot(self) -> str:
        return self.event_stream_manager.snapshot()
        
    def get_current_task_state(self) -> Optional[Task]:
        task: Optional[Task] = self.task

        logger.debug(f"[TASK] task in StateManager: {task}")

        if not task:
            logger.debug("[TASK] task not found in StateManager")
            return None

        # Build minimal per-step representation
        steps_list: List[Step] = []
        for step in task.steps:
            item: Dict[str, Any] = {}
            item = {
                "step_index": step.step_index,
                "step_name": step.step_name,
                "description": step.description,
                "action_instruction": step.action_instruction,
                "validation_instruction": step.validation_instruction,
                "status": step.status,
            }
            if step.failure_message:
                item["failure_message"] = step.failure_message
            steps_list.append(Step(**item, action_id=step.action_id))

        task: Task = Task(
            id=task.id,
            name=task.name,
            instruction=task.instruction,
            goal=task.goal,
            inputs_params=task.inputs_params,
            context=task.context,
            steps=steps_list
        )

        return task

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
    
    def add_to_active_task(self, task: Optional[Task]) -> None:
        if task is None:
            self.task = None
            STATE.update_current_task(None)
        else:
            self.task = task
            self.bump_task_state()

    def remove_active_task(self) -> None:
        self.task = None
        STATE.update_current_task(None)
    
    # ───────────────────── summarization & pruning ───────────────────────

    def _find_token_cutoff(self, messages: List[ConversationMessage], keep_tokens: int) -> int:
        """
        Find the cutoff index such that messages from cutoff to end have approximately keep_tokens.
        Returns the number of messages to summarize (from the beginning).
        """
        if not messages:
            return 0

        # Calculate tokens from the end, accumulating until we reach keep_tokens
        tokens_from_end = 0
        keep_count = 0
        for msg in reversed(messages):
            text = f"{msg['timestamp']}: {msg['role']}: \"{msg['content']}\""
            msg_tokens = count_tokens(text)
            if tokens_from_end + msg_tokens > keep_tokens:
                break
            tokens_from_end += msg_tokens
            keep_count += 1

        # Return how many messages to summarize (from the beginning)
        return len(messages) - keep_count

    def summarize_if_needed(self) -> None:
        """
        Trigger summarization when the conversation token count exceeds the configured threshold.

        Uses asyncio.create_task to schedule summarize_by_LLM() without requiring
        callers of record_*_message() to be async/await.
        """
        if self._total_tokens < self.summarize_at_tokens:
            return

        if self._summarize_task is not None and not self._summarize_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[StateManager] No running event loop; cannot schedule summarization.")
            return

        logger.debug(f"[StateManager] Triggering summarization: {self._total_tokens} tokens >= {self.summarize_at_tokens} threshold")
        self._summarize_task = loop.create_task(self.summarize_by_LLM(), name="conversation_summarize")
        self._summarize_task.add_done_callback(self._on_summarize_done)
    
    def _on_summarize_done(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[StateManager] summarize_by_LLM task crashed unexpectedly")
    
    async def summarize_by_LLM(self) -> None:
        """
        Summarize the oldest conversation messages using the language model.

        This version is concurrency-safe with synchronous record_*_message() calls:
        - Snapshot the chunk under a lock
        - Release lock while awaiting the LLM
        - Re-acquire lock to apply summary + prune using the *current* conversation
          so messages appended during the await are not lost.
        """
        with self._lock:
            if not self._conversation:
                return

            # Find cutoff based on tokens to keep
            cutoff = self._find_token_cutoff(self._conversation, self.tail_keep_after_summarize_tokens)

            if cutoff <= 0:
                # Nothing old enough to summarize
                return

            chunk = list(self._conversation[:cutoff])
            first_ts = chunk[0]["timestamp"] if chunk else None
            last_ts = chunk[-1]["timestamp"] if chunk else None
            window = ""
            if first_ts and last_ts:
                window = f"{first_ts} to {last_ts}"

            compact_lines = "\n".join(
                f"{msg['timestamp']}: {msg['role']}: \"{msg['content']}\""
                for msg in chunk
            )
            previous_summary = self.head_summary or "(none)"

        prompt = CONVERSATION_SUMMARIZATION_PROMPT.format(
            window=window,
            previous_summary=previous_summary,
            compact_lines=compact_lines
        )

        try:
            llm = self.event_stream_manager.llm
            llm_output = await llm.generate_response_async(user_prompt=prompt)
            new_summary = (llm_output or "").strip()

            logger.debug(f"[CONVERSATION SUMMARIZATION] llm_output_len={len(llm_output or '')}")

            if not new_summary:
                logger.warning("[CONVERSATION SUMMARIZATION] LLM returned empty summary; not updating.")
                return

            # Apply + prune under lock
            # Remove exactly the messages we summarized (first 'cutoff' messages)
            # New messages added during await will remain at the end
            with self._lock:
                self.head_summary = new_summary
                # Calculate tokens being removed
                removed_tokens = sum(
                    count_tokens(f"{msg['timestamp']}: {msg['role']}: \"{msg['content']}\"")
                    for msg in self._conversation[:cutoff]
                )
                self._total_tokens -= removed_tokens
                if cutoff >= len(self._conversation):
                    # All messages were summarized, clear everything
                    self._conversation = []
                else:
                    # Remove the summarized messages, keep the rest (including any new ones)
                    self._conversation = self._conversation[cutoff:]
                self._update_session_conversation_state()

        except Exception:
            logger.exception("[StateManager] LLM summarization failed. Keeping all messages without summarization.")
            return
