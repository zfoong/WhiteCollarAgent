from typing import Any, Dict, Literal, TypedDict
from core.config import MAX_ACTIONS_PER_TASK, MAX_TOKEN_PER_TASK

class AgentProperties:
    def __init__(self, current_task_id: str, action_count: int):
        self.current_task_id = current_task_id
        self.action_count = action_count
        self.max_actions_per_task = MAX_ACTIONS_PER_TASK
        self.token_count = 0
        self.max_tokens_per_task = MAX_TOKEN_PER_TASK

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
            "action_count": self.action_count,
            "max_actions_per_task": self.max_actions_per_task,
            "token_count": self.token_count,
            "max_tokens_per_task": self.max_tokens_per_task,
        }

class ConversationMessage(TypedDict):
    role: Literal["user", "agent"]
    content: str
    timestamp: str