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
from core.llm_interface import LLMCallType
from core.prompt import SELECT_ACTION_IN_TASK_PROMPT, SELECT_ACTION_PROMPT, SELECT_ACTION_IN_GUI_PROMPT, SELECT_ACTION_IN_SIMPLE_TASK_PROMPT
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

    def __init__(self, action_library: ActionLibrary, llm_interface, vlm_interface, context_engine: ContextEngine):
        """
        Initialize the router responsible for selecting or creating actions.

        Args:
            action_library: Repository for storing and retrieving action definitions.
            llm_interface: LLM client used to reason about which action to run.
            context_engine: Provider of system prompts and context formatting.
        """
        self.action_library = action_library
        self.llm_interface = llm_interface
        self.vlm_interface = vlm_interface
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
        conversation_mode_actions = ["send message", "ask question", "start task", "update todos", "end task", "ignore"]
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
        prompt = SELECT_ACTION_PROMPT.format(
            event_stream=self.context_engine.get_event_stream(),
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
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """
        When a task is running, this action selection will be used.

        1. Retrieves top-k candidate action names from ChromaDB.
        2. Builds a candidate list with searched and default action for the LLM.
        3. Asks the LLM if any candidate is valid, or if a new action is needed.
        4. If new action is needed, return an empty action name, and let the outer
           loop create the action.
        5. Otherwise, return the chosen existing action along with parameters.
        
        Args:
            query: Task-level instruction for the next step.
            action_type: Optional action type hint supplied to the LLM.
            GUI_mode: Whether the user is interacting through a GUI, affecting
                which actions are visible.
            context: Serialized task context to embed in the prompt.

        Returns:
            Dict[str, Any]: Decision payload with ``action_name`` and
            normalized ``parameters`` for execution, or an empty ``action_name``
            when a new action should be created.
        """
        action_candidates = []
        action_name_candidates = []
    
        # List of filtered default actions when creating task
        ignore_actions = ["ignore"]
    
        # Retrieve default actions (could be multiple)
        default_actions = self.action_library.retrieve_default_action()
    
        for act in default_actions:
            if act.name in ignore_actions:
                continue
            if not _is_visible_in_mode(act, GUI_mode):
                continue
            action_candidates.append({
                "name": act.name,
                "description": act.description,
                "type": act.action_type,
                "input_schema": act.input_schema,
                "output_schema": act.output_schema
            })
    
        # Additional candidate actions from search
        candidate_names = self.action_library.search_action(query, top_k=5)
        logger.info(f"ActionRouter found candidate actions: {candidate_names}")
        for name in candidate_names:
            act = self.action_library.retrieve_action(name)
            if not act:
                continue
            if act.name in ignore_actions:
                continue
            if not _is_visible_in_mode(act, GUI_mode):
                continue
            action_candidates.append({
                "name": act.name,
                "description": act.description,
                "type": act.action_type,
                "input_schema": act.input_schema,
                "output_schema": act.output_schema
            })
    
        # Dedupe names while preserving insertion order
        action_name_candidates = list({candidate["name"]: None for candidate in action_candidates}.keys())

        # Build the instruction prompt for the LLM
        # KV CACHING: Inject dynamic context into user prompt
        prompt = SELECT_ACTION_IN_TASK_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=self.context_engine.get_task_state(),
            event_stream=self.context_engine.get_event_stream(),
            query=query,
            reasoning=self._format_reasoning(reasoning),
            action_candidates=self._format_candidates(action_candidates),
            action_name_candidates=self._format_action_names(action_name_candidates),
        )

        max_retries = 3
        for attempt in range(max_retries):
            decision = await self._prompt_for_decision(prompt, is_task=True)

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
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """
        Action selection for simple task mode - streamlined without todo workflow.

        Simple tasks don't use todos and auto-end after delivering results.
        This method excludes todo-related actions and uses a simpler prompt.

        Args:
            query: Task-level instruction for the next step.
            reasoning: Reasoning context from the agent.

        Returns:
            Dict[str, Any]: Decision payload with ``action_name`` and
            normalized ``parameters`` for execution.
        """
        action_candidates = []
        action_name_candidates = []

        # Exclude todo management and ignore actions for simple tasks
        ignore_actions = ["ignore", "update todos"]

        # Retrieve default actions
        default_actions = self.action_library.retrieve_default_action()

        for act in default_actions:
            if act.name in ignore_actions:
                continue
            if not _is_visible_in_mode(act, GUI_mode=False):
                continue
            action_candidates.append({
                "name": act.name,
                "description": act.description,
                "type": act.action_type,
                "input_schema": act.input_schema,
                "output_schema": act.output_schema
            })

        # Additional candidate actions from search
        candidate_names = self.action_library.search_action(query, top_k=5)
        logger.info(f"ActionRouter (simple task) found candidate actions: {candidate_names}")
        for name in candidate_names:
            act = self.action_library.retrieve_action(name)
            if not act:
                continue
            if act.name in ignore_actions:
                continue
            if not _is_visible_in_mode(act, GUI_mode=False):
                continue
            action_candidates.append({
                "name": act.name,
                "description": act.description,
                "type": act.action_type,
                "input_schema": act.input_schema,
                "output_schema": act.output_schema
            })

        # Dedupe names while preserving insertion order
        action_name_candidates = list({candidate["name"]: None for candidate in action_candidates}.keys())

        # Build the instruction prompt using simple task prompt
        prompt = SELECT_ACTION_IN_SIMPLE_TASK_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=self.context_engine.get_task_state(),
            event_stream=self.context_engine.get_event_stream(),
            query=query,
            reasoning=self._format_reasoning(reasoning),
            action_candidates=self._format_candidates(action_candidates),
            action_name_candidates=self._format_action_names(action_name_candidates),
        )

        max_retries = 3
        for attempt in range(max_retries):
            decision = await self._prompt_for_decision(prompt, is_task=True)

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
        When a task is running, this action selection will be used.

        1. Retrieves top-k candidate action names from ChromaDB.
        2. Builds a candidate list with searched and default action for the LLM.
        3. Asks the LLM if any candidate is valid, or if a new action is needed.
        4. If new action is needed, return an empty action name, and let the outer
           loop create the action.
        5. Otherwise, return the chosen existing action along with parameters.
        
        Args:
            query: Task-level instruction for the next step.
            action_type: Optional action type hint supplied to the LLM.
            GUI_mode: Whether the user is interacting through a GUI, affecting
                which actions are visible.
            context: Serialized task context to embed in the prompt.

        Returns:
            Dict[str, Any]: Decision payload with ``action_name`` and
            normalized ``parameters`` for execution, or an empty ``action_name``
            when a new action should be created.
        """
        action_candidates = []
        action_name_candidates = []
    
        # List of filtered default actions when creating task
        ignore_actions = ["ignore"]
    
        # Additional candidate actions from search
        candidate_names = self.action_library.search_action(query, top_k=50)
        logger.info(f"ActionRouter found candidate actions: {candidate_names}")
        for name in candidate_names:
            act = self.action_library.retrieve_action(name)
            if not act:
                continue
            if act.name in ignore_actions:
                continue
            if not _is_visible_in_mode(act, GUI_mode):
                continue
            action_candidates.append({
                "name": act.name,
                "description": act.description,
                "type": act.action_type,
                "input_schema": act.input_schema,
                "output_schema": act.output_schema
            })
    
        # Dedupe names while preserving insertion order
        action_name_candidates = list({candidate["name"]: None for candidate in action_candidates}.keys())

        # Build the instruction prompt for the LLM
        # KV CACHING: Inject dynamic context into user prompt (GUI mode uses gui_event_stream)
        prompt = SELECT_ACTION_IN_GUI_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=self.context_engine.get_task_state(),
            gui_event_stream=self.context_engine.get_gui_event_stream(),
            query=query,
            reasoning=self._format_reasoning(reasoning),
            action_candidates=self._format_candidates(action_candidates),
            action_name_candidates=self._format_action_names(action_name_candidates),
        )

        max_retries = 3
        for attempt in range(max_retries):
            decision = await self._prompt_for_decision_gui(prompt=prompt, is_task=True)

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

    async def _prompt_for_decision(self, prompt: str, is_task: bool = False) -> Dict[str, Any]:
        max_retries = 3
        last_error: Optional[Exception] = None
        current_prompt = prompt

        # Get current task_id for session cache (if running in a task)
        current_task_id = STATE.get_agent_property("current_task_id", "") if is_task else ""

        for attempt in range(max_retries):
            # KV CACHING: System prompt is now STATIC only
            # Dynamic content (event_stream, task_state) is already in the user prompt
            system_prompt, _ = self.context_engine.make_prompt(
                user_flags={"query": False, "expected_output": False},
                system_flags={"agent_info": not is_task, "policy": False},
            )

            # Use session cache if we're in a task context and session exists
            if current_task_id and self.llm_interface.has_session_cache(current_task_id, LLMCallType.ACTION_SELECTION):
                raw_response = await self.llm_interface.generate_response_with_session_async(
                    task_id=current_task_id,
                    call_type=LLMCallType.ACTION_SELECTION,
                    user_prompt=current_prompt,
                    system_prompt_for_new_session=system_prompt,
                )
            else:
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
        
    async def _prompt_for_decision_gui(self, prompt: str = "", image_bytes: Optional[bytes] = None, is_task: bool = False) -> Dict[str, Any]:
        max_retries = 3
        last_error: Optional[Exception] = None
        current_prompt = prompt

        # Get current task_id for session cache (if running in a task)
        current_task_id = STATE.get_agent_property("current_task_id", "") if is_task else ""

        for attempt in range(max_retries):
            # KV CACHING: System prompt is now STATIC only
            # Dynamic content (gui_event_stream, task_state) is already in the user prompt
            system_prompt, _ = self.context_engine.make_prompt(
                user_flags={"query": False, "expected_output": False},
                system_flags={"role_info": not is_task, "agent_info": not is_task, "policy": False},
            )
            if image_bytes:
                # VLM calls don't use session cache (independent calls with images)
                raw_response = await self.vlm_interface.generate_response_async(
                    image_bytes,
                    system_prompt=system_prompt,
                    user_prompt=current_prompt,
                )
            else:
                # Use session cache if we're in a task context and session exists
                if current_task_id and self.llm_interface.has_session_cache(current_task_id, LLMCallType.GUI_ACTION_SELECTION):
                    raw_response = await self.llm_interface.generate_response_with_session_async(
                        task_id=current_task_id,
                        call_type=LLMCallType.GUI_ACTION_SELECTION,
                        user_prompt=current_prompt,
                        system_prompt_for_new_session=system_prompt,
                    )
                else:
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

    def _format_reasoning(self, context: str | list | dict | None) -> str:
        if context is None:
            return ""
        if isinstance(context, (list, dict)):
            return json.dumps(context, indent=2, ensure_ascii=False)
        return str(context)

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
        
