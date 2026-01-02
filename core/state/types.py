from typing import Any, Dict, Literal, TypedDict
from core.config import MAX_ACTIONS_PER_TASK, MAX_TOKEN_PER_TASK
from core.logger import logger

class AgentProperties:
    def __init__(self, current_task_id: str, action_count: int, current_step_index: int = 0):
        self.current_task_id = current_task_id
        self.current_step_index: int = current_step_index
        self.action_count: int = action_count
        self.max_actions_per_task: int = MAX_ACTIONS_PER_TASK        
        self.token_count: int = 0
        self.max_tokens_per_task: int = MAX_TOKEN_PER_TASK        
        
        # Validate config value
        if self.max_actions_per_task < 5:
            logger.warning(f"[MAX ACTIONS] The maximum actions per task is set to {self.max_actions_per_task}, which is lesser than the minimum. Resetting maximum actions per task to 5")
            self.max_actions_per_task = 5
            
        if self.max_tokens_per_task < 100000:
            logger.warning(f"[MAX TOKENS] The maximum tokens per task is set to {self.max_tokens_per_task}, which is lesser than the minimum. Resetting maximum tokens per task to 100,000")
            self.max_tokens_per_task = 100000
            

    # ───────────────
    # Public API
    # ───────────────

    def set_property(self, key: str, value: Any) -> None:
        """Public: set or override an agent property"""
        setattr(self, key, value)

    def get_property(self, key: str, default: Any = None) -> Any:
        """Public: safely read a property"""
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Public: external-safe snapshot of agent state"""
        return self._to_dict()

    # ───────────────
    # Internal helpers
    # ───────────────

    def _to_dict(self) -> Dict[str, Any]:
        """Internal: canonical source of agent state"""
        return {
            "current_task_id": self.current_task_id,
            "current_step_index": self.current_step_index,
            "action_count": self.action_count,
            "max_actions_per_task": self.max_actions_per_task,
            "token_count": self.token_count,
            "max_tokens_per_task": self.max_tokens_per_task,
        }

class ConversationMessage(TypedDict):
    role: Literal["user", "agent"]
    content: str
    timestamp: str