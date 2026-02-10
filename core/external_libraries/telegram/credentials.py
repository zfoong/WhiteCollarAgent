from dataclasses import dataclass, field
from typing import ClassVar, Literal
from core.external_libraries.credential_store import Credential


@dataclass
class TelegramCredential(Credential):
    """
    Telegram credential supporting both Bot API and MTProto (User Account) connections.

    For Bot API:
        - Set connection_type="bot_api"
        - Provide bot_id, bot_username, bot_token

    For MTProto (User Account):
        - Set connection_type="mtproto"
        - Provide phone_number, api_id, api_hash
        - session_string is populated after successful authentication
    """
    user_id: str
    connection_type: Literal["bot_api", "mtproto"] = "bot_api"

    # Bot API fields
    bot_id: str = ""
    bot_username: str = ""
    bot_token: str = ""

    # MTProto (User Account) fields
    phone_number: str = ""          # Phone number with country code (+1234567890)
    api_id: int = 0                 # From https://my.telegram.org
    api_hash: str = ""              # From https://my.telegram.org
    session_string: str = ""        # Telethon StringSession (populated after auth)
    account_name: str = ""          # Display name from Telegram account
    telegram_user_id: int = 0       # Numeric Telegram user ID

    # Unique key depends on connection type
    # For bot_api: user_id + bot_id
    # For mtproto: user_id + phone_number
    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "bot_id", "phone_number")
