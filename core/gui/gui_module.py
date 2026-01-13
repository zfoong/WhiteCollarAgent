import json
from typing import Dict, Optional, List
from core.action.action import Action
from core.state.agent_state import STATE
from core.state.types import ReasoningResult
from core.task.task import Step
from core.gui.handler import GUIHandler
from core.prompt import GUI_REASONING_PROMPT, GUI_QUERY_FOCUSED_PROMPT, GUI_PIXEL_POSITION_PROMPT, GUI_ACTION_PARAMETERS_VALIDATION_PROMPT
from core.vlm_interface import VLMInterface
from core.action.action_manager import ActionManager
from core.action.action_library import ActionLibrary
from core.action.action_router import ActionRouter
from core.context_engine import ContextEngine
from core.event_stream.event_stream_manager import EventStreamManager
from core.llm_interface import LLMInterface
from core.logger import logger

class GUIModule:
    def __init__(
        self, 
        provider: str = "byteplus", 
        action_library: ActionLibrary = None,
        action_router: ActionRouter = None,
        context_engine: ContextEngine = None,
        action_manager: ActionManager = None,
    ):
        self.llm: LLMInterface = LLMInterface(provider=provider)
        self.vlm: VLMInterface = VLMInterface(provider="gemini")
        self.action_library: ActionLibrary = action_library
        self.action_router: ActionRouter = action_router
        self.context_engine: ContextEngine = context_engine
        self.action_manager: ActionManager = action_manager
        self.gui_event_stream_manager: EventStreamManager = EventStreamManager(self.llm)
        self.previous_reason: str = ""

    def switch_to_gui_mode(self) -> None:
        STATE.update_gui_mode(True)

    def switch_to_cli_mode(self) -> None:
        STATE.update_gui_mode(False)

    def set_gui_event_stream(self, event: str) -> None:
        self.gui_event_stream_manager.log(
            "agent GUI event",
            event,
            severity="DEBUG",
            display_message=None,
        )

    def get_gui_event_stream(self) -> str:
        return self.gui_event_stream_manager.get_stream().to_prompt_snapshot(include_summary=True)

    async def perform_gui_task_step(self, step: Step, session_id: str, next_action_description: str, parent_action_id: str) -> dict:
        """
        Perform a GUI task step. Keeps calling the action until the next action is not None. When the next action is not None, it returns the response.
        If next action is None, it means the task is complete, and it returns the response.

        Args:
            step: The step to perform.
            session_id: The session ID.
            next_action_description: The next action description.
            parent_action_id: The parent action ID.
        """
        logger.info(f"[PERFORM GUI TASK STEP] {step} {session_id} {next_action_description} {parent_action_id}")
        try:
            self.switch_to_gui_mode()
            STATE.set_agent_property(
                "current_task_id", session_id)

            response: dict = {
                "status": "ok",
                "message": "Action completed successfully",
                "action_output": None,
            }

            while STATE.gui_mode:
                response: dict = await self._perform_gui_task_step_action(step, session_id, next_action_description, parent_action_id)
                logger.info(f"[GUI TASK STEP ACTION RESPONSE] {response}")
            
            event_stream_summary: str | None = self.gui_event_stream_manager.get_stream().head_summary
            response["event_stream_summary"] = event_stream_summary

            return response

        except Exception as e:
            logger.error(f"[GUI TASK ERROR] {e}", exc_info=True)
            raise

    # ===================================
    # Private Methods
    # ===================================

    async def _perform_gui_task_step_action(self, step: Step, session_id: str, next_action_description: str, parent_action_id: str) -> dict:
        """
        Perform a GUI task step action.

        Args:
            step: The step to perform.
            session_id: The session ID.
            next_action_description: The next action description.
            parent_action_id: The parent action ID.
        """
        try:
            query: str = next_action_description
            reasoning: str = ""
            parent_id = parent_action_id

            # ===================================
            # 1. Start Session
            # ===================================
            # await self.state_manager.start_session(True)
            # Assume session is already started from react

            # ===================================
            # 2. Check Limits
            # ===================================
            if not await self._check_agent_limits():
                return {
                    "status": "error",
                    "message": "Agent limits reached"
                }

            # ===================================
            # 3. Select Action
            # ===================================

            # 1. Take screenshot
            png_bytes = GUIHandler.get_screen_state(GUIHandler.TARGET_CONTAINER)
            if png_bytes is None:
                return {
                    "status": "error",
                    "message": "Failed to take screenshot"
                }
            
            # 1.5. Understand the image
            image_description: str = await self._get_image_description(png_bytes, query=self.previous_reason)
            
            # 2. Perform reasoning
            reasoning_result: ReasoningResult = await self._perform_reasoning_GUI(query=image_description)
            reasoning: str = reasoning_result.reasoning
            action_query: str = reasoning_result.action_query

            self.previous_reason = reasoning

            # 2.5. Get pixel position of the element
            pixel_position: List[Dict] = await self._get_pixel_position(png_bytes, action_query)

            # 3. Select action
            action_search_query: str = action_query + " " + json.dumps(pixel_position)
            action_decision = await self.action_router.select_action_in_GUI(query=action_search_query, reasoning=reasoning, GUI_mode=True)

            if not action_decision:
                raise ValueError("Action router returned no decision.")

            # ===================================
            # 4. Get Action
            # ===================================
            action_name = action_decision.get("action_name")
            action_params = action_decision.get("parameters", {})

            if not action_name:
                raise ValueError("No valid action selected by the router.")

            #  4.1 Validate action parameters
            if not await self._validate_action_parameters(action_decision, png_bytes, action_query):
                return {
                    "status": "error",
                    "message": "Invalid action parameters"
                }

            # Retrieve action
            action: Optional[Action] = self.action_library.retrieve_action(action_name)
            if action is None:
                raise ValueError(
                    f"Action '{action_name}' not found in the library. "
                    "Check DB connectivity or ensure the action is registered."
                )
            
            # Determine parent action
            if not parent_id:
                parent_id = step.action_id

            # ===================================
            # 5. Execute Action
            # ===================================
            action_output = await self.action_manager.execute_action(
                action=action,
                context=action_query if action_query else query,
                event_stream=self.get_gui_event_stream(),
                parent_id=parent_id,
                session_id=session_id,
                is_running_task=True,
                is_gui_task=True,
                input_data=action_params,
            )

            return {
                "status": "ok",
                "message": "Action completed successfully",
                "action_output": action_output
            }

        except Exception as e:
            logger.error(f"[GUI TASK STEP ERROR] {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
            }

    async def _perform_reasoning_GUI(self, query: str, retries: int = 2, log_reasoning_event = False) -> ReasoningResult:
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
            system_flags={"policy": False, "gui_event_stream": True, "event_stream": False},
        )
        # Format the user prompt with the incoming query
        prompt = GUI_REASONING_PROMPT.format(gui_state=query)

        # Attempt the LLM call and parsing up to (retries + 1) times
        for attempt in range(retries + 1):            
            response = await self.llm.generate_response_async(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )

            try:
                # Parse and validate the structured JSON response
                reasoning_result: ReasoningResult = self._parse_reasoning_response(response)

                if self.gui_event_stream_manager and log_reasoning_event:
                    self.set_gui_event_stream(reasoning_result.reasoning)

                return reasoning_result
            except ValueError as e:                
                raise RuntimeError("Failed to obtain valid reasoning from VLM") from e

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

    async def _check_agent_limits(self) -> bool:
        agent_properties = STATE.get_agent_properties()
        action_count: int = agent_properties.get("action_count", 0)
        max_actions: int = agent_properties.get("max_actions_per_task", 0)
        token_count: int = agent_properties.get("token_count", 0)
        max_tokens: int = agent_properties.get("max_tokens_per_task", 0)

        # Check action limits
        if (action_count / max_actions) >= 1.0:
            return False

        # Check token limits
        if (token_count / max_tokens) >= 1.0:
            return False
        
        # No limits close or reached
        return True

    async def _get_image_description(self, image_bytes: bytes, query: str) -> str:
        """
        Get the description of the image.
        """
        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
            system_flags={
                "policy": False, 
                "gui_event_stream": False, 
                "event_stream": False, 
                "task_state": False, 
                "conversation_history": False, 
                "agent_info": False, 
                "role_info": False, 
                "agent_state": False, 
                "base_instruction": False,
                "environment": False,
            }
        )

        user_prompt = GUI_QUERY_FOCUSED_PROMPT.format(query=query)

        image_description: str = await self.vlm.generate_response_async(
            image_bytes=image_bytes,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            debug=True,
        )

        return image_description

    async def _get_pixel_position(self, image_bytes: bytes, element_to_find: str) -> List[Dict]:
        """
        Get the pixel position of the element in the image.
        """
        prompt = GUI_PIXEL_POSITION_PROMPT.format(element_to_find=element_to_find)
        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
            system_flags={
                "policy": False, 
                "gui_event_stream": False, 
                "event_stream": False, 
                "task_state": False, 
                "conversation_history": False, 
                "agent_info": False, 
                "role_info": False, 
                "agent_state": False, 
                "base_instruction": False, 
                "environment": False,
            }
        )
        response = await self.vlm.generate_response_async(image_bytes, system_prompt=system_prompt, user_prompt=prompt)
        try:
            parsed: List[Dict] = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {response}") from e
        return parsed

    async def _validate_action_parameters(self, action_decision: Dict, image_bytes: bytes, query: str) -> bool:
        """
        Validate the action parameters.

        Args:
            action_decision: The action decision.
            image_bytes: The image bytes.
            query: The query.

        Returns:
            True if the action parameters are valid, False otherwise.
        """

        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
            system_flags={
                "policy": False, 
                "gui_event_stream": False, 
                "event_stream": False, 
                "task_state": False, 
                "conversation_history": False, 
                "agent_info": False, 
                "role_info": False, 
                "agent_state": False, 
                "base_instruction": False, 
                "environment": False,
            }
        )
        user_prompt = GUI_ACTION_PARAMETERS_VALIDATION_PROMPT.format(action_decision=json.dumps(action_decision), query=query)
        response = await self.vlm.generate_response_async(
            image_bytes=image_bytes, 
            system_prompt=system_prompt, 
            user_prompt=user_prompt,
        )
        parsed: Dict = json.loads(response) or {}
        valid: bool = parsed.get("valid") or False
        if not isinstance(valid, bool):
            raise ValueError(f"LLM returned invalid JSON: {response}. Expected JSON object with 'valid' field. Actual type: {type(valid)}")
        return valid