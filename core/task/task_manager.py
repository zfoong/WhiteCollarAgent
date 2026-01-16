import json, time, uuid
import shutil
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from dataclasses import asdict
from pathlib import Path
import re

from core.task.task_planner import TaskPlanner
from core.task.task import Task, Step
from core.trigger import TriggerQueue, Trigger
from core.logger import logger
from core.database_interface import DatabaseInterface
from core.event_stream.event_stream_manager import EventStreamManager
from core.config import AGENT_WORKSPACE_ROOT
from core.state.state_manager import StateManager
from core.state.agent_state import STATE

class TaskManager:
    def __init__(
        self,
        task_planner: TaskPlanner,
        triggers: TriggerQueue,
        db_interface: DatabaseInterface,
        event_stream_manager: EventStreamManager,
        state_manager: StateManager,
    ):
        """
        Coordinate task lifecycle management, including planning, execution,
        persistence, and event logging.

        The manager keeps an in-memory map of active :class:`Task` objects,
        persists changes to the database, synchronizes the state manager, and
        pushes triggers to the runtime queue to drive execution.

        Args:
            task_planner: Planner responsible for generating and updating step
                plans from high-level instructions.
            triggers: Queue used to schedule next actions for execution.
            db_interface: Persistence layer for task and step status updates.
            event_stream_manager: Event stream hub for user-visible progress
                logging.
            state_manager: In-memory state tracker for sharing task context
                with other components.
        """
        self.task_planner = task_planner
        self.triggers = triggers
        self.db_interface = db_interface
        self.event_stream_manager = event_stream_manager
        self.state_manager = state_manager
        self.active: Optional[Task] = None
        self.workspace_root = Path(AGENT_WORKSPACE_ROOT)

    def reset(self) -> None:
        """Clear all active tasks and detach any session-linked state."""
        self.active = None

    # ─────────────────────── Creation ─────────────────────────────────
    async def create_task(self, task_name: str, task_instruction: str) -> str:
        """
        Generate a new task plan and register it as active.

        The planner is invoked to break down the requested task into steps. A
        temporary workspace is provisioned, the plan is normalized into a
        :class:`Task`, and the result is recorded in the database and event
        stream. If planning fails, a minimal placeholder step is created so the
        task can still be surfaced.

        Args:
            task_name: Human-readable identifier supplied by the caller.
            task_instruction: Free-form description of the work to be
                completed.

        Returns:
            The unique identifier assigned to the created task.
        """
        task_id = f"{task_name}_{uuid.uuid4().hex[:6]}"
        task_id = self._sanitize_task_id(task_id)
        plan_json = await self.task_planner.plan_task(task_name, task_instruction)
        temp_dir = self._prepare_task_temp_dir(task_id)
        
        raw_task: Dict[str, Any] = {}
        try:
            raw_task = json.loads(plan_json)
            raw_steps = raw_task.get("steps")
            if not isinstance(raw_steps, list):
                raise ValueError("plan must be list")
            steps: List[Step] = [
                Step(
                    step_index=i,
                    step_name=st.get("step_name", "Default name value"),
                    description=st.get("description", "Default description value"),
                    action_instruction=st.get("action_instruction", ""),
                    validation_instruction=st.get("validation_instruction", ""),
                    status=st.get("status", "pending"),
                    failure_message=st.get("failure_message"),
                )
                for i, st in enumerate(raw_steps)
            ]
        except Exception as e:
            logger.error(f"[TaskManager] invalid plan – {e}")
            raw_task = {
                "goal": None,
                "inputs_params": None,
                "context": None,
            }
            steps = [Step(step_index=0, step_name="Send Message", description="Plan generation failed", action_instruction="", validation_instruction="", status="failed")]

        # Ensure a current step exists
        if steps and all(s.status != "current" for s in steps):
            first_pending = next((s for s in steps if s.status == "pending"), None)
            if first_pending:
                first_pending.status = "current"

        wf = Task(
            id=task_id,
            name=task_name,
            instruction=task_instruction,
            goal=raw_task.get("goal"),
            inputs_params=raw_task.get("inputs_params"),
            context=raw_task.get("context"),
            steps=steps,
            temp_dir=str(temp_dir),
        )
        self.active = wf
        self.db_interface.log_task(wf)
        self._sync_state_manager(wf)
        logger.debug(f"[TaskManager] Task {task_id} with {len(steps)} steps created")

        self.event_stream_manager.event_stream.temp_dir=temp_dir

        logger.debug("LOGGGING TO EVENT STREAM")
        self.event_stream_manager.log(
            "task",
            f"Created task: '{task_name}' with instruction: '{task_instruction}'.",
            display_message=f"Task created → {task_name}",
        )

        return task_id

    # ─────────────────────── Public: plan update helper ───────────────────────
    async def update_task_plan(
        self,
        event_stream: str,
        advance_next: bool = False,
    ) -> Tuple[Optional[str], Optional[Step]]:
        wf = self.active
        if not wf:
            logger.warning(f"[TaskManager] No active task found")
            return None, None

        updated_plan_json = await self.task_planner.update_plan(
            task_instruction=wf.instruction,
            task_plan=wf,
            event_stream=event_stream,
            advance_next=advance_next,
        )

        raw_task: Dict[str, Any] = {}
        try:
            raw_task = json.loads(updated_plan_json)
            raw_steps = raw_task.get("steps")
            if not isinstance(raw_steps, list):
                raise ValueError("plan must be list")
            steps: List[Step] = [
                Step(
                    step_index=i,
                    step_name=st.get("step_name", "Default name value"),
                    description=st.get("description", "Default description value"),
                    action_instruction=st.get("action_instruction", ""),
                    validation_instruction=st.get("validation_instruction", ""),
                    status=st.get("status", "pending"),
                    failure_message=st.get("failure_message"),
                )
                for i, st in enumerate(raw_steps)
            ]
        except Exception as e:
            logger.error(f"[TaskManager] invalid plan – {e}")
            raw_task = {
                "goal": None,
                "inputs_params": None,
                "context": None,
            }
            steps = [Step(step_index=0, step_name="chat", description="Plan generation failed", action_instruction="", validation_instruction="", status="failed")]

        # Ensure a current step exists
        if steps and all(s.status != "current" for s in steps):
            first_pending = next((s for s in steps if s.status == "pending"), None)
            if first_pending:
                first_pending.status = "current"

        updated_wf = Task(
            id=wf.id,
            name=wf.name,
            instruction=wf.instruction,
            goal=raw_task.get("goal"),
            inputs_params=raw_task.get("inputs_params"),
            context=raw_task.get("context"),
            steps=steps,
            temp_dir=str(wf.temp_dir),
        )
        self.active = updated_wf
        self.db_interface.log_task(updated_wf)
        self._sync_state_manager(updated_wf)
        logger.debug(f"[TaskManager] Task {wf.id} with {len(steps)} steps created")
        
        new_current_step = next((s for s in wf.steps if s.status == "current"), None)

        if new_current_step:
            if not new_current_step.action_id:
                new_current_step.action_id = str(uuid.uuid4())
            self.event_stream_manager.log(
                "task",
                f"Running new step: '{new_current_step.step_name}' – {new_current_step.description}",
                display_message=f"Running new step: '{new_current_step.step_name}' – {new_current_step.description}",
            )
            self.db_interface.log_task(wf)
            self._sync_state_manager(wf)

        return new_current_step

    # ─────────────────────── Start execution ──────────────────────────────────
    async def start_task(self) -> Dict[str, Any]:
        wf = self.active
        if not wf:
            return {"error": "task_not_found"}

        step = await self._ensure_and_log_current_step(wf)
        if not step:
            return {"error": "no_current_step"}

        await self.triggers.put(
            Trigger(
                fire_at=time.time(),
                priority=5,
                next_action_description=step.description,
                session_id=wf.id,
                payload={
                    "parent_action_id": step.action_id,
                },
            )
        )

        self.event_stream_manager.log(
            "task", 
            f"Running task step: '{step.step_name}' – {step.description}",
            display_message=f"Running task step: '{step.step_name}' – {step.description}"
        )
        logger.debug(f"[TaskManager] Step {step.step_name} queued ({wf.id})")
        return {"status": "queued", "step": step.step_name}

    # ─────────────────────── New tool-able controls ───────────────────────────
    async def mark_task_completed(self, message: Optional[str] = None) -> bool:
        wf = self.active
        if not wf:
            return False
        # finalize current step as completed if it's still open
        await self._finalize_current_step(wf, terminal_status="completed", message=message)
        await self._end_task(wf, status="completed", note=message)
        return True

    async def mark_task_error(self, message: Optional[str] = None) -> bool:
        wf = self.active
        if not wf:
            return False
        await self._finalize_current_step(wf, terminal_status="failed", message=message)
        await self._end_task(wf, status="error", note=message)
        return True

    async def mark_task_cancel(self, reason: Optional[str] = None) -> bool:
        wf = self.active
        if not wf:
            return False
        # mark all non-terminal steps as cancelled
        for st in wf.steps:
            if st.status in ("pending", "current"):
                st.status = "cancelled"
        await self._finalize_current_step(wf, terminal_status="cancelled", message=reason)
        await self._end_task(wf, status="cancelled", note=reason)
        return True

    async def start_next_step(
        self,
        replan: bool = False,
    ) -> Dict[str, Any]:
        """
        Finalize the current step as 'completed' and move to the next step.
        If replan=True, ask the planner to update the plan and advance; the
        resulting 'current' step (which may be newly created) will be used.

        Args:
            task_id: Identifier of the active task being advanced.
            replan: Whether to request a fresh plan update before selecting the
                next step.

        Returns:
            A status payload describing the next action (queued, completed, or
            no_next_step) or an error if the task is unknown.
        """
        wf = self.active
        if not wf:
            return {"error": "task_not_found"}

        # 1) finalize the current step as completed
        await self._finalize_current_step(wf, terminal_status="completed")

        new_current: Optional[Step] = None

        if replan:
            # 2a) replan and ask to advance
            new_current = await self.update_task_plan(
                event_stream="",           # no external event payload at this entry point
                advance_next=True,         # explicit baton move
            )
        else:
            # 2b) no replan: promote the next pending step
            #    (first non-terminal step after the previously current one)
            new_current = next((s for s in wf.steps if s.status == "pending"), None)
            if new_current:
                new_current.status = "current"

        # 3) if no new current, we may be done
        if not new_current:
            # If the last step is terminal and last is completed/skipped, we can auto-complete
            if wf.steps and wf.steps[-1].status in ("completed", "skipped"):
                await self._end_task(wf, status="completed", note="Auto-completed after last step")
                return {"status": "completed"}
            return {"status": "no_next_step"}

        # 4) ensure action row and enqueue trigger
        await self._ensure_and_log_current_step(wf)
        self.db_interface.log_task(wf)
        self._sync_state_manager(wf)
        STATE.set_agent_property("current_step_index", new_current.step_index)
        return {"status": "queued", "step": new_current.step_name}

    # ─────────────────────── Internal helpers ─────────────────────────────────
    async def _ensure_and_log_current_step(self, wf: Task) -> Optional[Step]:
        """Ensure there is a current step, promote the first pending if needed, and persist the change."""
        step = wf.get_current_step()
        if not step:
            return None

        updated = False
        if step.status != "current":
            step.status = "current"
            updated = True
        if not step.action_id:
            step.action_id = str(uuid.uuid4())
            updated = True

        if updated:
            self.db_interface.log_task(wf)
        self._sync_state_manager(wf)
        return step

    async def _finalize_current_step(self, wf: Task, terminal_status: str, message: Optional[str] = None) -> None:
        step = next((s for s in wf.steps if s.status == "current"), None)
        if not step:
            return
        step.status = terminal_status
        if message:
            step.failure_message = message
        self.db_interface.log_task(wf)
        self._sync_state_manager(wf)

    async def _end_task(self, wf: Task, status: str, note: Optional[str]) -> None:
        wf.status = status
        self.db_interface.log_task(wf)
        self._sync_state_manager(wf)
        self.event_stream_manager.log(
            "task",
            f"Task ended with status '{status}'. {note or ''}",
            display_message=f"Task {wf.name} → {status}",
            status=status,
        )
        STATE.set_agent_property("current_task_id", "")
        STATE.set_agent_property("action_count", 0)
        STATE.set_agent_property("token_count", 0)
        # purge any queued triggers for the session
        try:
            await self.triggers.remove_sessions([wf.id])
        except Exception:
            logger.warning(f"[TaskManager] Failed to purge triggers for {wf.id}")
        # remove from active memory
        self.active = None
        if self.state_manager:
            self.state_manager.remove_active_task()
        if status == "completed":
            self._cleanup_task_temp_dir(wf)

    def get_task(self) -> Optional[Task]:
        return self.active

    def _sync_state_manager(self, wf: Optional[Task]) -> None:
        if not self.state_manager:
            return
        self.state_manager.add_to_active_task(task=wf)

    def _prepare_task_temp_dir(self, task_id: str) -> Path:
        temp_root = self.workspace_root / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        task_temp_dir = temp_root / task_id
        task_temp_dir.mkdir(parents=True, exist_ok=True)
        return task_temp_dir

    def _cleanup_task_temp_dir(self, wf: Task) -> None:
        if not wf.temp_dir:
            return
        try:
            shutil.rmtree(wf.temp_dir, ignore_errors=True)
            logger.debug("[TaskManager] Cleaned up temp dir for task %s", wf.id)
        except Exception:
            logger.warning("[TaskManager] Failed to clean temp dir for %s", wf.id, exc_info=True)

    # ─────────────────────── helper function ───────────────────────────────────
    def _sanitize_task_id(self, s: str) -> str:
        s = s.strip()
        s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)  # replace invalid chars with _
        s = re.sub(r"_+", "_", s)               # collapse repeats
        return s.strip("._-") or "task"
