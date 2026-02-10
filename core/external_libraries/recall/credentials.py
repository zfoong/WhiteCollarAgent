from dataclasses import dataclass
from typing import ClassVar, Optional
from core.external_libraries.credential_store import Credential


@dataclass
class RecallCredential(Credential):
    """
    Stores Recall.ai API credentials.

    Recall.ai uses API keys for authentication, not OAuth.
    Each user/team can have their own API key.
    """
    user_id: str                          # CraftOS user ID
    api_key: str = ""                     # Recall.ai API key
    region: str = "us"                    # API region: "us" or "eu"

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id",)
