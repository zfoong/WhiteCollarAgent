"""
Discord App Library

Provides a unified interface for Discord operations.
Supports both Bot API and User Account connections.
"""
from typing import Optional, Dict, Any, List
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.discord.credentials import DiscordBotCredential, DiscordUserCredential, DiscordSharedBotGuildCredential
from core.external_libraries.discord.helpers import discord_bot_helpers as bot_api
from core.external_libraries.discord.helpers import discord_user_helpers as user_api
from core.external_libraries.discord.helpers.discord_voice_helpers import DiscordVoiceManager


class DiscordAppLibrary:
    """
    Discord integration library supporting both bot and user connections.

    Bot API: Full-featured bot operations (send/read messages, join voice, etc.)
    User API: Self-bot operations (DMs, servers, personal automation)
    """

    _bot_credentials_store: Optional[CredentialsStore[DiscordBotCredential]] = None
    _user_credentials_store: Optional[CredentialsStore[DiscordUserCredential]] = None
    _shared_bot_guild_store: Optional[CredentialsStore[DiscordSharedBotGuildCredential]] = None
    _voice_managers: Dict[str, DiscordVoiceManager] = {}  # bot_id -> VoiceManager

    @classmethod
    def initialize(cls):
        """Initialize the credential stores."""
        if cls._bot_credentials_store is None:
            cls._bot_credentials_store = CredentialsStore(
                DiscordBotCredential,
                "discord_bot_credentials.json"
            )
        if cls._user_credentials_store is None:
            cls._user_credentials_store = CredentialsStore(
                DiscordUserCredential,
                "discord_user_credentials.json"
            )
        if cls._shared_bot_guild_store is None:
            cls._shared_bot_guild_store = CredentialsStore(
                DiscordSharedBotGuildCredential,
                "discord_shared_bot_guilds.json"
            )

    # ═══════════════════════════════════════════════════════════════════════
    # CREDENTIAL MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    @classmethod
    def add_bot_credential(cls, credential: DiscordBotCredential):
        """Add a bot credential to the store."""
        cls._bot_credentials_store.add(credential)

    @classmethod
    def get_bot_credentials(cls, user_id: str, bot_id: Optional[str] = None) -> List[DiscordBotCredential]:
        """Get bot credentials for a user."""
        if bot_id:
            return cls._bot_credentials_store.get(user_id, bot_id=bot_id)
        return cls._bot_credentials_store.get(user_id)

    @classmethod
    def remove_bot_credential(cls, user_id: str, bot_id: str):
        """Remove a bot credential."""
        cls._bot_credentials_store.remove(user_id, bot_id=bot_id)

    @classmethod
    def add_user_credential(cls, credential: DiscordUserCredential):
        """Add a user credential to the store."""
        cls._user_credentials_store.add(credential)

    @classmethod
    def get_user_credentials(cls, user_id: str, discord_user_id: Optional[str] = None) -> List[DiscordUserCredential]:
        """Get user credentials for a user."""
        if discord_user_id:
            return cls._user_credentials_store.get(user_id, discord_user_id=discord_user_id)
        return cls._user_credentials_store.get(user_id)

    @classmethod
    def remove_user_credential(cls, user_id: str, discord_user_id: str):
        """Remove a user credential."""
        cls._user_credentials_store.remove(user_id, discord_user_id=discord_user_id)

    # ═══════════════════════════════════════════════════════════════════════
    # SHARED BOT GUILD MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    @classmethod
    def add_shared_bot_guild(cls, credential: DiscordSharedBotGuildCredential):
        """Add a shared bot guild association."""
        cls._shared_bot_guild_store.add(credential)

    @classmethod
    def get_shared_bot_guilds(cls, user_id: str, guild_id: Optional[str] = None) -> List[DiscordSharedBotGuildCredential]:
        """Get shared bot guild associations for a user."""
        if guild_id:
            return cls._shared_bot_guild_store.get(user_id, guild_id=guild_id)
        return cls._shared_bot_guild_store.get(user_id)

    @classmethod
    def remove_shared_bot_guild(cls, user_id: str, guild_id: str):
        """Remove a shared bot guild association."""
        cls._shared_bot_guild_store.remove(user_id, guild_id=guild_id)

    @classmethod
    def get_bot_token_for_guild(cls, user_id: str, guild_id: str, bot_id: Optional[str] = None) -> Optional[tuple]:
        """
        Get bot token and bot_id for a guild, checking user's own bots first,
        then falling back to the shared CraftOS bot if the user has a guild association.

        Returns: (bot_token, bot_id) tuple or None if no credentials found
        """
        # First try user's own bot credentials
        creds = cls.get_bot_credentials(user_id, bot_id)
        if creds:
            cred = creds[0]
            return (cred.bot_token, cred.bot_id)

        # Check if user has shared bot guild association for this guild
        shared_guilds = cls.get_shared_bot_guilds(user_id, guild_id)
        if shared_guilds:
            # Use the shared CraftOS bot
            from core.config import DISCORD_SHARED_BOT_TOKEN, DISCORD_SHARED_BOT_ID
            if DISCORD_SHARED_BOT_TOKEN:
                return (DISCORD_SHARED_BOT_TOKEN, f"shared_{DISCORD_SHARED_BOT_ID}")

        return None

    # ═══════════════════════════════════════════════════════════════════════
    # BOT OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    @classmethod
    def get_bot_info(cls, user_id: str, bot_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get bot user information.

        Args:
            user_id: CraftOS user ID
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.get_bot_user(cred.bot_token)

        if "ok" in result:
            return {"status": "success", "bot": result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_bot_guilds(cls, user_id: str, bot_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get guilds the bot is in.

        Args:
            user_id: CraftOS user ID
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.get_bot_guilds(cred.bot_token)

        if "ok" in result:
            return {"status": "success", "guilds": result["result"]["guilds"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_guild_channels(
        cls,
        user_id: str,
        guild_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get channels in a guild.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.get_guild_channels(cred.bot_token, guild_id)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def send_message(
        cls,
        user_id: str,
        channel_id: str,
        content: str,
        embed: Optional[Dict] = None,
        reply_to: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a channel using bot.

        Args:
            user_id: CraftOS user ID
            channel_id: Discord channel ID
            content: Message content
            embed: Optional embed
            reply_to: Optional message ID to reply to
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.send_message(cred.bot_token, channel_id, content, embed, reply_to)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_messages(
        cls,
        user_id: str,
        channel_id: str,
        limit: int = 50,
        before: Optional[str] = None,
        after: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get messages from a channel using bot.

        Args:
            user_id: CraftOS user ID
            channel_id: Discord channel ID
            limit: Max messages to retrieve
            before: Get messages before this ID
            after: Get messages after this ID
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.get_messages(cred.bot_token, channel_id, limit, before, after)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def send_dm_bot(
        cls,
        user_id: str,
        recipient_id: str,
        content: str,
        embed: Optional[Dict] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a DM to a user using bot.

        Args:
            user_id: CraftOS user ID
            recipient_id: Discord user ID to DM
            content: Message content
            embed: Optional embed
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.send_dm(cred.bot_token, recipient_id, content, embed)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_guild_members(
        cls,
        user_id: str,
        guild_id: str,
        limit: int = 100,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get members of a guild.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            limit: Max members to retrieve
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.list_guild_members(cred.bot_token, guild_id, limit)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def add_reaction(
        cls,
        user_id: str,
        channel_id: str,
        message_id: str,
        emoji: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a reaction to a message.

        Args:
            user_id: CraftOS user ID
            channel_id: Discord channel ID
            message_id: Discord message ID
            emoji: Emoji to react with
            bot_id: Optional specific bot ID
        """
        creds = cls.get_bot_credentials(user_id, bot_id)
        if not creds:
            return {"status": "error", "message": "No Discord bot credentials found"}

        cred = creds[0]
        result = bot_api.add_reaction(cred.bot_token, channel_id, message_id, emoji)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    # ═══════════════════════════════════════════════════════════════════════
    # USER ACCOUNT OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    @classmethod
    def get_user_info(cls, user_id: str, discord_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user account information.

        Args:
            user_id: CraftOS user ID
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.get_current_user(cred.user_token)

        if "ok" in result:
            return {"status": "success", "user": result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_user_guilds(cls, user_id: str, discord_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get guilds the user is in.

        Args:
            user_id: CraftOS user ID
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.get_user_guilds(cred.user_token)

        if "ok" in result:
            return {"status": "success", "guilds": result["result"]["guilds"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_dm_channels(cls, user_id: str, discord_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user's DM channels.

        Args:
            user_id: CraftOS user ID
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.get_dm_channels(cred.user_token)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def send_message_user(
        cls,
        user_id: str,
        channel_id: str,
        content: str,
        reply_to: Optional[str] = None,
        discord_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message as user account.

        Args:
            user_id: CraftOS user ID
            channel_id: Discord channel ID
            content: Message content
            reply_to: Optional message ID to reply to
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.send_message(cred.user_token, channel_id, content, reply_to)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_messages_user(
        cls,
        user_id: str,
        channel_id: str,
        limit: int = 50,
        before: Optional[str] = None,
        after: Optional[str] = None,
        discord_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get messages as user account.

        Args:
            user_id: CraftOS user ID
            channel_id: Discord channel ID
            limit: Max messages to retrieve
            before: Get messages before this ID
            after: Get messages after this ID
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.get_messages(cred.user_token, channel_id, limit, before, after)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def send_dm_user(
        cls,
        user_id: str,
        recipient_id: str,
        content: str,
        discord_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a DM as user account.

        Args:
            user_id: CraftOS user ID
            recipient_id: Discord user ID to DM
            content: Message content
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.send_dm(cred.user_token, recipient_id, content)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_friends(cls, user_id: str, discord_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user's friends list.

        Args:
            user_id: CraftOS user ID
            discord_user_id: Optional specific Discord user ID
        """
        creds = cls.get_user_credentials(user_id, discord_user_id)
        if not creds:
            return {"status": "error", "message": "No Discord user credentials found"}

        cred = creds[0]
        result = user_api.get_relationships(cred.user_token)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    # ═══════════════════════════════════════════════════════════════════════
    # VOICE OPERATIONS (Requires discord.py)
    # ═══════════════════════════════════════════════════════════════════════

    @classmethod
    async def join_voice_channel(
        cls,
        user_id: str,
        guild_id: str,
        channel_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Join a voice channel with the bot.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            channel_id: Voice channel ID
            bot_id: Optional specific bot ID
        """
        # Get bot token (user's own bot or shared CraftOS bot)
        token_info = cls.get_bot_token_for_guild(user_id, guild_id, bot_id)
        if not token_info:
            return {"status": "error", "message": "No Discord bot credentials found. Connect your own bot or invite the CraftOS bot to this server."}

        bot_token, effective_bot_id = token_info

        # Get or create voice manager for this bot
        if effective_bot_id not in cls._voice_managers:
            try:
                manager = DiscordVoiceManager(bot_token)
                start_result = await manager.start()
                if "error" in start_result:
                    return {"status": "error", "message": start_result["error"]}
                cls._voice_managers[effective_bot_id] = manager
            except ImportError as e:
                return {"status": "error", "message": str(e)}

        manager = cls._voice_managers[effective_bot_id]
        result = await manager.join_voice(guild_id, channel_id)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    async def leave_voice_channel(
        cls,
        user_id: str,
        guild_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Leave a voice channel.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            bot_id: Optional specific bot ID
        """
        # Get bot token (user's own bot or shared CraftOS bot)
        token_info = cls.get_bot_token_for_guild(user_id, guild_id, bot_id)
        if not token_info:
            return {"status": "error", "message": "No Discord bot credentials found"}

        _, effective_bot_id = token_info

        if effective_bot_id not in cls._voice_managers:
            return {"status": "error", "message": "Bot not connected to voice"}

        manager = cls._voice_managers[effective_bot_id]
        result = await manager.leave_voice(guild_id)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    async def speak_in_voice(
        cls,
        user_id: str,
        guild_id: str,
        text: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Speak text in a voice channel using TTS.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            text: Text to speak
            bot_id: Optional specific bot ID
        """
        # Get bot token (user's own bot or shared CraftOS bot)
        token_info = cls.get_bot_token_for_guild(user_id, guild_id, bot_id)
        if not token_info:
            return {"status": "error", "message": "No Discord bot credentials found"}

        _, effective_bot_id = token_info

        if effective_bot_id not in cls._voice_managers:
            return {"status": "error", "message": "Bot not connected to voice"}

        manager = cls._voice_managers[effective_bot_id]
        result = await manager.speak_text(guild_id, text)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    async def play_audio_in_voice(
        cls,
        user_id: str,
        guild_id: str,
        audio_path: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Play an audio file in a voice channel.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            audio_path: Path to audio file
            bot_id: Optional specific bot ID
        """
        # Get bot token (user's own bot or shared CraftOS bot)
        token_info = cls.get_bot_token_for_guild(user_id, guild_id, bot_id)
        if not token_info:
            return {"status": "error", "message": "No Discord bot credentials found"}

        _, effective_bot_id = token_info

        if effective_bot_id not in cls._voice_managers:
            return {"status": "error", "message": "Bot not connected to voice"}

        manager = cls._voice_managers[effective_bot_id]
        result = await manager.play_audio(guild_id, audio_path)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}

    @classmethod
    def get_voice_status(
        cls,
        user_id: str,
        guild_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get voice connection status.

        Args:
            user_id: CraftOS user ID
            guild_id: Discord guild ID
            bot_id: Optional specific bot ID
        """
        # Get bot token (user's own bot or shared CraftOS bot)
        token_info = cls.get_bot_token_for_guild(user_id, guild_id, bot_id)
        if not token_info:
            return {"status": "error", "message": "No Discord bot credentials found"}

        _, effective_bot_id = token_info

        if effective_bot_id not in cls._voice_managers:
            return {"status": "success", "connected": False}

        manager = cls._voice_managers[effective_bot_id]
        result = manager.get_voice_status(guild_id)

        if "ok" in result:
            return {"status": "success", **result["result"]}
        return {"status": "error", "message": result.get("error")}
