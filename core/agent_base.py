# -*- coding: utf-8 -*-
"""
core.agent_base

Generic, extensible agent that serves every role-specific AI worker.
This is a vanilla "base agent", can be launched by instantiating **AgentBase**
with default arguments; specialised agents simply subclass and override
or extend the protected hooks.

White Collar Agent is an open-source, light version of AI agent developed by CraftOS.
Here are the core features:
- Todo-based task tracking
- Can switch between CLI/GUI mode

Main agent cycle:
- Receive query from user
- Reply or create task
- Task cycle:
    - Action selection and execution
    - Update todos
    - Repeat until completion
"""

from __future__ import annotations

import traceback
import time
import uuid
import json
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from core.action.action import Action

from core.action.action_library import ActionLibrary
from core.action.action_manager import ActionManager
from core.action.action_router import ActionRouter
from core.tui import TUIInterface
from core.internal_action_interface import InternalActionInterface
from core.llm import LLMInterface, LLMCallType
from core.vlm_interface import VLMInterface
from core.database_interface import DatabaseInterface
from core.logger import logger
from core.context_engine import ContextEngine
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from core.trigger import Trigger, TriggerQueue
# STEP_REASONING_PROMPT removed - reasoning is now integrated into action selection
from core.state.types import ReasoningResult
from core.task.task_manager import TaskManager
from core.event_stream.event_stream_manager import EventStreamManager
from core.gui.gui_module import GUIModule
from core.gui.handler import GUIHandler
from decorators.profiler import profile, profile_loop, OperationCategory
from pathlib import Path


@dataclass
class AgentCommand:
    name: str
    description: str
    handler: Callable[[], Awaitable[str | None]]


