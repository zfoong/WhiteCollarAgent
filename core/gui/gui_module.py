import json
import ast
import tempfile
import os
from gradio_client import Client, file
from typing import Dict, Optional, List, Tuple
from core.action.action import Action
from core.state.agent_state import STATE
from core.state.types import ReasoningResult
from core.todo.todo import TodoItem
from core.gui.handler import GUIHandler
from core.prompt import GUI_REASONING_PROMPT, GUI_QUERY_FOCUSED_PROMPT, GUI_PIXEL_POSITION_PROMPT, GUI_REASONING_PROMPT_OMNIPARSER
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

        # ==================================
        #  CONFIG
        # ==================================
        omniparser_base_url: str = os.getenv("OMNIPARSER_BASE_URL", "http://127.0.0.1:7861")
        
        self.can_use_omniparser: bool = (os.getenv("USE_OMNIPARSER", "False") == "True") and (omniparser_base_url is not None)
        logger.info(f"[can_use_omniparser]: {self.can_use_omniparser}")
        
        if self.can_use_omniparser:
            self.gradio_client: Client | None = Client(omniparser_base_url)
        else:
            self.gradio_client: Client | None = None

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

    async def perform_gui_task_step(self, step: Optional[TodoItem], session_id: str, next_action_description: str, parent_action_id: str) -> dict:
        """
        Perform a GUI task step. Keeps calling the action until the next action is not None. When the next action is not None, it returns the response.
        If next action is None, it means the task is complete, and it returns the response.

        Args:
            step: The current todo item (optional).
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

    async def _perform_gui_task_step_action(self, step: Optional[TodoItem], session_id: str, next_action_description: str, parent_action_id: str) -> dict:
        """
        Perform a GUI task step action.

        Args:
            step: The current todo item (optional).
            session_id: The session ID.
            next_action_description: The next action description.
            parent_action_id: The parent action ID.
        """
        try:
            query: str = next_action_description
            reasoning: str = ""
            parent_id = parent_action_id

            # ===================================
            # 1. Check Limits
            # ===================================
            if not await self._check_agent_limits():
                self.switch_to_cli_mode()
                return {
                    "status": "error",
                    "message": "Agent limits reached"
                }

            # ===================================
            # 2. Take Screenshot
            # ===================================
            png_bytes = GUIHandler.get_screen_state(GUIHandler.TARGET_CONTAINER)
            if png_bytes is None:
                return {
                    "status": "error",
                    "message": "Failed to take screenshot"
                }
            
            # ===================================
            # 3. Perform Reasoning
            # ===================================
            if self.can_use_omniparser:
                reasoning_result, action_search_query = await self.omniparser_flow(query=query, png_bytes=png_bytes)
            else:
                reasoning_result, action_search_query = await self.vlm_flow(query=query, png_bytes=png_bytes)

            reasoning: str = reasoning_result.reasoning

            # ===================================
            # 4. Select Action
            # ===================================
            action_decision = await self.action_router.select_action_in_GUI(query=action_search_query, reasoning=reasoning, GUI_mode=True)

            if not action_decision:
                raise ValueError("Action router returned no decision.")

            action_name = action_decision.get("action_name")
            action_params = action_decision.get("parameters", {})

            if not action_name:
                raise ValueError("No valid action selected by the router.")

            # Retrieve action
            action: Optional[Action] = self.action_library.retrieve_action(action_name)
            if action is None:
                raise ValueError(
                    f"Action '{action_name}' not found in the library. "
                    "Check DB connectivity or ensure the action is registered."
                )
            
            # Use provided parent action ID (step.action_id no longer exists)

            # ===================================
            # 5. Execute Action
            # ===================================
            action_output = await self.action_manager.execute_action(
                action=action,
                context=reasoning_result.action_query if reasoning_result.action_query else query,
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

    async def vlm_flow(self, query: str, png_bytes: bytes) -> Tuple[ReasoningResult, str]:
        """
        Perform the VLM flow.
        """
        # ==================================
        # 1. Get Image Description
        # ==================================
        image_description: str = await self._get_image_description_vlm(png_bytes=png_bytes, query=query)

        # ==================================
        # 2. Perform Reasoning
        # ==================================
        reasoning_result: ReasoningResult = await self._perform_reasoning_GUI_vlm(query=image_description)
        action_query: str = reasoning_result.action_query

        # ==================================
        # 3. Get Pixel Position
        # ==================================
        pixel_position: List[int] = await self._get_pixel_position_vlm(image_bytes=png_bytes, element_to_find=action_query)

        # ==================================
        # 4. Construct Action Search Query
        # ==================================
        action_search_query: str = action_query + " " + json.dumps(pixel_position)

        return reasoning_result, action_search_query

    async def omniparser_flow(self, query: str, png_bytes: bytes) -> Tuple[ReasoningResult, str]:
        """
        Perform the omniparser flow.
        """
        # ==================================
        # 1. OmniParser Image Analysis
        # ==================================
        image_description, annotated_image_bytes = await self._get_image_description_omniparser(png_bytes)

        # ==================================
        # 2. Reasoning
        # ==================================
        reasoning_result, item_index = await self._perform_reasoning_GUI_omniparser(png_bytes=annotated_image_bytes)
        action_query: str = reasoning_result.action_query

        # ==================================
        # 3. Get Pixel Position
        # ==================================
        if len(image_description) > item_index:
            item = image_description[item_index]
            bbox: List[float] = self.extract_bbox_from_line(item)
            pixel_position: List[int] = self.convert_bbox_to_pixels(bbox, 1064, 1064)
        else:
            pixel_position = "No UI element needed for action"

        # ==================================
        # 4. Construct Action Search Query
        # ==================================
        action_search_query: str = action_query + " " + json.dumps(pixel_position)

        return reasoning_result, action_search_query

    # ==================================
    # VLM Helper Methods
    # ==================================

    async def _get_image_description_vlm(self, png_bytes: bytes, query: str) -> str:
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
                "agent_info": False,
                "role_info": False,
                "agent_state": False,
                "base_instruction": False,
                "environment": False,
            }
        )

        user_prompt = GUI_QUERY_FOCUSED_PROMPT.format(query=query)

        image_description: str = await self.vlm.generate_response_async(
            image_bytes=png_bytes,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            debug=True,
        )

        return image_description

    async def _perform_reasoning_GUI_vlm(self, query: str, retries: int = 2, log_reasoning_event = False) -> ReasoningResult:
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
        # KV CACHING: System prompt is now STATIC only
        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
            system_flags={"policy": False},
        )
        # KV CACHING: Inject dynamic context into user prompt
        prompt = GUI_REASONING_PROMPT.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=self.context_engine.get_task_state(),
            gui_event_stream=self.context_engine.get_gui_event_stream(),
            gui_state=query,
        )

        # Attempt the LLM call and parsing up to (retries + 1) times
        for attempt in range(retries + 1):            
            response = await self.llm.generate_response_async(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )

            try:
                # Parse and validate the structured JSON response
                reasoning_result, _ = self._parse_reasoning_response(response)

                if self.gui_event_stream_manager and log_reasoning_event:
                    self.set_gui_event_stream(reasoning_result.reasoning)

                return reasoning_result
            except ValueError as e:                
                raise RuntimeError("Failed to obtain valid reasoning from VLM") from e

    async def _get_pixel_position_vlm(self, image_bytes: bytes, element_to_find: str) -> List[Dict]:
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

    # ==================================
    # OmniParser Helper Methods
    # ==================================

    async def _get_image_description_omniparser(self, image_bytes: bytes) -> Tuple[List[str], bytes]:
        """
        Get the description of the image using OmniParser via Gradio Client.
        """
        print("Sending request to OmniParser (Gradio 4.x)...")

        # --- 1. Prepare Input Data ---
        input_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        try:
            # Write the raw bytes to the temp file
            input_tmp.write(image_bytes)
            input_tmp.close() # Close file so client can read it

            # --- 2. Make the Prediction Call  ---
            result = self.gradio_client.predict(
                file(input_tmp.name),
                0.05,              # Input 1: box_threshold
                0.1,               # Input 2: iou_threshold
                False,             # Input 3: use_paddleocr
                640,               # Input 4: imgsz
                api_name="/process"
            )
            # 'result' is a list: [path_to_downloaded_output_image, parsed_text_string]

        except Exception as e:
            raise ValueError(f"Gradio API call failed: {e}") from e
        finally:
            # Clean up the input temp file regardless of success/failure
            if os.path.exists(input_tmp.name):
                # We put this in a try block just in case another process locked it
                try: os.remove(input_tmp.name)
                except Exception: pass

        # --- 3. Parse Response ---
        try:
            # A) Extract Text Content (Index 1)
            raw_text_block = str(result[1]).strip()
            parsed_text_list = [line for line in raw_text_block.splitlines() if line.strip()]

            # B) Extract Annotated Image Bytes (Index 0)
            # Gradio client saves the output image to a temporary file path on disk.
            output_temp_path = result[0]

            if not os.path.exists(output_temp_path):
                 raise ValueError(f"Result image file not found at: {output_temp_path}")

            # Read bytes off disk
            with open(output_temp_path, "rb") as f:
                annotated_image_bytes = f.read()

            # Clean up output temp file
            try: os.remove(output_temp_path)
            except Exception: pass

            return parsed_text_list, annotated_image_bytes

        except (IndexError, TypeError, IOError, OSError) as e:
             raise ValueError(f"Failed to parse Gradio client response format: {e}") from e

    async def _perform_reasoning_GUI_omniparser(self, png_bytes: bytes, retries: int = 2, log_reasoning_event = False) -> Tuple[ReasoningResult, int]:
        """
        Perform reasoning on a image to guide action selection.

        Input:
            - png_bytes: The PNG bytes of the image.
            - retries: The number of retry attempts if the reasoning fails.
            - log_reasoning_event: Whether to log the reasoning event.

        Output:
            - reasoning_result: The reasoning result.
            - item_index: The index of the item in the image.
        """
        # KV CACHING: System prompt is now STATIC only
        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
            system_flags={"policy": False},
        )
        # KV CACHING: Inject dynamic context into user prompt
        prompt = GUI_REASONING_PROMPT_OMNIPARSER.format(
            agent_state=self.context_engine.get_agent_state(),
            task_state=self.context_engine.get_task_state(),
            gui_event_stream=self.context_engine.get_gui_event_stream(),
        )

        # Attempt the LLM call and parsing up to (retries + 1) times
        for attempt in range(retries + 1):            
            response = await self.vlm.generate_response_async(
                image_bytes=png_bytes,
                system_prompt=system_prompt,
                user_prompt=prompt,
            )

            try:
                # Parse and validate the structured JSON response
                reasoning_result, item_index = self._parse_reasoning_response(response)

                if self.gui_event_stream_manager and log_reasoning_event:
                    self.set_gui_event_stream(reasoning_result.reasoning)

                return reasoning_result, item_index
            except ValueError as e:                
                raise RuntimeError("Failed to obtain valid reasoning from VLM") from e

    def extract_bbox_from_line(self, data_line: str) -> Optional[List[float]]:
        """
        Parses a single OmniParser data string and extracts the bounding box.

        Args:
            data_line: A single string, e.g., "icon 0: {'type': ... 'bbox': [...] ...}"

        Returns:
            A list of 4 floats representing [ymin, xmin, ymax, xmax],
            or None if parsing fails.
        """
        try:
            # 1. Isolate the dictionary part of the string.
            # The line always starts with "icon N: {...", so we split at the first ": "
            parts = data_line.split(': ', 1)

            if len(parts) < 2:
                print(f"Error: Line format incorrect. Could not find separator ': '")
                return None

            # parts[0] is like "icon 0"
            # parts[1] is like "{'type': 'text', 'bbox': [...] ...}"
            dict_string_representation = parts[1].strip()

            # 2. Convert the string representation into a real Python dictionary.
            # ast.literal_eval safely evaluates strings containing Python literals.
            real_dictionary = ast.literal_eval(dict_string_representation)

            # 3. Extract the 'bbox' key.
            # We use .get() to avoid crashing if 'bbox' is somehow missing.
            bbox = real_dictionary.get('bbox')

            # Basic validation to ensure it looks like a bbox (list of 4 items)
            if isinstance(bbox, list) and len(bbox) == 4:
                return bbox
            else:
                print(f"Error: 'bbox' found but format is invalid: {bbox}")
                return None

        except (ValueError, SyntaxError, ast.ASTError) as e:
            print(f"Error parsing dictionary contents in line: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

    def convert_bbox_to_pixels(
        self,
        relative_bbox: List[float],
        img_width: int,
        img_height: int
    ) -> List[int]:
        """
        Converts normalized [ymin, xmin, ymax, xmax] to [ymin_px, xmin_px, ymax_px, xmax_px].

        Args:
            relative_bbox: List of 4 floats between 0.0 and 1.0 [ymin, xmin, ymax, xmax].
            img_width: The total width of the original image in pixels.
            img_height: The total height of the original image in pixels.

        Returns:
            List of 4 integers representing pixel coordinates.
        """
        # Unpack normalized coordinates
        ymin_rel, xmin_rel, ymax_rel, xmax_rel = relative_bbox

        # Calculate pixel coordinates.
        # We use int() to truncate decimals, which is standard for pixel grid coordinates.
        # Sometimes round() is used depending on precision needs, but int() is safer to stay within bounds.
        xmin_px = int(xmin_rel * img_width)
        xmax_px = int(xmax_rel * img_width)

        ymin_px = int(ymin_rel * img_height)
        ymax_px = int(ymax_rel * img_height)

        # Ensure coordinates don't go below zero just in case of weird float math
        xmin_px = max(0, xmin_px)
        ymin_px = max(0, ymin_px)

        # Return in the same order [ymin, xmin, ymax, xmax]
        return [ymin_px, xmin_px, ymax_px, xmax_px]

    # ==================================
    # Global Helper Methods
    # ==================================

    def _parse_reasoning_response(self, response: str) -> Tuple[ReasoningResult, int]:
        """
        Parse and validate the structured JSON response from the reasoning VLM call.
        """
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"VLM returned invalid JSON: {response}") from e

        if not isinstance(parsed, dict):
            raise ValueError(f"VLM response is not a JSON object: {parsed}")

        reasoning = parsed.get("reasoning")
        action_query = parsed.get("action_query")
        item_index = parsed.get("item_index", 0)

        if not isinstance(reasoning, str) or not isinstance(action_query, str):
            raise ValueError(f"Invalid reasoning schema: {parsed}")
        if not isinstance(item_index, int):
            raise ValueError(f"Invalid item index: {item_index}")

        reasoning_result = ReasoningResult(
            reasoning=reasoning,
            action_query=action_query,
        )
        return reasoning_result, int(item_index)

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
