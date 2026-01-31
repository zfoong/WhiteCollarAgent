# -*- coding: utf-8 -*-
"""
Created on Thu Mar 27 21:27:43 2025

@author: zfoong
"""

from datetime import datetime
import platform
import time
import json
import asyncio
import nest_asyncio
from typing import Optional, List, Dict, Any
from core.action.action_library import ActionLibrary
from core.action.action import Action
from core.action.action_executor import ActionExecutor
import io
import sys
import re

import uuid
from core.database_interface import DatabaseInterface
from core.logger import logger
from core.event_stream.event_stream_manager import EventStreamManager
from core.context_engine import ContextEngine
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from core.gui.handler import GUIHandler

nest_asyncio.apply()

# ------------------------------
# ActionManager
# ------------------------------


class ActionManager:
    """
    Executes actions, handling both atomic and hierarchical tasks.
    Persists every run into *action_history* (one document per run).
    The same document is *upserted* as the run transitions through
    "running" → "success"/"error" so that no duplicates are created.
    """
    def __init__(self,
                 action_library: ActionLibrary,
                 llm_interface,
                 db_interface: DatabaseInterface,
                 event_stream_manager: EventStreamManager,
                 context_engine: ContextEngine,
                 state_manager: StateManager):
        """
        Build an :class:`ActionManager` that can execute and track actions.

        Args:
            action_library: Source of action definitions and metadata.
            llm_interface: LLM client used for input resolution and routing
                follow-up decisions.
            db_interface: Persistence layer for action history records.
            event_stream_manager: Publisher used to log execution events for
                live task updates.
            context_engine: Provider for system prompts when prompting the LLM.
            state_manager: State controller for task progress updates.
        """
        self.action_library = action_library
        self.llm_interface = llm_interface
        self.db_interface = db_interface
        self.event_stream_manager = event_stream_manager
        self.context_engine = context_engine
        # Track in-flight actions so we can mark them aborted on shutdown
        self._inflight: dict[str, dict] = {}
        self.state_manager = state_manager
        self.executor = ActionExecutor()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def execute_action(
        self,
        action: Action,
        context: str,
        event_stream: str,
        parent_id: str | None = None,
        session_id: str | None = None,
        is_running_task: bool | None = False,
        is_gui_task: bool = False,
        *,
        input_data: Optional[dict] = None,
    ) -> dict: 
        """
        Execute an action and persist the full run lifecycle.

        The method normalizes platform-specific code, resolves inputs (via LLM
        when necessary), executes either atomic or divisible actions, performs
        optional observation checks, records status transitions, and logs
        progress to the event stream.

        Args:
            action: Action definition to run.
            context: Textual context for the current conversation or task.
            event_stream: Serialized event stream for the prompt passed to the LLM.
            parent_id: Optional run identifier when executing as a sub-action.
            session_id: Session identifier used for logging and persistence.
            is_running_task: Flag indicating whether the execution is part of an
                active task workflow (controls logging behavior).
            input_data: Pre-resolved action inputs. If omitted, inputs are
                gathered by prompting the LLM.

        Returns:
            dict: Final output payload of the action execution, including
            observation results when available.
        """
        # ───────────────────────────────────────────────────────────────────
        # 1. Resolve inputs via LLM
        # ───────────────────────────────────────────────────────────────────

        current_platform = platform.system().lower() # e.g. 'windows', 'linux', 'darwin'
        platform_code = (
            action.platform_overrides.get(current_platform, {}).get("code", action.code)
        )
        action.code = platform_code

        if not isinstance(input_data, dict):
            logger.error(f"Provided action input is not a dict. action={action.name}")

        logger.debug(f"[INPUT DATA] {input_data}")
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()

        # persist RUNNING
        self._log_action_history(
            run_id=run_id,
            action=action,
            inputs=input_data,
            outputs=None,
            status="running",
            started_at=started_at,
            ended_at=None,
            parent_id=parent_id,
            session_id=session_id,
        )
        
        logger.debug(f"Executing action {action.name} (run_id={run_id})...")

        # remember this run is in-flight
        self._inflight[run_id] = {
            "action": action,
            "inputs": input_data,
            "parent_id": parent_id,
            "session_id": session_id,
            "started_at": started_at,
        }

        logger.info(f"Action {action.name} marked as in-flight.")
        
        if is_running_task:
            self._log_event_stream(
                is_gui_task=is_gui_task,
                event_type="action_start",
                event=f"Running action {action.name} with input: {input_data}.",
                display_message=f"Running {action.name}",
                action_name=action.name,
            )
            
        logger.debug(f"Starting execution of action {action.name}...")

        try:
            # ────────────────────────────────────────────────────────────
            # 2. Execute
            # ────────────────────────────────────────────────────────────
                    
            status = ""

            logger.debug(f"Action type: {action.action_type}")
            
            if action.action_type == "atomic":
                try:
                    outputs = await self.execute_atomic_action(action, input_data)
                except Exception as e:
                    logger.error(f"[ERROR] Failed to execute atomic action {action.name}: {e}", exc_info=True)
                    raise e

                logger.debug(f"[OUTPUT DATA] Completed execute_atomic_action: {outputs}")

                # ────────────── Observation step ──────────────
                if action.observer:
                    obs_result = await self.run_observe_step(action, outputs)
                    if not obs_result["success"]:
                        status = "error"
                        outputs["observation"] = {
                            "success": False,
                            "message": obs_result.get("message")
                        }
                    else:
                        outputs["observation"] = {
                            "success": True,
                            "message": obs_result.get("message")
                        }
    
            else:
                logger.debug(f"Executing divisible action: {action.name}")
                try:
                    outputs = await self.execute_divisible_action(
                        action, input_data, run_id
                    )
                except Exception as e:
                    logger.error(f"[ERROR] Failed to execute divisible action {action.name}: {e}", exc_info=True)
                    raise e

            logger.debug(f"[OUTPUT DATA] Final outputs for action {action.name}: {outputs}")

            if status != "error":  # Only mark as success if no errors raised and observation passed
                status = "success"

        except asyncio.CancelledError:
            status = "error"
            outputs = {"error": "Action cancelled", "error_code": "cancelled"}
        except Exception as e:
            status = "error"
            outputs = {"error": str(e)}
            logger.exception(f"[ERROR] Exception while executing action {action.name}")
        finally:
            # ensure we always clear in-flight on any exit path
            # (final persistence happens below so we do not return early)
            pass

        ended_at = datetime.utcnow().isoformat()

        # ────────────────────────────────────────────────────────────────
        # 3. Persist final state (success or error)
        # ────────────────────────────────────────────────────────────────

        logger.debug(f"Action {action.name} completed with status: {status}.")
        
        if is_running_task:
            display_status = "failed" if status == "error" else "completed"
            self._log_event_stream(
                is_gui_task=is_gui_task,
                event_type="action_end",
                event=f"Action {action.name} completed with output: {outputs}.",
                display_message=f"{action.name} → {display_status}",
                action_name=action.name,
            )

            # Emit waiting_for_user event if action requested to wait for user reply
            if outputs and outputs.get("wait_for_user_reply", False):
                self._log_event_stream(
                    is_gui_task=is_gui_task,
                    event_type="waiting_for_user",
                    event="Agent is waiting for user response.",
                    display_message=None,  # No display message - handled by TUI status bar only
                    action_name=action.name,
                )

            # current_step: Optional[Step] = self.state_manager.get_current_step()
            # if current_step:
            #     self._log_event_stream(
            #         is_gui_task=is_gui_task,
            #         event_type="task",
            #         event=f"Running task step: '{current_step.step_name}' – {current_step.description} {context if context else ''}",
            #         display_message=f"Running task step: '{current_step.step_name}' – {current_step.description}",
            #         action_name=action.name,
            #     )
            #     logger.debug(f"[ActionManager] Step {current_step.step_name} queued ({session_id})")
                
        else:
            logger.warning(f"Action {action.name} completed with status: {status}. But no event stream manager to log to.")
        
        logger.debug(f"Persisting final state for action {action.name}...")
        STATE.set_agent_property("action_count", STATE.get_agent_property("action_count") + 1)

        self._log_action_history(
            run_id=run_id,
            action=action,
            inputs=input_data,
            outputs=outputs,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            parent_id=parent_id,
            session_id=session_id,
        )
        logger.debug(f"Final state for action {action.name} persisted.")
        # remove from in-flight after final persistence
        self._inflight.pop(run_id, None)

        logger.debug(f"Action {action.name} removed from in-flight tracking.")

        return outputs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_action_history(
        self,
        *,
        run_id: str,
        action: Action,
        inputs: dict | None,
        outputs: dict | None,
        status: str,
        started_at: str | None,
        ended_at: str | None,
        parent_id: str | None,
        session_id: str | None,
    ) -> None:
        """Upsert a single history document keyed by *runId*."""
        self.db_interface.upsert_action_history(
            run_id,
            session_id = session_id,
            parent_id=parent_id,
            name=action.name,
            action_type=action.action_type,
            status=status,
            inputs=inputs,
            outputs=outputs,
            started_at=started_at,
            ended_at=ended_at,
        )

    def _log_event_stream(self, is_gui_task: bool, event_type: str, event: str, display_message: str, action_name: str) -> None:
        if is_gui_task:
            GUIHandler.gui_module.set_gui_event_stream(event)
        else:
            if self.event_stream_manager:
                self.event_stream_manager.log(
                    event_type,
                    event,
                    display_message=display_message, action_name=action_name,
                )
            else:
                logger.warning(f"No event stream manager to log to for event type: {event_type}")
    # ------------------------------------------------------------------
    # Action execution primitives (unchanged)
    # ------------------------------------------------------------------

    async def execute_atomic_action(self, action: Action, input_data: dict):
        try:
            output = await self.executor.execute_action(action, input_data)

            logger.debug(f"The action output is:\n{output}")

            # If there was an error, return it directly
            if "error" in output:
                logger.error(f"Action execution error: {output['error']}")
                return output  # DO NOT parse

            # Sandboxed actions return {stdout, stderr, returncode}.
            # Try to parse the JSON result from stdout, and surface
            # non-zero return codes as errors so the agent can react.
            if "returncode" in output:
                rc = output.get("returncode", 0)
                stdout_raw = output.get("stdout", "")
                stderr_raw = output.get("stderr", "")

                if rc != 0:
                    logger.error(f"Sandboxed action returned non-zero exit code {rc}: {stderr_raw}")
                    return {
                        "error": stderr_raw or f"Action exited with code {rc}",
                        "stdout": stdout_raw,
                        "stderr": stderr_raw,
                        "returncode": rc,
                    }

                # Try to extract the JSON result printed by the action
                # wrapper (it's the last JSON object in stdout).
                if stdout_raw:
                    try:
                        parsed = self._parse_action_output(stdout_raw)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        logger.debug("Could not parse JSON from sandboxed stdout; returning raw output.")

            logger.debug(f"[ACTION] Parsed action output: {output}")
            return output

        except Exception as e:
            logger.exception("Error occurred while executing atomic action")
            return {"error": f"Execution failed: {str(e)}"}

    @staticmethod
    def _parse_action_output(raw_output: str) -> Any:
        """Attempt to decode a JSON object from captured stdout.

        Some actions may emit ANSI escape sequences or additional
        instructional text (for example when a CLI banner is printed)
        before the JSON payload. This helper strips ANSI codes and then
        tries to locate the JSON substring so the agent can continue
        operating instead of failing with ``JSONDecodeError``.
        """

        if not raw_output:
            return {}

        ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        cleaned = ansi_escape.sub("", raw_output).strip()

        if not cleaned:
            return {}

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("Raw action output was not pure JSON; attempting to extract payload.")
            # Attempt to salvage JSON embedded within other text.
            json_start_candidates = [idx for idx in (cleaned.find("{"), cleaned.find("[")) if idx != -1]
            if not json_start_candidates:
                raise

            start = min(json_start_candidates)
            end_brace = cleaned.rfind("}")
            end_bracket = cleaned.rfind("]")
            end_candidates = [idx for idx in (end_brace, end_bracket) if idx != -1]
            if not end_candidates:
                raise

            end = max(end_candidates)
            candidate = cleaned[start : end + 1]
            parsed = json.loads(candidate)
            logger.debug("Recovered JSON payload from action output.")
            return parsed

    async def execute_divisible_action(self, action, input_data, parent_id):
        results = {}
        for sub in action.sub_actions:
            results[sub.name] = await self.execute_action(
                sub,
                context=str(input_data),
                event_stream="",
                parent_id=parent_id,
                input_data=input_data if isinstance(input_data, dict) else None,
            )
        return results
    
    async def run_observe_step(self, action: Action, action_output: dict) -> Dict[str, Any]:
        """
        Executes the observation code with retries, to confirm action outcome.
        """
        observe = action.observer
        if not observe or not observe.code:
            return {"success": True, "message": "No observation step."}
    
        input_json = json.dumps(action_output)
        python_script = f"""import json;output = {input_json};{observe.code}"""
    
        attempt = 0
        start_time = time.time()
        while attempt < observe.max_retries and (time.time() - start_time) < observe.max_total_time_sec:
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
    
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            local_env = {}
    
            try:
                exec(python_script, {}, local_env)
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
    
                success = local_env.get("success", None)
                message = local_env.get("message", "")
    
                if success is True:
                    return {"success": True, "message": message}
                elif success is False:
                    return {"success": False, "message": message}
    
            except Exception as e:
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                logger.warning(f"[OBSERVE] Error during observation: {e}")
    
            await asyncio.sleep(observe.retry_interval_sec)
            attempt += 1
    
        return {"success": False, "message": "Observation failed or timed out."}

    # ------------------------------------------------------------------
    # helper
    # ------------------------------------------------------------------

    def get_action_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve recent action history entries.

        Args:
            limit: Maximum number of history documents to return.

        Returns:
            List[Dict[str, Any]]: Collection of run metadata in reverse
            chronological order.
        """
        return self.db_interface.get_action_history(limit)
