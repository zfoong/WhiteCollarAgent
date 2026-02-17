# core/skill/__init__.py
"""
Skill System Module

Provides skill management for CraftBot, including:
- SkillConfig: Configuration dataclasses
- SkillLoader: SKILL.md parsing
- SkillManager: Singleton for skill lifecycle management
"""

from core.skill.skill_config import Skill, SkillMetadata, SkillsConfig
from core.skill.skill_manager import skill_manager

__all__ = [
    "Skill",
    "SkillMetadata",
    "SkillsConfig",
    "skill_manager",
]
