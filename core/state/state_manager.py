from typing import Dict, List, Optional, Any
from core.state.types import AgentProperties
from core.state.agent_state import STATE
from core.event_stream.event_stream_manager import EventStreamManager
from core.task.task import Task, Step
from core.logger import logger


class StateManager:
    """Manages task state and runtime session data."""

    def __init__(
        self,
        event_stream_manager: EventStreamManager,
    ):
        # We have two types of state, persistant and session state
        # Persistant state are state that will not be changed frequently,
        # e.g. agent properties
        # Session state are states that is short-termed, one time used
        # e.g. current task, event stream, action state
        self.task: Optional[Task] = None
        self.event_stream_manager = event_stream_manager

    async def start_session(self, gui_mode: bool = False):

        event_stream = self.get_event_stream_snapshot()
        current_task: Optional[Task] = self.get_current_task_state()

        logger.debug(f"[CURRENT TASK]: this is the current_task: {current_task}")

        STATE.refresh(
            current_task=current_task,
            event_stream=event_stream,
            gui_mode=gui_mode
        )


    def clean_state(self):
        """
        End the session, clearing session context so the next user input starts fresh.
        """
        STATE.refresh()

    def reset(self) -> None:
        """Fully reset runtime state, including tasks and session context."""
        self.task = None
        STATE.agent_properties: AgentProperties = AgentProperties(current_task_id="", action_count=0, current_step_index=0)
        if self.event_stream_manager:
            self.event_stream_manager.clear_all()
        self.clean_state()

    def record_user_message(self, content: str) -> None:
        """Record a user message to the event stream."""
        self.event_stream_manager.log(
            "user message",
            content,
            display_message=content
        )
        self.bump_event_stream()

    def record_agent_message(self, content: str) -> None:
        """Record an agent message to the event stream."""
        self.event_stream_manager.log(
            "agent message",
            content,
            display_message=content
        )
        self.bump_event_stream()
    
    def get_current_step(self) -> Optional[Step]:
        wf: Optional[Task] = self.task
        if not wf:
            return None
        return wf.get_current_step()
    
    def get_event_stream_snapshot(self) -> str:
        return self.event_stream_manager.snapshot()
        
    def get_current_task_state(self) -> Optional[Task]:
        task: Optional[Task] = self.task

        logger.debug(f"[TASK] task in StateManager: {task}")

        if not task:
            logger.debug("[TASK] task not found in StateManager")
            return None

        # Build minimal per-step representation
        steps_list: List[Step] = []
        for step in task.steps:
            item: Dict[str, Any] = {}
            item = {
                "step_index": step.step_index,
                "step_name": step.step_name,
                "description": step.description,
                "action_instruction": step.action_instruction,
                "validation_instruction": step.validation_instruction,
                "status": step.status,
            }
            if step.failure_message:
                item["failure_message"] = step.failure_message
            steps_list.append(Step(**item, action_id=step.action_id))

        task: Task = Task(
            id=task.id,
            name=task.name,
            instruction=task.instruction,
            goal=task.goal,
            inputs_params=task.inputs_params,
            context=task.context,
            steps=steps_list
        )

        return task

    def bump_task_state(self) -> None:
        STATE.update_current_task(
                self.get_current_task_state()
            )
            
    def bump_event_stream(self) -> None:
        STATE.update_event_stream(self.get_event_stream_snapshot())
        
    def is_running_task(self) -> bool:
        if self.task:
            return True
        else:
            return False
    
    def add_to_active_task(self, task: Optional[Task]) -> None:
        if task is None:
            self.task = None
            STATE.update_current_task(None)
        else:
            self.task = task
            self.bump_task_state()

    def remove_active_task(self) -> None:
        self.task = None
        STATE.update_current_task(None)
