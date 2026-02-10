from dataclasses import dataclass
from typing import ClassVar
from core.external_libraries.credential_store import Credential

@dataclass
class SlackCredential(Credential):
    user_id: str
    workspace_id: str
    workspace_name: str
    bot_token: str
    team_id: str
    app_id: str = ""
    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "workspace_id")
