from dataclasses import dataclass
from typing import ClassVar
from core.external_libraries.credential_store import Credential

@dataclass
class NotionCredential(Credential):
    user_id: str
    workspace_id: str
    workspace_name: str
    token: str
    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "workspace_id")
