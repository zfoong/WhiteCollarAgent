"""Data classes and types for the TUI interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


TimelineEntry = Tuple[str, str, str]


@dataclass
class ActionEntry:
    """Container for agent action updates."""

    kind: str
    message: str
    style: str = "action"
    is_completed: bool = False
    parent_task: Optional[str] = None  # Task name if this action belongs to a task


@dataclass
class ActionUpdate:
    """Container for action update operations."""
    operation: str  # "add" or "update"
    entry: Optional[ActionEntry] = None
    entry_key: Optional[str] = None
