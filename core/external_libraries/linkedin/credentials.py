from dataclasses import dataclass
from typing import ClassVar, Optional
from core.external_libraries.credential_store import Credential


@dataclass
class LinkedInCredential(Credential):
    """
    Stores LinkedIn OAuth 2.0 credentials and associated metadata.

    Supports both personal profiles and company page access.
    LinkedIn uses URNs for identification (urn:li:person:xxx, urn:li:organization:xxx).
    """
    user_id: str                          # CraftOS user ID
    access_token: str = ""                # LinkedIn OAuth access token
    refresh_token: str = ""               # OAuth refresh token (if available)
    token_expiry: Optional[float] = None  # Unix timestamp when token expires
    linkedin_id: str = ""                 # LinkedIn URN (urn:li:person:xxx)
    name: str = ""                        # User's display name
    email: str = ""                       # User's email (from /userinfo endpoint)
    profile_picture_url: str = ""         # Profile picture URL
    # Company page access (optional - user may manage multiple organizations)
    organization_id: str = ""             # urn:li:organization:xxx
    organization_name: str = ""           # Company name

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "linkedin_id")
