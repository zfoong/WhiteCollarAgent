# -*- coding: utf-8 -*-
"""
Created on Thu Mar 27 21:32:01 2025

@author: zfoong
"""

import json
from dataclasses import asdict, is_dataclass
from typing import Optional, List, Dict, Any
from core.action.action import Action
from core.prompt import ASK_PLAN_PROMPT, UPDATE_PLAN_PROMPT, TASKDOC_FEWSHOTS_PROMPT
from core.database_interface import DatabaseInterface
from core.logger import logger
from core.context_engine import ContextEngine
from core.task.task import Task

# TaskPlanner
class TaskPlanner:
    def __init__(self, llm_interface, db_interface: Optional[DatabaseInterface] = None, fewshot_top_k: int = 1, context_engine: Optional[ContextEngine] = None):
        """
        Interface between high-level task descriptions and the LLM planner.

        The planner owns prompt construction, few-shot retrieval, and
        serialization helpers required to produce actionable task plans. It can
        optionally leverage stored task documents as examples to guide plan
        quality.

        Args:
            llm_interface: Client used to send prompts to the language model.
            db_interface: Optional database layer for retrieving few-shot task
                documents.
            fewshot_top_k: Number of example task documents to include in the
                prompt when available.
            context_engine: Optional engine for generating system prompts and
                contextual wrappers.
        """
        self.llm_interface = llm_interface
        self.db_interface = db_interface
        self.fewshot_top_k = fewshot_top_k
        self.context_engine = context_engine or ContextEngine()

    async def plan_task(self, task_name: str, task_instruction: str) -> str:
        """
        Request an initial step-by-step plan from the LLM.

        Args:
            task_name: Name of the task being planned (for logging/trace).
            task_instruction: Natural-language instruction provided by the
                caller describing the desired outcome.

        Returns:
            A JSON string representing the planned steps produced by the LLM.
        """
        logger.debug("[TaskPlanner] Generating initial plan from LLM...")
        plan_json = await self.ask_plan(task_instruction)
        return plan_json
    
    
    async def update_plan(
        self,
        task_instruction: str,
        task_plan: Any,
        event_stream: str,
        advance_next: bool = False,
    ) -> str:
        """
        Ask the LLM to update the plan given current steps + recent events.
        If advance_next=True, the agent is explicitly asking to move to the
        next step; the prompt includes that directive to encourage baton move.

        Args:
            task_instruction: The original user instruction that anchors the
                task.
            task_plan: Current representation of the plan (``Task`` or raw
                JSON-compatible object) to be included in the prompt.
            event_stream: Serialized recent events that should inform the
                updated plan.
            advance_next: Whether to explicitly request movement to the next
                step in the refreshed plan.

        Returns:
            A JSON string representing the updated plan, or a serialized
            snapshot of the provided plan when serialization or the LLM call
            fails.
        """
        try:
            directive = "\n\n[AGENT DIRECTIVE] advance_next = true" if advance_next else ""
            prompt_task_plan = (
                self._task_to_prompt_payload(task_plan)
                if isinstance(task_plan, Task)
                else task_plan
            )
            prompt = (
                UPDATE_PLAN_PROMPT.format(
                    user_query=task_instruction,
                    task_plan=self._serialize_for_prompt(prompt_task_plan),
                    event_stream=json.dumps(event_stream, indent=2),
                )
                + directive
            )
            logger.debug(f"[TaskPlanner] Sending update_plan prompt to LLM (advance_next={advance_next})")
            system_prompt, _ = self.context_engine.make_prompt(
                user_flags={"query": False, "expected_output": False},
                system_flags={"event_stream": False, "task_state": False},
            )
            updated_plan = await self.llm_interface.generate_response_async(system_prompt, prompt)
            json.loads(updated_plan)
            return updated_plan
        except Exception as e:
            fallback_snapshot = (
                self._serialize_for_prompt(self._task_to_prompt_payload(task_plan))
                if isinstance(task_plan, Task)
                else self._serialize_for_prompt(task_plan)
            )
            return fallback_snapshot

    async def ask_plan(self, user_query: str) -> str:
        """
        Build and send the initial planning prompt to the LLM.

        Args:
            user_query: Natural-language description of the task to plan.

        Returns:
            A JSON string representing the LLM's proposed plan.
        """
        base_prompt = ASK_PLAN_PROMPT.format(user_query=user_query)
        prompt = self._augment_prompt_with_fewshots(base_prompt, user_query)
        system_prompt, _ = self.context_engine.make_prompt(
            user_flags={"query": False, "expected_output": False},
        )
        return await self.llm_interface.generate_response_async(system_prompt, prompt)
    
    def _fallback_plan(self, plan_requirement):
        return json.dumps([
            {
                "step_index": 0,
                "step_name": "send message to user",
                "description": "Inform user that the agent is unable to generate plan",
                "status": "failed",
                "failure_message": "LLM failed to parse instruction",
            }
        ]) # TODO update fallback plan with latest task object structure
    
    def _retrieve_taskdoc_fewshots(self, user_query: str) -> List[str]:
        if not self.db_interface:
            logger.warning("[TaskPlanner] database interface not found when retrieving task doc.")
            return []
        try:
            return self.db_interface.get_task_document_texts(user_query, top_k=self.fewshot_top_k) or []
        except Exception as e:
            logger.warning(f"[TaskPlanner] Few-shot retrieval failed: {e}")
            return []

    def _augment_prompt_with_fewshots(self, base_prompt: str, user_query: str) -> str:
        examples = self._retrieve_taskdoc_fewshots(user_query)
        if not examples:
            logger.warning(f"[TaskPlanner] No example task document found for query: {user_query}")
            return base_prompt
        examples_block = "\n".join(f"\n[Task document example #{i+1}]\n{txt.strip()}" for i, txt in enumerate(examples))
        taskdoc_fewshots_prompt = TASKDOC_FEWSHOTS_PROMPT.format(examples_block=examples_block)
        return f"{base_prompt}{taskdoc_fewshots_prompt}"

    def _task_to_prompt_payload(self, task: Task) -> Dict[str, Any]:
        """Normalize a Task dataclass to the prompt schema expected by UPDATE_PLAN_PROMPT."""
        step_payloads = []
        for step in task.steps:
            step_dict = asdict(step)
            # Remove planner-only metadata
            step_dict.pop("action_id", None)
            # Drop empty failure messages to keep payload concise
            if step_dict.get("failure_message") is None:
                step_dict.pop("failure_message")
            step_payloads.append(step_dict)

        return {
            "goal": task.goal,
            "inputs_params": task.inputs_params,
            "context": task.context,
            "steps": step_payloads,
        }
    
    def _serialize_for_prompt(self, payload: Any, *, pretty: bool = False) -> str:
        """Serialize payloads (including dataclasses) to JSON strings for prompts."""
        if isinstance(payload, str):
            return payload

        if is_dataclass(payload):
            payload = asdict(payload)

        try:
            return json.dumps(payload, indent=2 if pretty else None)
        except TypeError:
            logger.error("[TaskPlanner] Failed to serialize payload for prompt", exc_info=True)
            return json.dumps({"error": "serialization_failed"})