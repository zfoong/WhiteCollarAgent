from dataclasses import dataclass
from typing import ClassVar, Optional
from core.external_libraries.credential_store import Credential


@dataclass
class ZoomCredential(Credential):
    """
    Stores Zoom OAuth 2.0 credentials and associated metadata.

    Supports Zoom user accounts with meeting management capabilities.
    """
    user_id: str                          # CraftOS user ID
    access_token: str = ""                # Zoom OAuth access token
    refresh_token: str = ""               # OAuth refresh token
    token_expiry: Optional[float] = None  # Unix timestamp when token expires
    zoom_user_id: str = ""                # Zoom user ID
    email: str = ""                       # User's email
    display_name: str = ""                # User's display name
    account_id: str = ""                  # Zoom account ID (for org accounts)

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "zoom_user_id")
