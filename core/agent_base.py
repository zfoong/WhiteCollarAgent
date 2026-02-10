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

from core.config import (
    AGENT_WORKSPACE_ROOT,
    AGENT_FILE_SYSTEM_PATH,
    AGENT_MEMORY_CHROMA_PATH,
    PROCESS_MEMORY_AT_STARTUP,
    MEMORY_PROCESSING_SCHEDULE_HOUR,
)

from core.tui import TUIInterface
from core.internal_action_interface import InternalActionInterface
from core.llm import LLMInterface, LLMCallType
from core.vlm_interface import VLMInterface
from core.database_interface import DatabaseInterface
from core.logger import logger
from core.memory import MemoryManager, MemoryPointer, MemoryFileWatcher, create_memory_processing_task
from core.context_engine import ContextEngine
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from core.trigger import Trigger, TriggerQueue
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

        self.event_stream_manager = EventStreamManager(
            self.llm,
            agent_file_system_path=AGENT_FILE_SYSTEM_PATH
        )
        
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
        self.action_router = ActionRouter(self.action_library, self.llm, self.context_engine)

        self.task_manager = TaskManager(
            db_interface=self.db_interface,
            event_stream_manager=self.event_stream_manager,
            state_manager=self.state_manager,
            llm_interface=self.llm,
            context_engine=self.context_engine,
        )

        # Clean up any leftover temp directories from previous runs
        self.task_manager.cleanup_all_temp_dirs()

        # ── memory manager for proactive agent ──
        self.memory_manager = MemoryManager(
            agent_file_system_path=str(AGENT_FILE_SYSTEM_PATH),
            chroma_path=str(AGENT_MEMORY_CHROMA_PATH),
        )
        # Connect memory manager to context engine for memory-aware prompts
        self.context_engine.set_memory_manager(self.memory_manager)

        # Index the agent file system on startup (incremental)
        try:
            self.memory_manager.update()
        except Exception as e:
            logger.warning(f"[MEMORY] Failed to update memory index on startup: {e}")

        # Start file watcher to auto-index on changes
        self.memory_file_watcher = MemoryFileWatcher(
            memory_manager=self.memory_manager,
            debounce_seconds=30.0,
        )
        self.memory_file_watcher.start()


        InternalActionInterface.initialize(
            self.llm,
            self.task_manager,
            self.state_manager,
            vlm_interface=self.vlm,
            memory_manager=self.memory_manager,
            context_engine=self.context_engine,
        )

        # Initialize footage callback (will be set by TUI interface later)
        self._tui_footage_callback = None

        GUIHandler.gui_module: GUIModule = GUIModule(
            provider=llm_provider,
            action_library=self.action_library,
            action_router=self.action_router,
            context_engine=self.context_engine,
            action_manager=self.action_manager,
            event_stream_manager=self.event_stream_manager,
            tui_footage_callback=self._tui_footage_callback,
        )

        # Set gui_module reference in InternalActionInterface for GUI event stream integration
        InternalActionInterface.gui_module = GUIHandler.gui_module

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
    # Main Agent Cycle
    # =====================================
    @profile_loop
    async def react(self, trigger: Trigger) -> None:
        """
        Main agent cycle - routes to appropriate workflow handler.

        This method handles 4 distinct workflows:
        1. MEMORY: Background memory processing tasks
        2. GUI TASK: Visual interaction with screen elements
        3. COMPLEX TASK: Multi-step tasks with todo management
        4. SIMPLE TASK: Quick tasks that auto-complete
        5. CONVERSATION: No active task, handle user messages

        Args:
            trigger: The Trigger that wakes the agent up and describes
                when and why the agent should act.
        """
        session_id = trigger.session_id

        try:
            logger.debug("[REACT] starting...")

            # ----- WORKFLOW 1: Special Processing (memory, proactive, onbaording, etc) -----
            if self._is_memory_trigger(trigger):
                task_created = await self._handle_memory_workflow(trigger)
                if not task_created:
                    return  # No events to process

            # Initialize session for all other workflows
            trigger_data: TriggerData = self._extract_trigger_data(trigger)
            await self._initialize_session(trigger_data.gui_mode, session_id)

            # ----- WORKFLOW 2: GUI Task Mode -----
            if self._is_gui_task_mode():
                await self._handle_gui_task_workflow(trigger_data, session_id)
                return

            # ----- WORKFLOW 3: Complex Task Mode -----
            if self._is_complex_task_mode():
                await self._handle_complex_task_workflow(trigger_data, session_id)
                return

            # ----- WORKFLOW 4: Simple Task Mode -----
            if self._is_simple_task_mode():
                await self._handle_simple_task_workflow(trigger_data, session_id)
                return

            # ----- WORKFLOW 5: Conversation Mode (default) -----
            await self._handle_conversation_workflow(trigger_data, session_id)

        except Exception as e:
            await self._handle_react_error(e, None, session_id, {})
        finally:
            self._cleanup_session()

    # =====================================
    # Memory Processing
    # =====================================

    def create_process_memory_task(self) -> str:
        """
        Create a task to process unprocessed events and move them to memory.

        This creates a task that uses the 'memory-processor' skill to guide
        the agent through:
        1. Read EVENT_UNPROCESSED.md for unprocessed events
        2. Evaluate event importance for long-term memory
        3. Check for duplicate memories using memory_search
        4. Write important, unique events to MEMORY.md
        5. Clear processed events from EVENT_UNPROCESSED.md

        Returns:
            The task ID of the created task.
        """
        logger.info("[MEMORY] Creating process memory task")

        # Enable skip_unprocessed_logging to prevent infinite loops
        # (events generated during memory processing won't be added to EVENT_UNPROCESSED.md)
        # This flag is automatically reset when the task ends (in task_manager._end_task)
        self.event_stream_manager.set_skip_unprocessed_logging(True)

        # Create task using the memory-processor skill
        task_id = create_memory_processing_task(self.task_manager)
        logger.info(f"[MEMORY] Process memory task created: {task_id}")

        return task_id

    async def _process_memory_at_startup(self) -> None:
        """
        Process unprocessed events into memory at startup.

        This checks if there are unprocessed events and fires a memory
        processing trigger if needed. The trigger goes through normal
        processing flow which creates the task and executes it.
        """
        import time

        try:
            unprocessed_file = AGENT_FILE_SYSTEM_PATH / "EVENT_UNPROCESSED.md"
            if not unprocessed_file.exists():
                logger.debug("[MEMORY] EVENT_UNPROCESSED.md not found, skipping startup processing")
                return

            # Check if there are events to process (more than just headers)
            content = unprocessed_file.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            # Filter out empty lines and header lines (starting with # or empty)
            event_lines = [l for l in lines if l.strip() and l.strip().startswith("[")]

            if not event_lines:
                logger.info("[MEMORY] No unprocessed events found at startup")
                return

            logger.info(f"[MEMORY] Found {len(event_lines)} unprocessed events at startup, firing processing trigger")

            # Fire a memory_processing trigger (not scheduled, so won't reschedule)
            trigger = Trigger(
                fire_at=time.time(),
                priority=50,
                next_action_description="Process unprocessed events into long-term memory (startup)",
                payload={
                    "type": "memory_processing",
                    "scheduled": False,  # Don't reschedule after this
                },
                session_id="memory_processing_startup",
            )
            await self.triggers.put(trigger)

        except Exception as e:
            logger.warning(f"[MEMORY] Failed to process memory at startup: {e}")

    async def _schedule_daily_memory_processing(self) -> None:
        """
        Schedule a trigger for daily memory processing at the configured hour.

        Creates a trigger that fires at MEMORY_PROCESSING_SCHEDULE_HOUR (default 3am)
        daily to process unprocessed events into long-term memory.
        """
        import time
        from datetime import datetime, timedelta

        try:
            now = datetime.now()
            # Calculate next occurrence of the scheduled hour
            scheduled_time = now.replace(
                hour=MEMORY_PROCESSING_SCHEDULE_HOUR,
                minute=0,
                second=0,
                microsecond=0
            )

            # If the scheduled time has already passed today, schedule for tomorrow
            if scheduled_time <= now:
                scheduled_time += timedelta(days=1)

            fire_at = scheduled_time.timestamp()

            trigger = Trigger(
                fire_at=fire_at,
                priority=100,  # Low priority - background task
                next_action_description="Process unprocessed events into long-term memory (daily scheduled task)",
                payload={
                    "type": "memory_processing",
                    "scheduled": True,
                },
                session_id="memory_processing_daily",
            )

            await self.triggers.put(trigger)
            logger.info(
                f"[MEMORY] Scheduled daily memory processing at "
                f"{scheduled_time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(in {(scheduled_time - now).total_seconds() / 3600:.1f} hours)"
            )

        except Exception as e:
            logger.warning(f"[MEMORY] Failed to schedule daily memory processing: {e}")

    async def _handle_memory_processing_trigger(self, reschedule: bool = True) -> bool:
        """
        Handle the memory processing trigger.

        This is called when a memory processing trigger fires (startup or scheduled).
        It creates a task to process unprocessed events, and optionally reschedules.

        Args:
            reschedule: If True, schedule the next daily processing trigger.

        Returns:
            True if a task was created and processing should continue,
            False if no task was created and react() should return.
        """
        logger.info("[MEMORY] Memory processing trigger fired")
        task_created = False

        try:
            # Check if there are events to process
            unprocessed_file = AGENT_FILE_SYSTEM_PATH / "EVENT_UNPROCESSED.md"
            if unprocessed_file.exists():
                content = unprocessed_file.read_text(encoding="utf-8")
                lines = content.strip().split("\n")
                event_lines = [l for l in lines if l.strip() and l.strip().startswith("[")]

                if event_lines:
                    logger.info(f"[MEMORY] Processing {len(event_lines)} unprocessed events")
                    self.create_process_memory_task()
                    task_created = True
                else:
                    logger.info("[MEMORY] No unprocessed events to process")
            else:
                logger.debug("[MEMORY] EVENT_UNPROCESSED.md not found")

        except Exception as e:
            logger.warning(f"[MEMORY] Failed to process memory: {e}")

        finally:
            # Reschedule for the next day (only for scheduled triggers)
            if reschedule:
                await self._schedule_daily_memory_processing()

        return task_created

    # =====================================
    # Workflow Routing
    # =====================================

    def _extract_trigger_data(self, trigger: Trigger) -> TriggerData:
        """Extract and structure data from trigger."""
        return TriggerData(
            query=trigger.next_action_description,
            gui_mode=trigger.payload.get("gui_mode"),
            parent_id=trigger.payload.get("parent_action_id"),
        )

    async def _initialize_session(self, gui_mode: bool | None, session_id: str) -> None:
        """Initialize the agent session and set current task ID.

        Note: Only sets current_task_id if no task is running, since create_task()
        already sets the task_id which must be used for session cache lookups.
        """
        if not self.state_manager.is_running_task():
            STATE.set_agent_property("current_task_id", session_id)
        await self.state_manager.start_session(gui_mode)

    # ----- Mode Checks -----

    def _is_memory_trigger(self, trigger: Trigger) -> bool:
        """Check if trigger is for memory processing."""
        return trigger.payload.get("type") == "memory_processing"

    def _is_gui_task_mode(self) -> bool:
        """Check if in GUI task execution mode."""
        return self.state_manager.is_running_task() and STATE.gui_mode

    def _is_complex_task_mode(self) -> bool:
        """Check if running a complex task."""
        return self.state_manager.is_running_task() and not self.task_manager.is_simple_task()

    def _is_simple_task_mode(self) -> bool:
        """Check if running a simple task."""
        return self.state_manager.is_running_task() and self.task_manager.is_simple_task()

    # ----- Workflow Handlers -----

    async def _handle_memory_workflow(self, trigger: Trigger) -> bool:
        """
        Handle memory processing workflow.

        Args:
            trigger: The memory processing trigger.

        Returns:
            True if a task was created and processing should continue,
            False if no task was created.
        """
        is_scheduled = trigger.payload.get("scheduled", False)
        return await self._handle_memory_processing_trigger(reschedule=is_scheduled)

    async def _handle_conversation_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle conversation mode - no active task.
        Routes user queries to appropriate actions (send_message, task_start, etc.)
        Uses prefix caching only (no session caching for conversation mode).
        """
        logger.debug(f"[WORKFLOW: CONVERSATION] Query: {trigger_data.query}")

        # Use _select_action to maintain proper call chain
        action_decision, reasoning = await self._select_action(trigger_data)

        action, action_params, parent_id = await self._retrieve_and_prepare_action(
            action_decision, trigger_data.parent_id
        )

        action_output = await self._execute_action(
            action, action_params, trigger_data, reasoning, parent_id, session_id
        )

        new_session_id = action_output.get("task_id") or session_id
        await self._finalize_action_execution(new_session_id, action_output, session_id)

    async def _handle_simple_task_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle simple task mode - streamlined execution without todos.
        Quick tasks that auto-complete after delivering results.
        Uses session caching for efficient multi-turn execution.
        """
        logger.debug(f"[WORKFLOW: SIMPLE TASK] Query: {trigger_data.query}")

        # Use _select_action to maintain proper call chain with session caching
        action_decision, reasoning = await self._select_action(trigger_data)

        action, action_params, parent_id = await self._retrieve_and_prepare_action(
            action_decision, trigger_data.parent_id
        )

        action_output = await self._execute_action(
            action, action_params, trigger_data, reasoning, parent_id, session_id
        )

        new_session_id = action_output.get("task_id") or session_id
        await self._finalize_action_execution(new_session_id, action_output, session_id)

    async def _handle_complex_task_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle complex task mode - full todo workflow with planning.
        Multi-step tasks with todo management and user verification.
        Uses session caching for efficient multi-turn execution.
        """
        logger.debug(f"[WORKFLOW: COMPLEX TASK] Query: {trigger_data.query}")

        # Use _select_action to maintain proper call chain with session caching
        action_decision, reasoning = await self._select_action(trigger_data)

        action, action_params, parent_id = await self._retrieve_and_prepare_action(
            action_decision, trigger_data.parent_id
        )

        action_output = await self._execute_action(
            action, action_params, trigger_data, reasoning, parent_id, session_id
        )

        new_session_id = action_output.get("task_id") or session_id
        await self._finalize_action_execution(new_session_id, action_output, session_id)

    async def _handle_gui_task_workflow(self, trigger_data: TriggerData, session_id: str) -> None:
        """
        Handle GUI task mode - visual interaction workflow.
        Tasks requiring screen interaction via mouse/keyboard.
        """
        logger.debug("[WORKFLOW: GUI TASK] Entered GUI mode.")

        gui_response = await self._handle_gui_task_execution(trigger_data, session_id)

        await self._finalize_action_execution(
            gui_response.get("new_session_id"), gui_response.get("action_output"), session_id
        )

    # ----- GUI Task Helpers -----

    async def _handle_gui_task_execution(
        self, trigger_data: TriggerData, session_id: str
    ) -> dict:
        """
        Handle GUI mode task execution.

        Returns:
            Dictionary with action_output and new_session_id.
            Note: GUI events are now logged to main event stream directly.
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

        return {
            "action_output": action_output,
            "new_session_id": new_session_id,
        }

    # ----- Action Selection -----

    @profile("agent_select_action", OperationCategory.AGENT_LOOP)
    async def _select_action(self, trigger_data: TriggerData) -> tuple[dict, str]:
        """
        Select an action based on current task state.

        Routes to appropriate action selection method:
        - Complex task: _select_action_in_task (with session caching)
        - Simple task: _select_action_in_simple_task (with session caching)
        - Conversation: action_router.select_action (prefix caching only)

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

    # ----- Action Execution -----

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

    # ----- Error Handling -----

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

    # ----- Session Management -----

    def _cleanup_session(self) -> None:
        """Safely cleanup session state."""
        try:
            self.state_manager.clean_state()
        except Exception as e:
            logger.warning(f"[REACT] Failed to end session safely: {e}")

    # ----- Agent Limits -----

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

    # ----- Trigger Management -----

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
                    ),
                    skip_merge=True,  # Session is already explicitly set, no LLM merge check needed
                )
            except Exception as e:
                logger.error(f"[TRIGGER] Failed to enqueue trigger for session {new_session_id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[TRIGGER] Unexpected error in create_new_trigger: {e}", exc_info=True)

    # ----- Chat Handling -----

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
    # State Management
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
                    event_stream_manager=self.event_stream_manager,
                    tui_footage_callback=self._tui_footage_callback,
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
    # External Libraries
    # =====================================

    async def _initialize_external_libraries(self) -> None:
        """Initialize all external app libraries."""
        try:
            from core.external_libraries.notion.external_app_library import NotionAppLibrary
            from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
            from core.external_libraries.slack.external_app_library import SlackAppLibrary
            from core.external_libraries.telegram.external_app_library import TelegramAppLibrary
            from core.external_libraries.linkedin.external_app_library import LinkedInAppLibrary
            from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
            from core.external_libraries.discord.external_app_library import DiscordAppLibrary
            from core.external_libraries.recall.external_app_library import RecallAppLibrary
            from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary

            NotionAppLibrary.initialize()
            WhatsAppAppLibrary.initialize()
            SlackAppLibrary.initialize()
            TelegramAppLibrary.initialize()
            LinkedInAppLibrary.initialize()
            ZoomAppLibrary.initialize()
            DiscordAppLibrary.initialize()
            RecallAppLibrary.initialize()
            GoogleWorkspaceAppLibrary.initialize()
            
            logger.info("[EXT LIBS] External libraries initialized")
        except Exception as e:
            logger.warning(f"[EXT LIBS] Failed to initialize external libraries: {e}")

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

        # Initialize external app libraries
        await self._initialize_external_libraries()

        # Process unprocessed events into memory at startup (if enabled)
        if PROCESS_MEMORY_AT_STARTUP:
            await self._process_memory_at_startup()

        # Schedule daily memory processing
        await self._schedule_daily_memory_processing()

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