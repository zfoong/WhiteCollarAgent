from dataclasses import dataclass, field
from typing import ClassVar, Optional
from core.external_libraries.credential_store import Credential


@dataclass
class WhatsAppCredential(Credential):
    """
    WhatsApp credential for WhatsApp Web connections via QR code (session-based).
    """
    user_id: str
    phone_number_id: str  # Session identifier

    # WhatsApp Web fields
    session_id: str = ""  # Unique session identifier
    session_data: str = ""  # Serialized session data for reconnection
    jid: str = ""  # WhatsApp JID (e.g., 1234567890@s.whatsapp.net)

    # Common fields
    display_phone_number: str = ""

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "phone_number_id")
