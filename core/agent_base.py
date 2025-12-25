# -*- coding: utf-8 -*-
"""
core.agent_base

Generic, extensible agent that serves every role-specific AI worker.
This is a vanilla “base agent”, can be launched by instantiating **AgentBase**
with default arguments; specialised agents simply subclass and override
or extend the protected hooks.

White Collar Agent is an open-source, light version of AI agent developed by CraftOS.
Here are the core features:
- Planning
- Can switch between CLI/GUI mode
- Contain task document for few-shot examples

Main agent cycle:
- Receive query from user
- Reply or create task
- Task cycle:
    - Planning
    - Action
    - Repeat until completion
"""

from __future__ import annotations

import traceback
import time
import uuid
import json
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, NamedTuple, Optional

from core.action.action_library import ActionLibrary
from core.action.action_manager import ActionManager
from core.action.action_router import ActionRouter
from core.tui_interface import TUIInterface
from core.internal_action_interface import InternalActionInterface
from core.llm_interface import LLMInterface
from core.vlm_interface import VLMInterface
from core.database_interface import DatabaseInterface
from core.logger import logger
from core.context_engine import ContextEngine
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from core.gui.handler import GUIHandler
from core.trigger import Trigger, TriggerQueue
from core.prompt import STEP_REASONING_PROMPT
from core.config import MAX_ACTIONS_PER_TASK

from core.task.task_manager import TaskManager
from core.task.task_planner import TaskPlanner
from core.event_stream.event_stream_manager import EventStreamManager


@dataclass
class AgentCommand:
    name: str
    description: str
    handler: Callable[[], Awaitable[str | None]]

class ReasoningResult(NamedTuple):
    reasoning: str
    action_query: str

