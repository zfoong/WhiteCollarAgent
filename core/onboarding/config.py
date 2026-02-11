# -*- coding: utf-8 -*-
"""
Configuration constants for the onboarding module.
"""

from pathlib import Path
from core.config import PROJECT_ROOT

# Onboarding config file (in core/config/ with other config files)
ONBOARDING_CONFIG_FILE: Path = PROJECT_ROOT / "core" / "config" / "onboarding_config.json"

# Default values
DEFAULT_AGENT_NAME: str = "Agent"
DEFAULT_USER_NAME: str = ""

# Hard onboarding steps configuration
# Each step has: id, required (must complete), title (display name)
HARD_ONBOARDING_STEPS = [
    {"id": "provider", "required": True, "title": "LLM Provider"},
    {"id": "api_key", "required": True, "title": "API Key"},
    {"id": "user_name", "required": False, "title": "Your Name"},
    {"id": "agent_name", "required": False, "title": "Agent Name"},
    {"id": "mcp", "required": False, "title": "MCP Servers"},
    {"id": "skills", "required": False, "title": "Skills"},
]

# Soft onboarding interview questions template
SOFT_ONBOARDING_QUESTIONS = [
    "name",           # What should I call you?
    "job",            # What do you do for work?
    "location",       # Where are you located?
    "timezone",       # What timezone are you in?
    "tone",           # How would you like me to communicate?
    "proactivity",    # Should I be proactive or wait for instructions?
    "approval",       # What actions need your approval?
]
