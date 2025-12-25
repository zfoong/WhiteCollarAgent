# -*- coding: utf-8 -*-
"""State management utilities for single-user, single-session agents."""

import json
from datetime import datetime
from typing import Dict, List, Literal, Optional, TypedDict

import mss
import mss.tools

from core.event_stream.event_stream_manager import EventStreamManager
from core.logger import logger


class ConversationMessage(TypedDict):
    role: Literal["user", "agent"]
    content: str
    timestamp: str

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
        """
        Initialise a new in-memory session container for the active user.

        Session are created per task and it stores the initial conversation, 
        task, and event stream snapshots so downstream components (LLMs, UIs, tools)
        can read a consistent baseline state. The singleton instance is 
        replaced on every call, meaning this resets any previously 
        active session context.

        Args:
            session_id: Unique identifier for the task that owns the state.
            conversation_state: snapshot of conversation.
            current_task: JSON-serialised task state for the workflow currently being executed.
            event_stream: Event stream buffer that records events happen in task so far.
            gui_mode: Flag indicating whether the agent is running in GUI mode.
        """

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
        Retrieve the current session container if it exists.

        Returns:
            StateSession | None: The current session, or ``None`` when no
            session has been started.
        """
        return cls._instance

    @classmethod
    def end(cls):
        """
        Clear the active session reference.

        Downstream calls to :meth:`get` will raise ``RuntimeError`` until
        :meth:`start` is invoked again. No persistent state is modified.
        """
        cls._instance = None

    """
    Call update when state changes to reflect on the latest state.
    Otherwise the session does not get updated with latest state.
    """
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


class StateManager:
    """Manages conversation snapshots, task state, and runtime session data."""

    def __init__(self, event_stream_manager: EventStreamManager, vlm_interface=None):
        """
        Build a manager responsible for coordinating runtime agent state.

        Args:
            event_stream_manager: Event stream backend used to persist and
                retrieve user-visible logs.
            vlm_interface: Optional visual language model interface used when
                capturing screen context.
        """
        # We have two types of state, persistant and session state
        # Persistant state are state that will not be changed frequently,
        # e.g. agent properties
        # Session state are states that is short-termed, one time used
        # e.g. current conversation, conversation state, action state
        self.tasks: Dict[str, dict] = {}
        self.event_stream_manager = event_stream_manager
        self.agent_properties = {}
        self.vlm_interface = vlm_interface
        self._conversation: List[ConversationMessage] = []

    async def start_session(self, session_id: str = "default", gui_mode: bool = False):
        """
        Prepare the singleton :class:`StateSession` for the provided session id.

        The method rebuilds conversation, task, and event stream snapshots from
        internal caches before delegating to :meth:`StateSession.start`. It is
        typically invoked whenever a new user interaction begins so the agent
        can answer with consistent state.

        Args:
            session_id: Identifier for the logical session being resumed or
                created.
            gui_mode: Whether the session should be flagged for GUI-aware
                behaviour.
        """
        conversation_state = await self.get_conversation_state()

        logger.debug(f"[SESSION ID]: this is the session id: {session_id}")

        current_task = self.get_current_task_state(session_id)

        logger.debug(f"[CURRENT TASK]: this is the current_task: {current_task}")

        event_stream = self.get_event_stream_snapshot(session_id)

        StateSession.start(
            session_id=session_id,
            conversation_state=conversation_state,
            current_task=current_task,
            event_stream=event_stream,
            gui_mode=gui_mode
        )

    
    def end_session(self):
        """
        Terminate the current :class:`StateSession` and drop transient context.

        This is safe to call even when no session is active; downstream calls
        to :meth:`StateSession.get` will error until a new session is started.
        """
        StateSession.end()

    def clear_conversation_history(self) -> None:
        """
        Remove all recorded conversation messages from memory.

        The formatted conversation snapshot is also refreshed on the active
        session so that future consumers see an empty history.
        """
        self._conversation.clear()
        self._update_session_conversation_state()

    def reset(self) -> None:
        """
        Clear all in-memory state managed by the :class:`StateManager`.

        This removes tasks, agent properties, conversation history, and event
        streams before ending the active session, effectively returning the
        agent to a clean boot state.
        """
        self.tasks.clear()
        self.agent_properties = {}
        self.clear_conversation_history()
        if self.event_stream_manager:
            self.event_stream_manager.clear_all()
        self.end_session()
        
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
        """
        Return the current conversation transcript formatted for prompts.

        Only the most recent 25 messages are included to keep context within
        model token limits.

        Returns:
            str: Human-readable summary of the conversation history.
        """
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
        sess = StateSession.get_or_none()
        if sess:
            sess.update_conversation_state(self._format_conversation_state())

    def record_user_message(self, content: str) -> None:
        """
        Append a user-authored message to the tracked conversation history.

        Args:
            content: Raw text of the user's message.
        """
        self._append_conversation_message("user", content)
        self._update_session_conversation_state()

    def record_agent_message(self, content: str) -> None:
        """
        Append an agent-authored message to the tracked conversation history.

        Args:
            content: Raw text of the agent's reply.
        """
        self._append_conversation_message("agent", content)
        self._update_session_conversation_state()
    
    def get_current_step(self, session_id: str) -> Optional[dict]:
        """
        Retrieve the current or next pending step for a workflow.

        Args:
            session_id: Identifier for the workflow session to inspect.

        Returns:
            dict | None: The step dictionary marked ``current`` or ``pending``,
            or ``None`` when the workflow is not found.
        """
        wf = self.tasks.get(session_id)
        if not wf:
            return None
        for st in wf["steps"]:
            if st["status"] == "current":
                return st
        for st in wf["steps"]:
            if st["status"] == "pending":
                return st
        return None
    
    def get_event_stream_snapshot(self, session_id: str, *, max_events: int = 60) -> str:
        """
        Fetch a serialised event stream excerpt for the session.

        Args:
            session_id: Identifier for the event stream to read.
            max_events: Maximum number of recent events to include in the
                snapshot.

        Returns:
            str: Formatted event stream suitable for display or transmission.
        """
        return self.event_stream_manager.snapshot(session_id, max_events=max_events)
        
    def get_current_task_state(self, session_id: str) -> Optional[str]:
        """
        Build a JSON summary of the current task for the given session.

        The summary includes per-step metadata and high-level workflow inputs
        so consumers can reconstruct task context without accessing internal
        structures.

        Args:
            session_id: Identifier used to locate the workflow in ``tasks``.

        Returns:
            str | None: Prettified JSON string of the task state, or ``None``
            when no task is active for the session.
        """
        wf = self.tasks.get(session_id)

        logger.debug(f"[TASK] wf in StateManager: {wf}, session id: {session_id}")

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

    def get_screen_state(self) -> Optional[str]:
        """
        Capture a screenshot of the primary display and send it to the VLM.

        The capture occurs entirely in memory: the primary (or only) monitor is
        grabbed with ``mss``, encoded to PNG bytes, and then forwarded to the
        configured visual language model interface for analysis.

        Returns:
            str | None: Response from the visual model, or an error string if
            capture fails. Raises when no VLM interface is configured.

        Raises:
            RuntimeError: If the ``vlm_interface`` dependency was not provided
                at construction time.
        """
        if self.vlm_interface is None:
            raise RuntimeError("StateManager not initialised with VLMInterface.")
    
        # Capture screen → PNG bytes in memory
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])  # get only primary screen, set index to 0 to get all screens. # TODO, change back to 0
            png_bytes: bytes = mss.tools.to_png(shot.rgb, shot.size, output=None)

        try:
            with mss.mss() as sct:
                monitors = sct.monitors  # List of monitor dicts

                # Always capture primary monitor if it exists, otherwise the only monitor
                primary_index = 1 if len(monitors) > 1 else 0
                shot = sct.grab(monitors[primary_index])

                # Convert to in-memory PNG bytes
                png_bytes = mss.tools.to_png(shot.rgb, shot.size, output=None)

            # Send screenshot bytes to the VLM
            return self.vlm_interface.scan_ui_bytes(png_bytes, use_ocr=False)

        except Exception as e:
            # Log for debugging
            print(f"[ScreenState ERROR] {e}")
            return f"[ScreenState ERROR] {e}"

    def bump_task_state(self, session_id: str) -> None:
        """
        Refresh the session's cached task snapshot from internal state.

        Args:
            session_id: Identifier of the workflow whose task state should be
                propagated to :class:`StateSession`.
        """
        sess = StateSession.get_or_none()
        if sess:
            sess.update_current_task(
                self.get_current_task_state(session_id)
            )
            
    def bump_event_stream(self, session_id: str) -> None:
        """
        Update the session's event stream snapshot from the event manager.

        Args:
            session_id: Identifier for the event stream to capture.
        """
        logger.debug(f"Process Started - Bump event stream for id: {session_id}")
        sess = StateSession.get_or_none()
        if sess:
            logger.debug(f"Process Started - Found event stream for id: {session_id}")
            sess.update_event_stream(self.get_event_stream_snapshot(session_id))
            
    async def bump_conversation_state(self) -> None:
        """
        Synchronise the session's conversation snapshot with the latest history.
        """
        sess = StateSession.get_or_none()
        if sess:
            sess.update_conversation_state(await self.get_conversation_state())

    def is_running_task_with_id(self, session_id: str) -> bool:
        """
        Check whether a workflow with the given session id is tracked.

        Args:
            session_id: Identifier of the workflow to look up.

        Returns:
            bool: ``True`` when the workflow exists, ``False`` otherwise.
        """
        wf = self.tasks.get(session_id)
        if not wf:
            return False
        return True
        
    def is_running_task(self) -> bool:
        """
        Determine if any workflows are currently registered.

        Returns:
            bool: ``True`` when at least one workflow exists.
        """
        if self.tasks:
            return True
        else:
            return False
    
    def add_to_active_task(self, task_id: str, task: dict):
        """
        Add or replace an active workflow definition.

        Args:
            task_id: Identifier under which the workflow should be stored.
            task: Workflow payload to persist.
        """
        self.set_active_task(task_id, task)

    # TODO remove duplicate
    def set_active_task(self, task_id: str, task: dict):
        """
        Persist the workflow state and update session caches accordingly.

        Args:
            task_id: Identifier for the workflow being stored.
            task: Workflow payload to persist.
        """
        self.tasks[task_id] = task
        self.bump_task_state(task_id)

    def remove_active_task(self, task_id: str) -> None:
        """
        Remove a workflow from the active tasks list.

        Args:
            task_id: Identifier of the workflow to remove.
        """        
        self.tasks.pop(task_id, None)
        sess = StateSession.get_or_none()
        if sess and sess.session_id == task_id:
            sess.update_current_task(None)
    
    def get_all_task_state(self) -> List[str]:
        pass    

    def set_agent_property(self, key, value):
        """
        Sets a global agent property (not specific to any task).
        """
        self.agent_properties[key] = value

    def get_agent_property(self, key, default=None):
        """
        Retrieves a global agent property.
        """
        return self.agent_properties.get(key, default)