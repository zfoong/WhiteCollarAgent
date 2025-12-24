# -*- coding: utf-8 -*-
"""
Root config for base agent, should be overwrite by specialise agent
"""

from pathlib import Path
from typing import Dict, List, Optional

def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).resolve().parent.parent

PROJECT_ROOT = get_project_root()
AGENT_WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
MAX_ACTIONS_PER_TASK: int = 5
MAX_TOKEN_PER_TASK: int = 3000000 # of tokens