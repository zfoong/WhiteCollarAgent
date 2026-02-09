# -*- coding: utf-8 -*-
"""
core.action.action_router

Agent uses this module to select actions based on the plan

@author: zfoong
"""

import json
import ast
from typing import Optional, List, Dict, Any, Tuple
from core.action.action_library import ActionLibrary
from core.context_engine import ContextEngine
from core.state.agent_state import STATE

from core.logger import logger
from core.llm import LLMCallType
from core.prompt import SELECT_ACTION_IN_TASK_PROMPT, SELECT_ACTION_PROMPT, SELECT_ACTION_IN_GUI_PROMPT, SELECT_ACTION_IN_SIMPLE_TASK_PROMPT, GUI_ACTION_SPACE_PROMPT
from decorators.profiler import profile, OperationCategory


def _is_visible_in_mode(action, GUI_mode: bool) -> bool:
    """
    Returns True if the action should be visible under the given GUI_mode.
    - Empty/missing mode is visible in both modes.
    - 'GUI' is visible only when GUI_mode=True.
    - 'CLI' is visible only when GUI_mode=False.
    - 'ALL' is visible when GUI_mode=False and GUI_mode=True.
    """
    mode = getattr(action, "mode", None)
    if not mode:  # None, "", or falsy -> visible in both
        return True
    if mode == 'ALL':
        return True
    m = str(mode).strip().upper()
    if GUI_mode:
        return m == "GUI"
    else:
        return m == "CLI"