class AgentBase:
    """
    Foundation class for all agents.

    Sub-classes typically override **one or more** of the following:

    * `_load_extra_system_prompt`     → inject role-specific prompt fragment
    * `_register_extra_actions`       → register additional tools
    * `_build_db_interface`           → point to another Mongo/Chroma DB
    """

    def __init__(
        self,
        *,
        data_dir: str = "core/data",
        chroma_path: str = "./chroma_db",
        llm_provider: str = "byteplus",
    ) -> None:
        """
        This constructor that initializes all agent components.

        Args:
            data_dir: Filesystem path where persistent agent data (plans,
                history, etc.) is stored.
            chroma_path: Directory for the local Chroma vector store used by the
                RAG components.
            llm_provider: Provider name passed to :class:`LLMInterface` and
                :class:`VLMInterface`.
        """        
        # persistence & memory
        self.db_interface = self._build_db_interface(
            data_dir = data_dir, chroma_path=chroma_path
        )

        # LLM + prompt plumbing
        self.llm = LLMInterface(provider=llm_provider, db_interface=self.db_interface)
        self.vlm = VLMInterface(provider=llm_provider)

        self.event_stream_manager = EventStreamManager(self.llm)
        
        # action & task layers
        self.action_library = ActionLibrary(self.llm, db_interface=self.db_interface)
        self.action_library.sync_databases()  # base tools
        self._register_extra_actions()        # role-specific tools
        
        self.task_docs_path = "core/data/task_document"
        if self.task_docs_path:
            try:
                stats = self.db_interface.ingest_task_documents_from_folder(self.task_docs_path)
                logger.debug(f"[TASKDOC SYNC] folder={self.task_docs_path} → {stats}")
            except Exception:
                logger.error("[TASKDOC SYNC] Failed to ingest task documents", exc_info=True)

        self.triggers = TriggerQueue(llm=self.llm)

        # global state
        self.state_manager = StateManager(
            self.event_stream_manager
        )
        self.context_engine = ContextEngine(state_manager=self.state_manager)
        self.context_engine.set_role_info_hook(self._generate_role_info_prompt)

        self.action_manager = ActionManager(
            self.action_library, self.llm, self.db_interface, self.event_stream_manager, self.context_engine, self.state_manager
        )
        self.action_router = ActionRouter(self.action_library, self.llm, self.context_engine)

        self.task_planner = TaskPlanner(llm_interface=self.llm, db_interface=self.db_interface, fewshot_top_k=1, context_engine=self.context_engine)
        self.task_manager = TaskManager(
            self.task_planner,
            self.triggers,
            db_interface=self.db_interface,
            event_stream_manager=self.event_stream_manager,
            state_manager=self.state_manager,
        )

        InternalActionInterface.initialize(
            self.llm,
            self.task_manager,
            self.state_manager,
            vlm_interface=self.vlm,
        )

        # ── misc ──
        self.is_running: bool = True
        self._extra_system_prompt: str = self._load_extra_system_prompt()

        self._command_registry: Dict[str, AgentCommand] = {}
        self._register_builtin_commands()

    # ─────────────────────────── commands ──────────────────────────────

    def _register_builtin_commands(self) -> None:
        self.register_command(
            "/reset",
            "Reset the agent state, clearing tasks, triggers, and session data.",
            self.reset_agent_state,
        )

    def register_command(
        self,
        name: str,
        description: str,
        handler: Callable[[], Awaitable[str | None]],
    ) -> None:
        """
        Register an in-band command that users can invoke from chat.

        Commands are simple hooks (e.g. ``/reset``) that map to coroutine
        handlers. They are surfaced in the UI and routed via
        :meth:`get_commands`.

        Args:
            name: Command string the user types; case-insensitive.
            description: Human-readable description used in help menus.
            handler: Awaitable callable that performs the command action and
                returns an optional message to display.
        """

        self._command_registry[name.lower()] = AgentCommand(
            name=name.lower(), description=description, handler=handler
        )

    def get_commands(self) -> Dict[str, AgentCommand]:
        """Return all registered commands."""

        return self._command_registry

    # ─────────────────────────── agent “turn” ────────────────────────────
    async def react(self, trigger: Trigger) -> None:
        """
        This is the main agent cycle. It executes a full agent turn in response to an incoming trigger.

        The method routes the request through action selection, execution, and
        follow-up scheduling while logging to the event stream. Errors are
        captured and recorded without crashing the outer loop.

        Args:
            trigger: The :class:`Trigger` wakes agent up, and describes when and why the agent
                should act, including session context and payload.
        """
        session_id = trigger.session_id
        new_session_id = None
        action_output = {}  # ensure safe reference in error paths

        try:
            logger.debug("[REACT] starting...")

            STATE.set_agent_property(
                "current_task_id", session_id
            )

            query: str = trigger.next_action_description
            reasoning: str = ""
            current_step_index: int | None = None
            gui_mode = trigger.payload.get("gui_mode")
            parent_id = trigger.payload.get("parent_action_id")

            # ===================================
            # 1. Start Session
            # ===================================
            await self.state_manager.start_session(gui_mode)

            # ===================================
            # 2. Handle GUI mode
            # ===================================
            logger.debug(f"[GUI MODE FLAG] {gui_mode}")
            logger.debug(f"[GUI MODE FLAG - state] {STATE.gui_mode}")

            # GUI-mode handling
            if STATE.gui_mode:
                logger.debug("[GUI MODE] Entered GUI mode.")
                png_bytes = GUIHandler.get_screen_state()
                screen_md = self.vlm.scan_ui_bytes(png_bytes, use_ocr=False)

                if self.event_stream_manager:
                    self.event_stream_manager.log(
                        "screen",
                        screen_md,
                        display_message="Screen summary updated",
                    )

                self.state_manager.bump_event_stream()

            # ===================================
            # 3. Check Limits
            # ===================================
            should_continue:bool = await self._check_agent_limits()
            if not should_continue:
                return

            # ===================================
            # 4. Select Action
            # ===================================
            logger.debug("[REACT] selecting action")
            is_running_task: bool = self.state_manager.is_running_task()

            if is_running_task:
                # Perform reasoning to guide action selection within the task
                reasoning_result: ReasoningResult = await self._perform_reasoning(query=query)
                reasoning: str = reasoning_result.reasoning
                action_query: str = reasoning_result.action_query

                logger.debug(f"[AGENT QUERY] {action_query}")
                action_decision = await self.action_router.select_action_in_task(
                    query=action_query, reasoning=reasoning
                )
            else:
                logger.debug(f"[AGENT QUERY] {query}")
                action_decision = await self.action_router.select_action(
                    query=query
                )

            if not action_decision:
                raise ValueError("Action router returned no decision.")

            # ===================================
            # 5. Get Action
            # ===================================
            action_name = action_decision.get("action_name")
            action_params = action_decision.get("parameters", {})

            if not action_name:
                raise ValueError("No valid action selected by the router.")

            # Retrieve action
            action = self.action_library.retrieve_action(action_name)
            if action is None:
                raise ValueError(
                    f"Action '{action_name}' not found in the library. "
                    "Check DB connectivity or ensure the action is registered."
                )
            
            # Determine parent action
            if not parent_id and is_running_task:
                current_step = self.state_manager.get_current_step()
                if current_step and current_step.get("action_id"):
                    parent_id = current_step["action_id"]

            parent_id = parent_id or None  # enforce None at root

            # ===================================
            # 6. Execute Action
            # ===================================
            try:
                action_output = await self.action_manager.execute_action(
                    action=action,
                    context=reasoning if reasoning else query,
                    event_stream=STATE.event_stream,
                    parent_id=parent_id,
                    session_id=session_id,
                    is_running_task=is_running_task,
                    input_data=action_params,
                )
            except Exception as e:
                logger.error(f"[REACT ERROR] executing action '{action_name}': {e}", exc_info=True)
                raise

            # ===================================
            # 7. Post-Action Handling
            # ===================================
            new_session_id = action_output.get("task_id") or session_id

            self.state_manager.bump_event_stream()

            # Schedule next trigger if continuing a task
            await self._create_new_trigger(new_session_id, action_output, STATE)

        except Exception as e:
            # log error without raising again
            tb = traceback.format_exc()
            logger.error(f"[REACT ERROR] {e}\n{tb}")

            try:
                session_to_use = new_session_id or session_id
                if session_to_use and self.event_stream_manager:
                    logger.debug("[REACT ERROR] logging to event stream")

                    self.event_stream_manager.log(
                        "error",
                        f"[REACT] {type(e).__name__}: {e}\n{tb}",
                        display_message=None,
                    )

                    logger.debug("[AGENT BASE] Action failed")

                    self.state_manager.bump_event_stream()

                    logger.debug("[AGENT BASE] Action failed and then bumped")
                    logger.debug(f"[AGENT BASE] Action Output: {action_output}")

                    # Schedule fallback follow-up only if action_output exists
                    logger.debug("[AGENT BASE] Failed action so create new trigger")
                    await self._create_new_trigger(session_to_use, action_output, STATE)

            except Exception:
                logger.error("[REACT ERROR] Failed to log to event stream or create trigger", exc_info=True)

        finally:
            # Always end session safely
            try:
                self.state_manager.clean_state()
            except Exception:
                logger.warning("[REACT] Failed to end session safely")


    # ───────────────────── helpers used by handlers/commands ──────────────

    async def _check_agent_limits(self) -> bool:
        agent_properties = STATE.get_agent_properties()
        action_count: int = agent_properties.get("action_count", 0)
        max_actions: int = agent_properties.get("max_actions_per_task", 0)
        token_count: int = agent_properties.get("token_count", 0)
        max_tokens: int = agent_properties.get("max_tokens_per_task", 0)

        # Check action limits
        if (action_count / max_actions) >= 1.0:
            response = await self.task_manager.mark_task_cancel(reason=f"Task reached the maximum actions allowed limit: {max_actions}")
            task_cancelled: bool = response
            if self.event_stream_manager and task_cancelled:
                self.event_stream_manager.log(
                    "warning",
                    f"Action limit reached: 100% of the maximum actions ({max_actions} actions) has been used. Aborting task.",
                    display_message=f"Action limit reached: 100% of the maximum ({max_actions} actions) has been used. Aborting task.",
                )
                self.state_manager.bump_event_stream()
            return not task_cancelled
        elif (action_count / max_actions) >= 0.8:
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    "warning",
                    f"Action limit nearing: 80% of the maximum actions ({max_actions} actions) has been used. "
                    "Consider wrapping up the task or informing the user that the task may be too complex. "
                    "If necessary, mark the task as aborted to prevent premature termination.",
                    display_message=None,
                )
                self.state_manager.bump_event_stream()
                return True

        # Check token limits
        if (token_count / max_tokens) >= 1.0:
            response = await self.task_manager.mark_task_cancel(reason=f"Task reached the maximum tokens allowed limit: {max_tokens}")
            task_cancelled: bool = response
            if self.event_stream_manager and task_cancelled:
                self.event_stream_manager.log(
                    "warning",
                    f"Token limit reached: 100% of the maximum tokens ({max_tokens} tokens) has been used. Aborting task.",
                    display_message=f"Action limit reached: 100% of the maximum ({max_tokens} tokens) has been used. Aborting task.",
                )
                self.state_manager.bump_event_stream()
            return not task_cancelled
        elif (token_count / max_tokens) >= 0.8:
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    "warning",
                    f"Token limit nearing: 80% of the maximum tokens ({max_tokens} tokens) has been used. "
                    "Consider wrapping up the task or informing the user that the task may be too complex. "
                    "If necessary, mark the task as aborted to prevent premature termination.",
                    display_message=None,
                )
                self.state_manager.bump_event_stream()
                return True
        
        # No limits close or reached
        return True

    async def _perform_reasoning(self, query: str, retries: int = 2) -> ReasoningResult:
        """
        Perform LLM-based reasoning on a user query to guide action selection.

        This function calls an asynchronous LLM API, validates its structured JSON
        response, and retries if the output is malformed.

        Args:
            query (str): The raw user query from the user.
            retries (int): Number of retry attempts if the LLM returns invalid JSON.

        Returns:
            ReasoningResult: A validated reasoning result containing:
                - reasoning: The model's reasoning output
                - action_query: A refined query used for action selection
        """

        # Build the system prompt using the current context configuration
        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
            system_flags={"policy": False},
        )

        # Format the user prompt with the incoming query
        prompt = STEP_REASONING_PROMPT.format(user_query=query)

        # Track the last parsing/validation error for meaningful failure reporting
        last_error: Exception | None = None

        # Attempt the LLM call and parsing up to (retries + 1) times
        for attempt in range(retries + 1):
            # Await the asynchronous LLM call (non-blocking)
            response = await self.llm.generate_response_async(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )

            # Log raw LLM output for debugging and observability
            print(f"[REASONING attempt={attempt}] {response}")

            try:
                # Parse and validate the structured JSON response
                return self._parse_reasoning_response(response)

            except ValueError as e:
                # Capture the error and retry if attempts remain
                last_error = e

        # All retries exhausted — fail fast with a clear error
        raise RuntimeError("Failed to obtain valid reasoning from LLM") from last_error

    async def _create_new_trigger(self, new_session_id, action_output, STATE):
        """
        Schedule a follow-up trigger when a task is ongoing.

        This helper inspects the current task state and enqueues a new trigger
        so the agent can continue multi-step executions. It is defensive by
        design so failures do not interrupt the main ``react`` loop.

        Args:
            new_session_id: Session identifier to continue.
            action_output: Result dictionary returned by the previous action
                execution; may contain timing metadata.
            state_session: The current :class:`StateSession` object, used to
                propagate session context and payload.
        """
        try:
            if not self.state_manager.is_running_task():
                # Nothing to schedule if no task is running
                return

            # Resolve current step for parent action ID
            parent_action_id = None
            try:
                current_step = self.state_manager.get_current_step()
                if current_step:
                    parent_action_id = current_step.get("action_id")
            except Exception as e:
                logger.error(f"[TRIGGER] Failed to get current step for session {new_session_id}: {e}", exc_info=True)

            # Delay logic
            fire_at_delay = 0.0
            try:
                fire_at_delay = float(action_output.get("fire_at_delay", 0.0))
            except Exception:
                logger.error("[TRIGGER] Invalid fire_at_delay in action_output. Using 0.0", exc_info=True)

            fire_at = time.time() + fire_at_delay

            logger.debug(f"[TRIGGER] Creating new trigger for session: {new_session_id}")

            # Build and enqueue trigger safely
            try:
                await self.triggers.put(
                    Trigger(
                        fire_at=fire_at,
                        priority=5,
                        next_action_description="Perform the next best action for the task based on the plan and event stream",
                        session_id=new_session_id,
                        payload={
                            "parent_action_id": parent_action_id,
                            "gui_mode": STATE.gui_mode,
                        },
                    )
                )
            except Exception as e:
                logger.error(f"[TRIGGER] Failed to enqueue trigger for session {new_session_id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[TRIGGER] Unexpected error in create_new_trigger: {e}", exc_info=True)

    async def _handle_chat_message(self, payload: Dict):
        try:
            user_input: str = payload.get("text", "")
            if not user_input:
                logger.warning("Received empty message.")
                return

            chat_content = user_input
            logger.info(f"[CHAT RECEIVED] {chat_content}")
            gui_mode = payload.get("gui_mode")
            await self.state_manager.start_session(gui_mode)

            self.state_manager.record_user_message(chat_content)

            await self.triggers.put(
                Trigger(
                    fire_at=time.time(),
                    priority=1,
                    next_action_description=(
                        "Please perform action that best suit this user chat "
                        f"you just received: {chat_content}"
                    ),
                    session_id="chat",
                    payload={"gui_mode": gui_mode},
                )
            )

        except Exception as e:
            logger.error(f"Error handling incoming message: {e}", exc_info=True)

    # ────────────────────────────── hooks ────────────────────────────────

    def _load_extra_system_prompt(self) -> str:
        """
        Sub-classes may override to return a *role-specific* system-prompt
        fragment that is **prepended** to the standard one.
        """
        return ""

    def _register_extra_actions(self) -> None:
        """
        Sub-classes override to register additional Action objects,
        e.g.::

            from .actions import email_campaign
            self.action_library.register_module(email_campaign)
        """
        return
    
    def _generate_role_info_prompt(self) -> str:
        """
        Subclasses override this to return role-specific system instructions
        (responsibilities, behaviour constraints, expected domain tasks, etc).
        """
        return ""

    def _build_db_interface(self, *, data_dir: str, chroma_path: str):
        """A tiny wrapper so a subclass can point to another DB/collection."""
        return DatabaseInterface(
            data_dir = data_dir, chroma_path=chroma_path
        )

    # ────────────────────────── internals ────────────────────────────────

    async def reset_agent_state(self) -> str:
        """
        Reset runtime state so the agent behaves like a fresh instance.

        Clears triggers, resets task and state managers, and purges event
        streams. Useful for debugging or user-initiated resets.

        Returns:
            Confirmation message summarizing the reset.
        """

        await self.triggers.clear()
        self.task_manager.reset()
        self.state_manager.reset()
        self.event_stream_manager.clear_all()

        return "Agent state reset. Starting fresh." 

    def _parse_reasoning_response(self, response: str) -> ReasoningResult:
        """
        Parse and validate the structured JSON response from the reasoning LLM call.
        """
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {response}") from e

        if not isinstance(parsed, dict):
            raise ValueError(f"LLM response is not a JSON object: {parsed}")

        reasoning = parsed.get("reasoning")
        action_query = parsed.get("action_query")

        if not isinstance(reasoning, str) or not isinstance(action_query, str):
            raise ValueError(f"Invalid reasoning schema: {parsed}")

        return ReasoningResult(
            reasoning=reasoning,
            action_query=action_query,
        )

    # ─────────────────────────── lifecycle ──────────────────────────────
    async def run(self, *, provider: str | None = None, api_key: str = "") -> None:
        """
        Launch the interactive TUI loop for the agent.

        Args:
            provider: Optional provider override passed to the TUI before chat
                starts; defaults to the provider configured during
                initialization.
            api_key: Optional API key presented in the TUI for convenience.
        """

        # Allow the TUI to present provider/api-key configuration before chat starts.
        cli = TUIInterface(
            self,
            default_provider=provider or self.llm.provider,
            default_api_key=api_key,
        )
        await cli.start()