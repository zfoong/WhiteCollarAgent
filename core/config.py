# -*- coding: utf-8 -*-
"""
Root config for base agent, should be overwrite by specialise agent
"""

from pathlib import Path

def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).resolve().parent.parent

PROJECT_ROOT = get_project_root()
AGENT_WORKSPACE_ROOT = PROJECT_ROOT / "agent_file_system/workspace"
AGENT_FILE_SYSTEM_PATH = PROJECT_ROOT / "agent_file_system"
AGENT_MEMORY_CHROMA_PATH = PROJECT_ROOT / "chroma_db_memory"
MAX_ACTIONS_PER_TASK: int = 150
MAX_TOKEN_PER_TASK: int = 6000000 # of tokens

# Memory processing configuration
PROCESS_MEMORY_AT_STARTUP: bool = True  # Process EVENT_UNPROCESSED.md into MEMORY.md at startup
MEMORY_PROCESSING_SCHEDULE_HOUR: int = 3  # Hour (0-23) to run daily memory processing