# ------------------------------
# ActionRouter
# ------------------------------
class ActionRouter:
    """
    Selects actions based on user queries, with an LLM verifying correctness
    or creating new actions on the fly.
    """

    def __init__(self, action_library: ActionLibrary, llm_interface, context_engine: ContextEngine):
        """
        Initialize the router responsible for selecting or creating actions.

        Args:
            action_library: Repository for storing and retrieving action definitions.
            llm_interface: LLM client used to reason about which action to run.
            context_engine: Provider of system prompts and context formatting.
        """
        self.action_library = action_library
        self.llm_interface = llm_interface
        self.context_engine = context_engine

    @profile("action_router_select_action", OperationCategory.ACTION_ROUTING)
    async def select_action(
        self,
        query: str,
        action_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        default action selection function when not in a task
        For now, only choosing between chat, ignore or create and start task

        1. Retrieves top-k candidate action names from ChromaDB.
        2. Builds a candidate list with searched and default action for the LLM.
        3. Asks the LLM if any candidate is valid, or if a new action is needed.
        4. If new action is needed, create & store it, then return it.
        5. Otherwise, return the chosen existing action with its parameters.

        Args:
            query: User's request that should be satisfied by an action.
            action_type: Optional type filter forwarded to the LLM.
            context: Additional conversational context to ground the prompt.

        Returns:
            Dict[str, Any]: Parsed decision containing ``action_name`` and
            ``parameters`` ready for execution or creation.
        """
        conversation_mode_actions = ["send_message", "task_start", "task_update_todos", "task_end", "ignore"]
        action_candidates = []
        
        for action in conversation_mode_actions:
            act = self.action_library.retrieve_action(action_name=action)
            if act:
                action_candidates.append({
                    "name": act.name,
                    "description": act.description,
                    "type": act.action_type,
                    "input_schema": act.input_schema,
                    "output_schema": act.output_schema
                })
    
        # Build the instruction prompt for the LLM
        # KV CACHING: Inject dynamic context into user prompt
        # Memory context provides relevant memories for context-aware decisions
        prompt = SELECT_ACTION_PROMPT.format(
            event_stream=self.context_engine.get_event_stream(),
            memory_context=self.context_engine.get_memory_context(query),
            query=query,
            action_candidates=self._format_candidates(action_candidates),
        )

        decision = await self._prompt_for_decision(prompt, is_task=False)

        logger.debug(
            f"Action router selected action={decision.get('action_name')} "
            f"with parameters={decision.get('parameters')}"
        )

        return decision

    @profile("action_router_select_action_in_task", OperationCategory.ACTION_ROUTING)
    async def select_action_in_task(
        self,
        query: str,
        action_type: Optional[str] = None,
        GUI_mode=False,
    ) -> Dict[str, Any]:
        """
        When a task is running, this action selection will be used.

        Reasoning is now integrated directly into the action selection prompt,
        eliminating the need for a separate reasoning LLM call.

        1. Gets compiled action list from task's action sets.
        2. Builds a candidate list for the LLM.
        3. LLM reasons about the current state and selects an action.
        4. Returns the chosen action along with parameters and reasoning.

        Args:
            query: Task-level instruction for the next step.
            action_type: Optional action type hint supplied to the LLM.
            GUI_mode: Whether the user is interacting through a GUI, affecting
                which actions are visible.

        Returns:
            Dict[str, Any]: Decision payload with ``action_name``, ``parameters``,
            and ``reasoning`` for execution.
        """
        action_candidates = []
        action_name_candidates = []

        # List of filtered actions
        ignore_actions = ["ignore"]

        # Get compiled action list from task's action sets
        compiled_actions = self._get_current_task_compiled_actions()

        # Use static compiled list - NO RAG SEARCH
        action_candidates = self._build_candidates_from_compiled_list(
            compiled_actions, GUI_mode, ignore_actions
        )
        logger.info(f"ActionRouter using compiled action list: {len(action_candidates)} actions")

        # Build the instruction prompt for the LLM
        # KV CACHING: Static/session-static content first, dynamic (event_stream) last
        # Reasoning is now part of the action selection prompt (single LLM call)
        #
        # For session caching:
        # - static_prompt: everything except event_stream (cached prefix)
        # - full_prompt: includes event_stream (used for first call or non-cached)
        # Note: task_state includes skill instructions and is session-static (doesn't change during task)
        # Memory context provides relevant memories for context-aware decisions
        task_state = self.context_engine.get_task_state()
        memory_context = self.context_engine.get_memory_context(query)
        static_prompt = SELECT_ACTION_IN_TASK_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=task_state,
            memory_context=memory_context,
            event_stream="",  # Empty for static prompt
            query=query,
            action_candidates=self._format_candidates(action_candidates),
        )
        full_prompt = SELECT_ACTION_IN_TASK_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=task_state,
            memory_context=memory_context,
            event_stream=self.context_engine.get_event_stream(),
            query=query,
            action_candidates=self._format_candidates(action_candidates),
        )

        max_retries = 3
        for attempt in range(max_retries):
            decision = await self._prompt_for_decision(
                full_prompt,
                is_task=True,
                static_prompt=static_prompt,
                call_type=LLMCallType.ACTION_SELECTION,
            )

            selected_action_name = decision.get("action_name", "")
            if selected_action_name == "":
                return decision

            selected_action = self.action_library.retrieve_action(selected_action_name)
            if selected_action is not None and _is_visible_in_mode(selected_action, GUI_mode):
                decision["parameters"] = self._ensure_parameters(decision.get("parameters"))
                return decision

            logger.warning(
                f"Received invalid action name '{selected_action_name}' during selection attempt {attempt + 1}"
            )

        # 3. If we fail to find a valid action name after the retries, raise an error
        raise ValueError("Invalid selected action returned by LLM after retries.")

    @profile("action_router_select_action_in_simple_task", OperationCategory.ACTION_ROUTING)
    async def select_action_in_simple_task(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """
        Action selection for simple task mode - streamlined without todo workflow.

        Reasoning is now integrated directly into the action selection prompt,
        eliminating the need for a separate reasoning LLM call.

        Simple tasks don't use todos and auto-end after delivering results.
        This method excludes todo-related actions and uses a simpler prompt.

        Args:
            query: Task-level instruction for the next step.

        Returns:
            Dict[str, Any]: Decision payload with ``action_name``, ``parameters``,
            and ``reasoning`` for execution.
        """
        action_candidates = []
        action_name_candidates = []

        # Exclude todo management and ignore actions for simple tasks
        ignore_actions = ["ignore", "task_update_todos"]

        # Get compiled action list from task's action sets
        compiled_actions = self._get_current_task_compiled_actions()

        # Use static compiled list - NO RAG SEARCH
        action_candidates = self._build_candidates_from_compiled_list(
            compiled_actions, GUI_mode=False, ignore_actions=ignore_actions
        )
        logger.info(f"ActionRouter (simple task) using compiled action list: {len(action_candidates)} actions")

        # Build the instruction prompt using simple task prompt
        # KV CACHING: Static/session-static content first, dynamic (event_stream) last
        # Reasoning is now part of the action selection prompt (single LLM call)
        #
        # For session caching:
        # - static_prompt: everything except event_stream (cached prefix)
        # - full_prompt: includes event_stream (used for first call or non-cached)
        # Note: task_state includes skill instructions and is session-static (doesn't change during task)
        # Memory context provides relevant memories for context-aware decisions
        task_state = self.context_engine.get_task_state()
        memory_context = self.context_engine.get_memory_context(query)
        static_prompt = SELECT_ACTION_IN_SIMPLE_TASK_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=task_state,
            memory_context=memory_context,
            event_stream="",  # Empty for static prompt
            query=query,
            action_candidates=self._format_candidates(action_candidates),
        )
        full_prompt = SELECT_ACTION_IN_SIMPLE_TASK_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=task_state,
            memory_context=memory_context,
            event_stream=self.context_engine.get_event_stream(),
            query=query,
            action_candidates=self._format_candidates(action_candidates),
        )

        max_retries = 3
        for attempt in range(max_retries):
            decision = await self._prompt_for_decision(
                full_prompt,
                is_task=True,
                static_prompt=static_prompt,
                call_type=LLMCallType.ACTION_SELECTION,
            )

            selected_action_name = decision.get("action_name", "")
            if selected_action_name == "":
                return decision

            selected_action = self.action_library.retrieve_action(selected_action_name)
            if selected_action is not None and _is_visible_in_mode(selected_action, GUI_mode=False):
                decision["parameters"] = self._ensure_parameters(decision.get("parameters"))
                return decision

            logger.warning(
                f"Received invalid action name '{selected_action_name}' during simple task selection attempt {attempt + 1}"
            )

        raise ValueError("Invalid selected action returned by LLM after retries.")

    @profile("action_router_select_action_in_GUI", OperationCategory.ACTION_ROUTING)
    async def select_action_in_GUI(
        self, 
        query: str,
        action_type: Optional[str] = None,
        GUI_mode=False,
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """
        GUI-specific action selection when a task is running.

        Reasoning is now integrated directly into the action selection prompt,
        using VLM to see the screen and select the appropriate action.

        1. Gets compiled action list from task's action sets.
        2. VLM reasons about the screen state, selects an action, and identifies
           the UI element to interact with (if applicable).
        3. Returns the decision with action, parameters, reasoning, and element_to_find.

        Args:
            query: Task-level instruction for the next step.
            gui_state: Description of the current screen state (from VLM/OmniParser).
            image_bytes: Screenshot bytes for VLM to see the screen.
            action_type: Optional action type hint supplied to the LLM.
            GUI_mode: Whether the user is interacting through a GUI, affecting
                which actions are visible.

        Returns:
            Dict[str, Any]: Decision payload with ``action_name``, ``parameters``,
            ``reasoning``, and ``element_to_find`` for execution.
        """
        # GUI mode uses hardcoded compact action space prompt for efficiency
        # No need to build candidates dynamically - action validation happens after selection
        compiled_actions = self._get_current_task_compiled_actions()
        logger.info(f"ActionRouter (GUI) using compact action space prompt with {len(compiled_actions)} actions")

        # Build the instruction prompt for the LLM
        # KV CACHING: Static/session-static content first, dynamic (event_stream) last
        #
        # For session caching (BytePlus):
        # - static_prompt: everything except event_stream (cached prefix)
        # - full_prompt: includes event_stream (used for first call or non-cached)
        # Note: task_state includes skill instructions and is session-static (doesn't change during task)
        task_state = self.context_engine.get_task_state()
        memory_context = self.context_engine.get_memory_context(query)
        static_prompt = SELECT_ACTION_IN_GUI_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=task_state,
            event_stream="",  # Empty for static prompt
            memory_context=memory_context,
            reasoning=reasoning,
            query=query,
            gui_action_space=GUI_ACTION_SPACE_PROMPT,
        )
        full_prompt = SELECT_ACTION_IN_GUI_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=task_state,
            event_stream=self.context_engine.get_event_stream(),
            memory_context=memory_context,
            reasoning=reasoning,
            query=query,
            gui_action_space=GUI_ACTION_SPACE_PROMPT,
        )

        max_retries = 3
        for attempt in range(max_retries):
            decision = await self._prompt_for_decision_gui(
                full_prompt,
                is_task=True,
                static_prompt=static_prompt,
                call_type=LLMCallType.GUI_ACTION_SELECTION,
            )

            selected_action_name = decision.get("action_name", "")
            if selected_action_name == "":
                return decision

            selected_action = self.action_library.retrieve_action(selected_action_name)
            if selected_action is not None and _is_visible_in_mode(selected_action, GUI_mode):
                decision["parameters"] = self._ensure_parameters(decision.get("parameters"))
                return decision

            logger.warning(
                f"Received invalid action name '{selected_action_name}' during selection attempt {attempt + 1}"
            )

        # 3. If we fail to find a valid action name after the retries, raise an error
        raise ValueError("Invalid selected action returned by LLM after retries.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _prompt_for_decision(
        self,
        prompt: str,
        is_task: bool = False,
        static_prompt: Optional[str] = None,
        call_type: str = LLMCallType.ACTION_SELECTION,
    ) -> Dict[str, Any]:
        """
        Prompt the LLM for an action decision with session caching support.

        For BytePlus session caching:
        - First call: Send full prompt (static_prompt + event_stream)
        - Subsequent calls: Send only delta events (new events since last call)

        Args:
            prompt: The full prompt (used for non-session calls or first call)
            is_task: Whether this is a task context (enables session caching)
            static_prompt: The static parts of the prompt without event_stream
                          (used for session cache creation)
            call_type: The type of LLM call for session cache keying
        """
        max_retries = 3
        last_error: Optional[Exception] = None
        current_prompt = prompt

        # Get current task_id for session cache (if running in a task)
        current_task_id = STATE.get_agent_property("current_task_id", "") if is_task else ""

        for attempt in range(max_retries):
            # KV CACHING: System prompt is now STATIC only
            # Dynamic content (event_stream) is handled separately for session caching
            system_prompt, _ = self.context_engine.make_prompt(
                user_flags={"query": False, "expected_output": False},
                system_flags={"agent_info": not is_task, "policy": False},
            )

            raw_response = None

            # Use session cache if we're in a task context AND session is registered
            # Session is only registered for complex tasks (not simple tasks)
            if current_task_id and is_task:
                has_session = self.llm_interface.has_session_cache(current_task_id, call_type)

                if has_session:
                    # Session is registered (complex task) - use session caching
                    # Check if we've synced events before (i.e., made at least one LLM call)
                    from core.event_stream.event_stream_manager import EventStreamManager
                    event_stream_manager: EventStreamManager = self.context_engine.state_manager.event_stream_manager
                    stream = event_stream_manager.get_stream()
                    has_synced_before = stream.has_session_sync(call_type) if stream else False

                    if has_synced_before:
                        # We've made calls before - send only delta events
                        delta_events, has_delta = self.context_engine.get_event_stream_delta(call_type)

                        if has_delta:
                            # Send only the new events
                            logger.info(f"[SESSION CACHE] Sending delta events for {call_type}")
                            raw_response = await self.llm_interface.generate_response_with_session_async(
                                task_id=current_task_id,
                                call_type=call_type,
                                user_prompt=delta_events,
                                system_prompt_for_new_session=system_prompt,
                            )
                            # Mark events as synced after successful call
                            self.context_engine.mark_event_stream_synced(call_type)
                        else:
                            # No new events - this could mean summarization happened
                            logger.info(f"[SESSION CACHE] No delta events, resetting cache for {call_type}")
                            self.llm_interface.end_session_cache(current_task_id, call_type)
                            self.context_engine.reset_event_stream_sync(call_type)
                            # Fall through to first-call path
                            has_synced_before = False

                    if not has_synced_before:
                        # First call with session - send full prompt to establish session
                        logger.info(f"[SESSION CACHE] Creating new session for {call_type} (first call)")
                        raw_response = await self.llm_interface.generate_response_with_session_async(
                            task_id=current_task_id,
                            call_type=call_type,
                            user_prompt=current_prompt,  # Full prompt with event_stream
                            system_prompt_for_new_session=system_prompt,
                        )
                        # Mark events as synced after successful session creation
                        self.context_engine.mark_event_stream_synced(call_type)
                else:
                    # No session registered (simple task) - use prefix cache / regular response
                    raw_response = await self.llm_interface.generate_response_async(system_prompt, current_prompt)
            else:
                # Not in task context - use regular response
                raw_response = await self.llm_interface.generate_response_async(system_prompt, current_prompt)

            decision, parse_error = self._parse_action_decision(raw_response)
            if decision is not None:
                decision.setdefault("parameters", {})
                decision["parameters"] = self._ensure_parameters(decision.get("parameters"))
                return decision

            feedback_error = parse_error or "unknown parsing error"
            last_error = ValueError(f"Unable to parse action decision on attempt {attempt + 1}: {feedback_error}")
            logger.warning(
                f"Failed to parse LLM decision on attempt {attempt + 1}: "
                f"{raw_response} | error={feedback_error}"
            )
            current_prompt = self._augment_prompt_with_feedback(prompt, attempt + 1, raw_response, feedback_error)

        if last_error:
            raise last_error
        raise ValueError("Unable to parse LLM decision")
        
    async def _prompt_for_decision_gui(
        self,
        prompt: str,
        is_task: bool = False,
        static_prompt: Optional[str] = None,
        call_type: str = LLMCallType.GUI_ACTION_SELECTION,
    ) -> Dict[str, Any]:
        """
        Prompt the LLM for a GUI action decision with session caching support.

        For BytePlus session caching:
        - First call: Send full prompt (static_prompt + event_stream)
        - Subsequent calls: Send only delta events (new events since last call)

        Args:
            prompt: The full prompt (used for non-session calls or first call)
            is_task: Whether this is a task context (enables session caching)
            static_prompt: The static parts of the prompt without event_stream
                          (used for session cache creation)
            call_type: The type of LLM call for session cache keying
        """
        max_retries = 3
        last_error: Optional[Exception] = None
        current_prompt = prompt

        # Get current task_id for session cache (if running in a task)
        current_task_id = STATE.get_agent_property("current_task_id", "") if is_task else ""

        for attempt in range(max_retries):
            # KV CACHING: System prompt is now STATIC only
            # Dynamic content (event_stream) is handled separately for session caching
            system_prompt, _ = self.context_engine.make_prompt(
                user_flags={"query": False, "expected_output": False},
                system_flags={"role_info": not is_task, "agent_info": not is_task, "policy": False},
            )

            raw_response = None

            # Use session cache if we're in a task context AND session is registered
            if current_task_id and is_task:
                has_session = self.llm_interface.has_session_cache(current_task_id, call_type)

                if has_session:
                    # Session is registered - use session caching
                    # Check if we've synced events before (i.e., made at least one LLM call)
                    from core.event_stream.event_stream_manager import EventStreamManager
                    event_stream_manager: EventStreamManager = self.context_engine.state_manager.event_stream_manager
                    stream = event_stream_manager.get_stream()
                    has_synced_before = stream.has_session_sync(call_type) if stream else False

                    if has_synced_before:
                        # We've made calls before - send only delta events
                        delta_events, has_delta = self.context_engine.get_event_stream_delta(call_type)

                        if has_delta:
                            # Send only the new events
                            logger.info(f"[SESSION CACHE] GUI: Sending delta events for {call_type}")
                            raw_response = await self.llm_interface.generate_response_with_session_async(
                                task_id=current_task_id,
                                call_type=call_type,
                                user_prompt=delta_events,
                                system_prompt_for_new_session=system_prompt,
                            )
                            # Mark events as synced after successful call
                            self.context_engine.mark_event_stream_synced(call_type)
                        else:
                            # No new events - this could mean summarization happened
                            logger.info(f"[SESSION CACHE] GUI: No delta events, resetting cache for {call_type}")
                            self.llm_interface.end_session_cache(current_task_id, call_type)
                            self.context_engine.reset_event_stream_sync(call_type)
                            # Fall through to first-call path
                            has_synced_before = False

                    if not has_synced_before:
                        # First call with session - send full prompt to establish session
                        logger.info(f"[SESSION CACHE] GUI: Creating new session for {call_type} (first call)")
                        raw_response = await self.llm_interface.generate_response_with_session_async(
                            task_id=current_task_id,
                            call_type=call_type,
                            user_prompt=current_prompt,  # Full prompt with event_stream
                            system_prompt_for_new_session=system_prompt,
                        )
                        # Mark events as synced after successful session creation
                        self.context_engine.mark_event_stream_synced(call_type)
                else:
                    # No session registered - use prefix cache / regular response
                    raw_response = await self.llm_interface.generate_response_async(system_prompt, current_prompt)
            else:
                # Not in task context - use regular response
                raw_response = await self.llm_interface.generate_response_async(system_prompt, current_prompt)

            decision, parse_error = self._parse_action_decision(raw_response)
            if decision is not None:
                decision.setdefault("parameters", {})
                decision["parameters"] = self._ensure_parameters(decision.get("parameters"))
                return decision

            feedback_error = parse_error or "unknown parsing error"
            last_error = ValueError(f"Unable to parse action decision on attempt {attempt + 1}: {feedback_error}")
            logger.warning(
                f"Failed to parse LLM decision on attempt {attempt + 1}: "
                f"{raw_response} | error={feedback_error}"
            )
            current_prompt = self._augment_prompt_with_feedback(prompt, attempt + 1, raw_response, feedback_error)

        if last_error:
            raise last_error
        raise ValueError("Unable to parse LLM decision")

    def _parse_action_decision(self, raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as json_error:
            try:
                parsed = ast.literal_eval(raw)
            except Exception as eval_error:
                logger.error(f"Unable to parse action decision: {raw}")
                return None, f"json error: {json_error}; literal_eval error: {eval_error}"

        if not isinstance(parsed, dict):
            logger.error(f"Parsed action decision is not a dict: {raw}")
            return None, "parsed value is not a dictionary"

        return parsed, None

    def _augment_prompt_with_feedback(
        self,
        base_prompt: str,
        attempt: int,
        raw_response: str,
        error_message: str,
    ) -> str:
        feedback_block = (
            f"\n\nPrevious attempt {attempt} failed to parse because: {error_message}. "
            "Review your last reply above (shown in the RAW RESPONSE section) and return a corrected response. "
            "You must return ONLY a JSON object with action_name and parameters fields. "
            "Do not include any additional commentary, code fences, or explanatory text.\n\n"
            "RAW RESPONSE:\n"
            f"{raw_response}\n"
            "--- End of RAW RESPONSE ---\n"
            "Respond now with the corrected JSON object."
        )
        return base_prompt + feedback_block

    def _format_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        if not candidates:
            return "[]"

        simplified: List[Dict[str, Any]] = []
        for candidate in candidates:
            # input_schema = candidate.get("input_schema") or {}
            # if isinstance(input_schema, dict):
            #     input_fields = list(input_schema.keys())
            # elif isinstance(input_schema, list):
            #     input_fields = list(input_schema)
            # else:
            #     input_fields = []

            output_schema = candidate.get("output_schema") or {}
            if isinstance(output_schema, dict):
                output_fields = list(output_schema.keys())
            elif isinstance(output_schema, list):
                output_fields = list(output_schema)
            else:
                output_fields = []

            simplified.append(
                {
                    "name": candidate.get("name"),
                    "description": candidate.get("description"),
                    "input_schema": candidate.get("input_schema"),
                    "output_schema": output_fields
                }
            )

        return json.dumps(simplified, indent=2, ensure_ascii=False)

    def _format_action_names(self, names: List[str]) -> str:
        if not names:
            return "[]"
        return json.dumps(names, indent=2, ensure_ascii=False)

    # NOTE: _format_reasoning was removed - reasoning is now integrated into action selection

    def _format_event_stream(self, event_stream: str | list | dict | None) -> str:
        if not event_stream:
            return "No prior events available."
        if isinstance(event_stream, (list, dict)):
            return json.dumps(event_stream, indent=2, ensure_ascii=False)
        return str(event_stream)

    def _ensure_parameters(self, parameters: Any) -> Dict[str, Any]:
        if isinstance(parameters, dict):
            return parameters
        return {}

    def _build_candidates_from_compiled_list(
        self,
        compiled_actions: List[str],
        GUI_mode: bool,
        ignore_actions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Build action candidate list from pre-compiled action names.

        This method is used when the task has a static action list (from action sets),
        eliminating the need for RAG-based action retrieval.

        Args:
            compiled_actions: Pre-compiled list of action names from task.compiled_actions
            GUI_mode: Whether to filter for GUI mode visibility
            ignore_actions: List of action names to exclude

        Returns:
            List of action candidate dictionaries for the LLM prompt
        """
        ignore_actions = ignore_actions or []
        candidates = []

        for name in compiled_actions:
            if name in ignore_actions:
                continue

            act = self.action_library.retrieve_action(name)
            if not act:
                continue

            if not _is_visible_in_mode(act, GUI_mode):
                continue

            candidates.append({
                "name": act.name,
                "description": act.description,
                "type": act.action_type,
                "input_schema": act.input_schema,
                "output_schema": act.output_schema
            })

        return candidates

    def _get_current_task_compiled_actions(self) -> List[str]:
        """
        Get the compiled action list from the current task.

        Returns:
            List of action names if task has compiled_actions, otherwise empty list
        """
        task = STATE.current_task
        if task and hasattr(task, 'compiled_actions') and task.compiled_actions:
            return task.compiled_actions
        return []
        
