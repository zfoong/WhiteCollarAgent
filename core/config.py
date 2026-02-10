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

# Credential storage mode (local-only in WhiteCollarAgent)
USE_REMOTE_CREDENTIALS: bool = False

# OAuth client credentials (set via /cred config or environment variables)
import os
GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
LINKEDIN_CLIENT_ID: str = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET: str = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
ZOOM_CLIENT_ID: str = os.environ.get("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET: str = os.environ.get("ZOOM_CLIENT_SECRET", "")
DISCORD_SHARED_BOT_TOKEN: str = os.environ.get("DISCORD_SHARED_BOT_TOKEN", "")
DISCORD_SHARED_BOT_ID: str = os.environ.get("DISCORD_SHARED_BOT_ID", "")

# Shared Slack App (CraftOS-hosted)
SLACK_SHARED_CLIENT_ID: str = os.environ.get("SLACK_SHARED_CLIENT_ID", "")
SLACK_SHARED_CLIENT_SECRET: str = os.environ.get("SLACK_SHARED_CLIENT_SECRET", "")

# Shared Telegram Bot (CraftOS-hosted)
TELEGRAM_SHARED_BOT_TOKEN: str = os.environ.get("TELEGRAM_SHARED_BOT_TOKEN", "")
TELEGRAM_SHARED_BOT_USERNAME: str = os.environ.get("TELEGRAM_SHARED_BOT_USERNAME", "")

# Telegram API credentials for MTProto user login (from https://my.telegram.org)
TELEGRAM_API_ID: str = os.environ.get("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH: str = os.environ.get("TELEGRAM_API_HASH", "")

# Shared Notion Integration (CraftOS-hosted)
NOTION_SHARED_CLIENT_ID: str = os.environ.get("NOTION_SHARED_CLIENT_ID", "")
NOTION_SHARED_CLIENT_SECRET: str = os.environ.get("NOTION_SHARED_CLIENT_SECRET", "")