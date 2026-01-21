# -*- coding: utf-8 -*-
"""
Root config for base agent, should be overwrite by specialise agent
"""

from pathlib import Path

def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).resolve().parent.parent

PROJECT_ROOT = get_project_root()
AGENT_WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
MAX_ACTIONS_PER_TASK: int = 150
MAX_TOKEN_PER_TASK: int = 6000000 # of tokens