@dataclass
class TriggerData:
    """Structured data extracted from a Trigger."""
    query: str
    gui_mode: bool | None
    parent_id: str | None

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
        llm_provider: str = "anthropic",
        deferred_init: bool = False,
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
            deferred_init: If True, allow LLM/VLM initialization to be deferred
                until API key is configured (useful for first-time setup).
        """

        # persistence & memory
        self.db_interface = self._build_db_interface(
            data_dir = data_dir, chroma_path=chroma_path
        )

        # LLM + prompt plumbing (may be deferred if API key not yet configured)
        self.llm = LLMInterface(
            provider=llm_provider,
            db_interface=self.db_interface,
            deferred=deferred_init,
        )
        self.vlm = VLMInterface(provider=llm_provider, deferred=deferred_init)

        self.event_stream_manager = EventStreamManager(self.llm)
        
        # action & task layers
        self.action_library = ActionLibrary(self.llm, db_interface=self.db_interface)

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
        self.action_router = ActionRouter(self.action_library, self.llm, self.vlm, self.context_engine)

        self.task_manager = TaskManager(
            db_interface=self.db_interface,
            event_stream_manager=self.event_stream_manager,
            state_manager=self.state_manager,
        )

        InternalActionInterface.initialize(
            self.llm,
            self.task_manager,
            self.state_manager,
            vlm_interface=self.vlm,
            context_engine=self.context_engine,
        )

        GUIHandler.gui_module: GUIModule = GUIModule(
            provider=llm_provider,
            action_library=self.action_library,
            action_router=self.action_router,
            context_engine=self.context_engine,
            action_manager=self.action_manager,
        )

        # ── misc ──
        self.is_running: bool = True
        self._extra_system_prompt: str = self._load_extra_system_prompt()

        self._command_registry: Dict[str, AgentCommand] = {}
        self._register_builtin_commands()

    # =====================================
    # Commands
    # =====================================

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

    # =====================================
    # Agent Turn
    # =====================================
    @profile_loop
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
            
            # Initialize session and extract trigger data
            trigger_data: TriggerData = self._extract_trigger_data(trigger)
            await self._initialize_session(trigger_data.gui_mode, session_id)

            # Handle GUI mode task execution (early return path)
            if self._should_handle_gui_task():
                gui_response = await self._handle_gui_task_execution(
                    trigger_data, session_id
                )
                if self.event_stream_manager and gui_response.get("event_stream_summary"):
                    self.event_stream_manager.log(
                        "agent GUI event",
                        gui_response.get("event_stream_summary"),
                        severity="DEBUG",
                        display_message=None,
                    )
                    self.state_manager.bump_event_stream()
                await self._finalize_action_execution(gui_response.get("new_session_id"), gui_response.get("action_output"), session_id)
                return

            # Select and execute action (standard path)
            action_decision, reasoning = await self._select_action(trigger_data)
            action, action_params, parent_id = await self._retrieve_and_prepare_action(
                action_decision, trigger_data.parent_id
            )
            
            action_output = await self._execute_action(
                action, action_params, trigger_data, reasoning, parent_id, session_id
            )
            
            # Post-action handling
            new_session_id = action_output.get("task_id") or session_id
            await self._finalize_action_execution(new_session_id, action_output, session_id)
            return

        except Exception as e:
            await self._handle_react_error(e, new_session_id, session_id, action_output)
            return
        finally:
            self._cleanup_session()

    # =====================================
    # Internal Methods
    # =====================================

    def _extract_trigger_data(self, trigger: Trigger) -> TriggerData:
        """Extract and structure data from trigger."""
        return TriggerData(
            query=trigger.next_action_description,
            gui_mode=trigger.payload.get("gui_mode"),
            parent_id=trigger.payload.get("parent_action_id"),
        )

    async def _initialize_session(self, gui_mode: bool | None, session_id: str) -> None:
        """Initialize the agent session and set current task ID."""
        STATE.set_agent_property("current_task_id", session_id)
        await self.state_manager.start_session(gui_mode)

    def _should_handle_gui_task(self) -> bool:
        """Check if we should handle GUI task execution."""
        return self.state_manager.is_running_task() and STATE.gui_mode

    async def _handle_gui_task_execution(
        self, trigger_data: TriggerData, session_id: str
    ) -> dict:
        """
        Handle GUI mode task execution.

        Returns:
            Dictionary with action_output, new_session_id, and event_stream_summary
        """
        current_todo = self.state_manager.get_current_todo()

        logger.debug("[GUI MODE] Entered GUI mode.")

        gui_response = await GUIHandler.gui_module.perform_gui_task_step(
            step=current_todo,
            session_id=session_id,
            next_action_description=trigger_data.query,
            parent_action_id=trigger_data.parent_id,
        )

        if gui_response.get("status") != "ok":
            raise ValueError(gui_response.get("message", "GUI task step failed"))

        action_output = gui_response.get("action_output", {})
        new_session_id = action_output.get("task_id") or session_id
        event_stream_summary: str | None = gui_response.get("event_stream_summary")

        return {
            "action_output": action_output,
            "new_session_id": new_session_id,
            "event_stream_summary": event_stream_summary,
        }

    @profile("agent_select_action", OperationCategory.AGENT_LOOP)
    async def _select_action(self, trigger_data: TriggerData) -> tuple[dict, str]:
        """
        Select an action based on current task state.

        Returns:
            Tuple of (action_decision, reasoning) where reasoning is empty string
            for non-task contexts.
        """
        is_running_task = self.state_manager.is_running_task()

        if is_running_task:
            # Check task mode - simple tasks use streamlined action selection
            if self.task_manager.is_simple_task():
                return await self._select_action_in_simple_task(trigger_data.query)
            else:
                return await self._select_action_in_task(trigger_data.query)
        else:
            logger.debug(f"[AGENT QUERY] {trigger_data.query}")
            action_decision = await self.action_router.select_action(query=trigger_data.query)
            if not action_decision:
                raise ValueError("Action router returned no decision.")
            return action_decision, ""

    @profile("agent_select_action_in_task", OperationCategory.AGENT_LOOP)
    async def _select_action_in_task(self, query: str) -> tuple[dict, str]:
        """
        Select action when running within a task context.

        Reasoning is now integrated into the action selection prompt,
        so this method directly calls the action router without a separate
        reasoning step.

        Returns:
            Tuple of (action_decision, reasoning)
        """
        # Single LLM call - reasoning is integrated into action selection
        action_decision = await self.action_router.select_action_in_task(
            query=query,
            GUI_mode=STATE.gui_mode,
        )

        if not action_decision:
            raise ValueError("Action router returned no decision.")

        # Extract reasoning from the action decision (now included in response)
        reasoning = action_decision.get("reasoning", "")
        logger.debug(f"[AGENT REASONING] {reasoning}")

        # Log reasoning to event stream
        if self.event_stream_manager and reasoning:
            self.event_stream_manager.log(
                "agent reasoning",
                reasoning,
                severity="DEBUG",
                display_message=None,
            )
            self.state_manager.bump_event_stream()

        return action_decision, reasoning

    @profile("agent_select_action_in_simple_task", OperationCategory.AGENT_LOOP)
    async def _select_action_in_simple_task(self, query: str) -> tuple[dict, str]:
        """
        Select action for simple task mode - lighter weight than complex task.

        Reasoning is now integrated into the action selection prompt.
        Simple tasks use streamlined prompts and no todo workflow.
        They auto-end after delivering results.

        Returns:
            Tuple of (action_decision, reasoning)
        """
        # Single LLM call - reasoning is integrated into action selection
        action_decision = await self.action_router.select_action_in_simple_task(
            query=query,
        )

        if not action_decision:
            raise ValueError("Action router returned no decision.")

        # Extract reasoning from the action decision (now included in response)
        reasoning = action_decision.get("reasoning", "")
        logger.debug(f"[AGENT REASONING - SIMPLE TASK] {reasoning}")

        # Don't log to event stream for simple tasks (efficiency)

        return action_decision, reasoning

    async def _retrieve_and_prepare_action(
        self, action_decision: dict, initial_parent_id: str | None
    ) -> tuple[Action, dict, str | None]:
        """
        Retrieve action from library and determine parent action ID.
        
        Returns:
            Tuple of (action, action_params, parent_id)
        """
        action_name = action_decision.get("action_name")
        action_params = action_decision.get("parameters", {})
        
        if not action_name:
            raise ValueError("No valid action selected by the router.")

        action = self.action_library.retrieve_action(action_name)
        if action is None:
            raise ValueError(
                f"Action '{action_name}' not found in the library. "
                "Check DB connectivity or ensure the action is registered."
            )
        
        # Use provided parent ID or None
        parent_id = initial_parent_id

        return action, action_params, parent_id or None

    @profile("agent_execute_action", OperationCategory.AGENT_LOOP)
    async def _execute_action(
        self,
        action: Action,
        action_params: dict,
        trigger_data: TriggerData,
        reasoning: str,
        parent_id: str | None,
        session_id: str,
    ) -> dict:
        """Execute the selected action."""
        is_running_task = self.state_manager.is_running_task()
        context = reasoning if reasoning else trigger_data.query
        
        logger.info(f"[ACTION] Ready to run {action}")
        
        return await self.action_manager.execute_action(
            action=action,
            context=context,
            event_stream=STATE.event_stream,
            parent_id=parent_id,
            session_id=session_id,
            is_running_task=is_running_task,
            input_data=action_params,
        )

    async def _finalize_action_execution(
        self, new_session_id: str, action_output: dict, session_id: str
    ) -> None:
        """Handle post-action cleanup and trigger scheduling."""
        self.state_manager.bump_event_stream()
        if not await self._check_agent_limits():
            return
        await self._create_new_trigger(new_session_id, action_output, STATE)

    async def _handle_react_error(
        self,
        error: Exception,
        new_session_id: str | None,
        session_id: str,
        action_output: dict,
    ) -> None:
        """Handle errors during react execution."""
        tb = traceback.format_exc()
        logger.error(f"[REACT ERROR] {error}\n{tb}")

        session_to_use = new_session_id or session_id
        if not session_to_use or not self.event_stream_manager:
            return

        try:
            logger.debug("[REACT ERROR] Logging to event stream")
            self.event_stream_manager.log(
                "error",
                f"[REACT] {type(error).__name__}: {error}\n{tb}",
                display_message=None,
            )
            self.state_manager.bump_event_stream()
            await self._create_new_trigger(session_to_use, action_output, STATE)
        except Exception as e:
            logger.error(
                "[REACT ERROR] Failed to log to event stream or create trigger",
                exc_info=True,
            )

    def _cleanup_session(self) -> None:
        """Safely cleanup session state."""
        try:
            self.state_manager.clean_state()
        except Exception as e:
            logger.warning(f"[REACT] Failed to end session safely: {e}")

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

    # NOTE: _perform_reasoning method was removed.
    # Reasoning is now integrated directly into action selection prompts,
    # reducing the number of LLM calls from 2N to N for N action cycles.

    @profile("agent_create_new_trigger", OperationCategory.TRIGGER)
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
                        next_action_description="Perform the next best action for the task based on the todos and event stream",
                        session_id=new_session_id,
                        payload={
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

    # =====================================
    # Hooks
    # =====================================

    def _load_extra_system_prompt(self) -> str:
        """
        Sub-classes may override to return a *role-specific* system-prompt
        fragment that is **prepended** to the standard one.
        """
        return ""
    
    def _generate_role_info_prompt(self) -> str:
        """
        Subclasses override this to return role-specific system instructions
        (responsibilities, behaviour constraints, expected domain tasks, etc).
        """
        return "You are an AI agent, named 'white collar agent', developed by CraftOS, a general computer-use AI agent that can switch between CLI/GUI mode."

    def _build_db_interface(self, *, data_dir: str, chroma_path: str):
        """A tiny wrapper so a subclass can point to another DB/collection."""
        return DatabaseInterface(
            data_dir = data_dir, chroma_path=chroma_path
        )

    # =====================================
    # Internals
    # =====================================

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

    # =====================================
    # Initialization
    # =====================================

    def reinitialize_llm(self, provider: str | None = None) -> bool:
        """Reinitialize LLM and VLM interfaces with updated configuration.

        Call this after updating environment variables with new API keys.

        Args:
            provider: Optional provider to switch to. If None, uses current provider.

        Returns:
            True if both LLM and VLM were initialized successfully.
        """
        llm_ok = self.llm.reinitialize(provider)
        vlm_ok = self.vlm.reinitialize(provider)

        if llm_ok and vlm_ok:
            logger.info(f"[AGENT] LLM and VLM reinitialized with provider: {self.llm.provider}")
            # Update GUI module provider if needed
            if hasattr(self, 'action_library') and hasattr(GUIHandler, 'gui_module'):
                GUIHandler.gui_module = GUIModule(
                    provider=self.llm.provider,
                    action_library=self.action_library,
                    action_router=self.action_router,
                    context_engine=self.context_engine,
                    action_manager=self.action_manager,
                )
        return llm_ok and vlm_ok

    @property
    def is_llm_initialized(self) -> bool:
        """Check if the LLM interface is properly initialized."""
        return self.llm.is_initialized

    # =====================================
    # MCP Integration
    # =====================================

    async def _initialize_mcp(self) -> None:
        """
        Initialize MCP (Model Context Protocol) client and register tools as actions.

        This method:
        1. Loads MCP configuration from core/config/mcp_config.json
        2. Connects to enabled MCP servers
        3. Discovers tools from each connected server
        4. Registers tools as actions in the ActionRegistry

        MCP tools become available as action sets (e.g., mcp_filesystem) that
        can be selected during task creation.
        """
        try:
            from core.mcp.mcp_client import mcp_client
            from core.config import PROJECT_ROOT

            config_path = PROJECT_ROOT / "core" / "config" / "mcp_config.json"

            if not config_path.exists():
                logger.info(f"[MCP] No MCP config found at {config_path}, skipping MCP initialization")
                return

            logger.info(f"[MCP] Loading config from {config_path}")

            # Initialize MCP client (loads config and connects to servers)
            await mcp_client.initialize(config_path)

            # Log connection status before registering
            status = mcp_client.get_status()
            connected_count = sum(1 for s in status.get("servers", {}).values() if s.get("connected"))
            total_servers = len(status.get("servers", {}))
            logger.info(f"[MCP] Connected to {connected_count}/{total_servers} servers")

            for server_name, server_info in status.get("servers", {}).items():
                if server_info.get("connected"):
                    logger.info(
                        f"[MCP] Server '{server_name}': {server_info['tool_count']} tools available"
                    )

            # Register MCP tools as actions
            tool_count = mcp_client.register_tools_as_actions()

            if tool_count > 0:
                logger.info(
                    f"[MCP] Successfully registered {tool_count} MCP tools as actions"
                )
            else:
                # Provide more detailed diagnostics
                if not mcp_client.servers:
                    logger.warning("[MCP] No MCP servers connected - check if Node.js/npx is installed")
                else:
                    for name, server in mcp_client.servers.items():
                        if not server.is_connected:
                            logger.warning(f"[MCP] Server '{name}' failed to connect")
                        elif not server.tools:
                            logger.warning(f"[MCP] Server '{name}' connected but has no tools")

        except ImportError as e:
            logger.warning(f"[MCP] MCP module not available: {e}")
        except Exception as e:
            import traceback
            logger.warning(f"[MCP] Failed to initialize MCP: {e}")
            logger.debug(f"[MCP] Traceback: {traceback.format_exc()}")

    async def _shutdown_mcp(self) -> None:
        """Gracefully disconnect from all MCP servers."""
        try:
            from core.mcp.mcp_client import mcp_client
            await mcp_client.disconnect_all()
            logger.info("[MCP] Disconnected from all MCP servers")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[MCP] Error during MCP shutdown: {e}")

    # =====================================
    # Skills Integration
    # =====================================

    async def _initialize_skills(self) -> None:
        """
        Initialize the skills system and discover available skills.

        This method:
        1. Loads skills configuration from core/config/skills_config.json
        2. Discovers skills from global (~/.whitecollar/skills/) and project directories
        3. Makes skills available for automatic selection during task creation

        Skills provide specialized instructions that are injected into context
        when selected for a task.
        """
        try:
            from core.skill.skill_manager import skill_manager
            from core.config import PROJECT_ROOT

            config_path = PROJECT_ROOT / "core" / "config" / "skills_config.json"

            logger.info(f"[SKILLS] Loading config from {config_path}")

            # Initialize skill manager (loads config and discovers skills)
            await skill_manager.initialize(config_path)

            # Log discovered skills
            status = skill_manager.get_status()
            total_skills = status.get("total_skills", 0)
            enabled_skills = status.get("enabled_skills", 0)

            if total_skills > 0:
                logger.info(f"[SKILLS] Discovered {total_skills} skills ({enabled_skills} enabled)")
                for skill_name, skill_info in status.get("skills", {}).items():
                    if skill_info.get("enabled"):
                        logger.debug(f"[SKILLS] - {skill_name}: {skill_info.get('description', 'No description')}")
            else:
                logger.info("[SKILLS] No skills discovered. Create skills in ~/.whitecollar/skills/ or .whitecollar/skills/")

        except ImportError as e:
            logger.warning(f"[SKILLS] Skill module not available: {e}")
        except Exception as e:
            import traceback
            logger.warning(f"[SKILLS] Failed to initialize skills: {e}")
            logger.debug(f"[SKILLS] Traceback: {traceback.format_exc()}")

    # =====================================
    # Lifecycle
    # =====================================

    async def run(self, *, provider: str | None = None, api_key: str = "") -> None:
        """
        Launch the interactive TUI loop for the agent.

        Args:
            provider: Optional provider override passed to the TUI before chat
                starts; defaults to the provider configured during
                initialization.
            api_key: Optional API key presented in the TUI for convenience.
        """
        # Initialize MCP client and register tools
        await self._initialize_mcp()

        # Initialize skills system
        await self._initialize_skills()

        try:
            # Allow the TUI to present provider/api-key configuration before chat starts.
            cli = TUIInterface(
                self,
                default_provider=provider or self.llm.provider,
                default_api_key=api_key,
            )
            await cli.start()
        finally:
            # Gracefully shutdown MCP connections
            await self._shutdown_mcp()