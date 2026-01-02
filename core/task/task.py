# -*- coding: utf-8 -*-
"""
Created on Wed Apr 30 15:22:43 2025

@author: zfoong
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

@dataclass
class Step:
    step_index: int
    step_name: str
    description: str
    # Allowed: pending | current | completed | failed | skipped | cancelled
    action_instruction: str
    validation_instruction: str    
    status: str = "pending"
    failure_message: Optional[str] = None
    # Identifier used to correlate steps across logs and triggers
    action_id: Optional[str] = None

    def to_dict(self, fold: bool = False, current_step_index: int = 0) -> Dict[str, Any]:
        """Return a dictionary representation of the step."""
        item = {
            "step_index": self.step_index,
            "step_name": self.step_name,
            "status": self.status,
        }
        if self.failure_message:
            item["failure_message"] = self.failure_message

        if fold and current_step_index == self.step_index:
            item["description"] = self.description
            item["action_instruction"] = self.action_instruction
            item["validation_instruction"] = self.validation_instruction
            
        return item

@dataclass
class Task:
    id: str
    name: str
    instruction: str
    steps: List[Step]
    goal: str
    inputs_params: str
    context: str
    temp_dir: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Allowed: running | completed | error | paused | cancelled
    status: str = "running"
    results: Dict[str, Any] = field(default_factory=dict)

    def get_current_step(self) -> Optional[Step]:
        """
        Return the step that should be executed next for this task.

        The method first prefers any step explicitly marked as ``current`` to
        preserve planner intent. If none is marked, it falls back to the first
        ``pending`` step so execution can continue from the beginning of the
        queue. If every step is terminal, ``None`` is returned to indicate that
        the task has fully progressed.

        Returns:
            The :class:`Step` currently in progress or queued next, or ``None``
            when no runnable steps remain.
        """
        # Prefer explicitly marked current
        for step in self.steps:
            if step.status == "current":
                return step
        # Fallback to first pending if no explicit current
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def to_dict(self, fold: bool = False, current_step_index: int = 0) -> Dict[str, Any]:
        """Return a dictionary representation of the task."""
        return {
            "id": self.id,
            "name": self.name,
            "instruction": self.instruction,
            "goal": self.goal,
            "inputs_params": self.inputs_params,
            "context": self.context,
            "steps": [step.to_dict(fold=fold, current_step_index=current_step_index) for step in self.steps],
        }