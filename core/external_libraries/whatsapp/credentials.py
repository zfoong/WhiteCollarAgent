from dataclasses import dataclass, field
from typing import ClassVar, Literal, Optional
from core.external_libraries.credential_store import Credential


@dataclass
class WhatsAppCredential(Credential):
    """
    WhatsApp credential supporting both Business API and WhatsApp Web connections.

    connection_type:
        - "business_api": Uses Meta's WhatsApp Business Cloud API (permanent token)
        - "whatsapp_web": Uses WhatsApp Web via QR code (session-based)
    """
    user_id: str
    phone_number_id: str  # For business_api: Meta's Phone Number ID; For whatsapp_web: session identifier
    connection_type: Literal["business_api", "whatsapp_web"] = "business_api"

    # Business API fields (used when connection_type == "business_api")
    business_account_id: str = ""
    access_token: str = ""

    # WhatsApp Web fields (used when connection_type == "whatsapp_web")
    session_id: str = ""  # Unique session identifier
    session_data: str = ""  # Serialized session data for reconnection
    jid: str = ""  # WhatsApp JID (e.g., 1234567890@s.whatsapp.net)

    # Common fields
    display_phone_number: str = ""

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "phone_number_id")
