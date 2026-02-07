# core/tui/skill_settings.py
"""
Skill Settings Management for TUI.

Provides helper functions for skill management commands in the TUI.
Similar to mcp_settings.py for MCP server management.
"""

from typing import List, Dict, Tuple, Any, Optional


def list_skills() -> List[Dict[str, Any]]:
    """
    List all discovered skills with their status.

    Returns:
        List of skill info dictionaries with name, description, enabled status, etc.
    """
    try:
        from core.skill.skill_manager import skill_manager

        skills = skill_manager.get_all_skills()
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "enabled": skill.enabled,
                "user_invocable": skill.metadata.user_invocable,
                "action_sets": skill.metadata.action_sets,
                "source": str(skill.source_path),
            }
            for skill in skills
        ]
    except ImportError:
        return []
    except Exception:
        return []


def get_skill_info(name: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific skill.

    Args:
        name: The skill name.

    Returns:
        Skill info dictionary or None if not found.
    """
    try:
        from core.skill.skill_manager import skill_manager

        skill = skill_manager.get_skill(name)
        if not skill:
            return None

        return {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "user_invocable": skill.metadata.user_invocable,
            "argument_hint": skill.metadata.argument_hint,
            "action_sets": skill.metadata.action_sets,
            "allowed_tools": skill.metadata.allowed_tools,
            "source": str(skill.source_path),
            "instructions": skill.instructions,
        }
    except ImportError:
        return None
    except Exception:
        return None


def enable_skill(name: str) -> Tuple[bool, str]:
    """
    Enable a skill.

    Args:
        name: The skill name to enable.

    Returns:
        Tuple of (success, message).
    """
    try:
        from core.skill.skill_manager import skill_manager

        if skill_manager.enable_skill(name):
            return True, f"Skill '{name}' enabled."
        else:
            return False, f"Skill '{name}' not found."
    except ImportError:
        return False, "Skill system not available."
    except Exception as e:
        return False, f"Failed to enable skill: {e}"


def disable_skill(name: str) -> Tuple[bool, str]:
    """
    Disable a skill.

    Args:
        name: The skill name to disable.

    Returns:
        Tuple of (success, message).
    """
    try:
        from core.skill.skill_manager import skill_manager

        if skill_manager.disable_skill(name):
            return True, f"Skill '{name}' disabled."
        else:
            return False, f"Skill '{name}' not found."
    except ImportError:
        return False, "Skill system not available."
    except Exception as e:
        return False, f"Failed to disable skill: {e}"


def reload_skills() -> Tuple[bool, str]:
    """
    Reload skills from disk.

    Returns:
        Tuple of (success, message).
    """
    try:
        from core.skill.skill_manager import skill_manager

        count = skill_manager.reload_skills()
        return True, f"Reloaded {count} skills."
    except ImportError:
        return False, "Skill system not available."
    except Exception as e:
        return False, f"Failed to reload skills: {e}"


def get_skill_search_directories() -> List[str]:
    """
    Get the directories being searched for skills.

    Returns:
        List of directory paths.
    """
    try:
        from core.skill.skill_manager import skill_manager

        status = skill_manager.get_status()
        return status.get("search_dirs", [])
    except ImportError:
        return []
    except Exception:
        return []


def toggle_skill(name: str) -> Tuple[bool, str]:
    """
    Toggle a skill's enabled state.

    Args:
        name: The skill name to toggle.

    Returns:
        Tuple of (success, message).
    """
    try:
        from core.skill.skill_manager import skill_manager

        skill = skill_manager.get_skill(name)
        if not skill:
            return False, f"Skill '{name}' not found."

        if skill.enabled:
            return disable_skill(name)
        else:
            return enable_skill(name)
    except ImportError:
        return False, "Skill system not available."
    except Exception as e:
        return False, f"Failed to toggle skill: {e}"


def get_skill_raw_content(name: str) -> Optional[str]:
    """
    Get the raw SKILL.md content for a skill.

    Args:
        name: The skill name.

    Returns:
        Raw markdown content or None if not found.
    """
    try:
        from core.skill.skill_manager import skill_manager

        skill = skill_manager.get_skill(name)
        if not skill:
            return None

        # Read the raw file content
        if skill.source_path.exists():
            return skill.source_path.read_text(encoding="utf-8")
        return None
    except ImportError:
        return None
    except Exception:
        return None
