from dataclasses import dataclass
from typing import ClassVar, Optional
from core.external_libraries.credential_store import Credential


@dataclass
class DiscordBotCredential(Credential):
    """
    Stores Discord Bot credentials.

    Discord bots use bot tokens for authentication.
    Bots can send/read messages, join voice channels, and more.
    """
    user_id: str                          # CraftOS user ID
    bot_token: str = ""                   # Discord bot token
    bot_id: str = ""                      # Discord bot application ID
    bot_username: str = ""                # Bot username (e.g., MyBot#1234)

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "bot_id")


@dataclass
class DiscordUserCredential(Credential):
    """
    Stores Discord User Account credentials.

    WARNING: Automating user accounts may violate Discord's Terms of Service.
    This is provided for self-bot/personal automation use cases only.

    User accounts can access DMs, servers, and voice channels as a regular user.
    """
    user_id: str                          # CraftOS user ID
    user_token: str = ""                  # Discord user token
    discord_user_id: str = ""             # Discord user ID
    username: str = ""                    # Discord username
    discriminator: str = ""               # Discord discriminator (if applicable)

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "discord_user_id")


@dataclass
class DiscordSharedBotGuildCredential(Credential):
    """
    Stores association between a CraftOS user and a Discord guild
    that uses the shared CraftOS Discord bot.

    This allows users to connect their Discord servers without
    creating their own bot - they simply invite the CraftOS bot.
    """
    user_id: str                          # CraftOS user ID
    guild_id: str = ""                    # Discord guild ID
    guild_name: str = ""                  # Discord guild name
    guild_icon: str = ""                  # Discord guild icon hash (optional)
    connected_at: str = ""                # ISO timestamp when connected

    UNIQUE_KEYS: ClassVar[tuple] = ("user_id", "guild_id")
