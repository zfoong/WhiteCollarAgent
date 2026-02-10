"""
Tests for Discord external app library.

Uses pytest with unittest.mock to mock the Discord REST API helper functions
(bot_api and user_api), allowing all library methods to be tested without
network access or real Discord credentials.

Usage:
    pytest core/external_libraries/discord/tests/test_discord_library.py -v
"""
import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.discord.credentials import (
    DiscordBotCredential,
    DiscordUserCredential,
    DiscordSharedBotGuildCredential,
)
from core.external_libraries.discord.external_app_library import DiscordAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset DiscordAppLibrary class-level state before each test."""
    DiscordAppLibrary._bot_credentials_store = None
    DiscordAppLibrary._user_credentials_store = None
    DiscordAppLibrary._shared_bot_guild_store = None
    DiscordAppLibrary._voice_managers = {}
    yield
    DiscordAppLibrary._bot_credentials_store = None
    DiscordAppLibrary._user_credentials_store = None
    DiscordAppLibrary._shared_bot_guild_store = None
    DiscordAppLibrary._voice_managers = {}


@pytest.fixture
def bot_credential():
    """Return a sample Discord bot credential."""
    return DiscordBotCredential(
        user_id="test_user",
        bot_token="fake-bot-token-12345",
        bot_id="bot_001",
        bot_username="TestBot#1234",
    )


@pytest.fixture
def user_credential():
    """Return a sample Discord user credential."""
    return DiscordUserCredential(
        user_id="test_user",
        user_token="fake-user-token-67890",
        discord_user_id="discord_user_001",
        username="TestUser",
        discriminator="5678",
    )


@pytest.fixture
def shared_guild_credential():
    """Return a sample shared bot guild credential."""
    return DiscordSharedBotGuildCredential(
        user_id="test_user",
        guild_id="guild_001",
        guild_name="Test Server",
        guild_icon="abc123icon",
        connected_at="2026-01-15T12:00:00Z",
    )


@pytest.fixture
def initialized_library(bot_credential, user_credential, shared_guild_credential):
    """Initialize the library with mock credential stores and inject credentials."""
    with patch("core.external_libraries.discord.external_app_library.CredentialsStore") as MockStore:
        # Create separate mock store instances for each credential type
        bot_store = MagicMock()
        user_store = MagicMock()
        guild_store = MagicMock()

        # Make the constructor return our mock stores in order
        MockStore.side_effect = [bot_store, user_store, guild_store]

        DiscordAppLibrary.initialize()

        # Wire up the mock stores
        DiscordAppLibrary._bot_credentials_store = bot_store
        DiscordAppLibrary._user_credentials_store = user_store
        DiscordAppLibrary._shared_bot_guild_store = guild_store

        # Default: get() returns the injected credential for "test_user"
        def bot_get(user_id, **filters):
            if user_id == "test_user":
                bot_id_filter = filters.get("bot_id")
                if bot_id_filter is None or bot_id_filter == bot_credential.bot_id:
                    return [bot_credential]
            return []

        def user_get(user_id, **filters):
            if user_id == "test_user":
                du_filter = filters.get("discord_user_id")
                if du_filter is None or du_filter == user_credential.discord_user_id:
                    return [user_credential]
            return []

        def guild_get(user_id, **filters):
            if user_id == "test_user":
                gid_filter = filters.get("guild_id")
                if gid_filter is None or gid_filter == shared_guild_credential.guild_id:
                    return [shared_guild_credential]
            return []

        bot_store.get.side_effect = bot_get
        user_store.get.side_effect = user_get
        guild_store.get.side_effect = guild_get

    return DiscordAppLibrary


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_stores_start_none(self):
        assert DiscordAppLibrary._bot_credentials_store is None
        assert DiscordAppLibrary._user_credentials_store is None
        assert DiscordAppLibrary._shared_bot_guild_store is None

    def test_initialize_creates_stores(self):
        with patch("core.external_libraries.discord.external_app_library.CredentialsStore") as MockStore:
            MockStore.side_effect = [MagicMock(), MagicMock(), MagicMock()]
            DiscordAppLibrary.initialize()
            assert DiscordAppLibrary._bot_credentials_store is not None
            assert DiscordAppLibrary._user_credentials_store is not None
            assert DiscordAppLibrary._shared_bot_guild_store is not None

    def test_initialize_idempotent(self):
        with patch("core.external_libraries.discord.external_app_library.CredentialsStore") as MockStore:
            MockStore.side_effect = [MagicMock(), MagicMock(), MagicMock()]
            DiscordAppLibrary.initialize()
            bot_store = DiscordAppLibrary._bot_credentials_store
            user_store = DiscordAppLibrary._user_credentials_store
            guild_store = DiscordAppLibrary._shared_bot_guild_store

            # Calling initialize again should NOT create new stores
            DiscordAppLibrary.initialize()
            assert DiscordAppLibrary._bot_credentials_store is bot_store
            assert DiscordAppLibrary._user_credentials_store is user_store
            assert DiscordAppLibrary._shared_bot_guild_store is guild_store

    def test_initialize_creates_correct_stores(self):
        with patch("core.external_libraries.discord.external_app_library.CredentialsStore") as MockStore:
            MockStore.side_effect = [MagicMock(), MagicMock(), MagicMock()]
            DiscordAppLibrary.initialize()

            # Three stores created
            assert MockStore.call_count == 3

            # Verify credential types passed to each store
            calls = MockStore.call_args_list
            assert calls[0][0][0] == DiscordBotCredential
            assert calls[0][0][1] == "discord_bot_credentials.json"
            assert calls[1][0][0] == DiscordUserCredential
            assert calls[1][0][1] == "discord_user_credentials.json"
            assert calls[2][0][0] == DiscordSharedBotGuildCredential
            assert calls[2][0][1] == "discord_shared_bot_guilds.json"


# ---------------------------------------------------------------------------
# Credential Management Tests
# ---------------------------------------------------------------------------

class TestBotCredentialManagement:

    def test_add_bot_credential(self, initialized_library, bot_credential):
        initialized_library.add_bot_credential(bot_credential)
        initialized_library._bot_credentials_store.add.assert_called_once_with(bot_credential)

    def test_get_bot_credentials_by_user(self, initialized_library):
        result = initialized_library.get_bot_credentials("test_user")
        assert len(result) == 1
        assert result[0].bot_token == "fake-bot-token-12345"

    def test_get_bot_credentials_by_user_and_bot_id(self, initialized_library):
        result = initialized_library.get_bot_credentials("test_user", bot_id="bot_001")
        assert len(result) == 1
        assert result[0].bot_id == "bot_001"

    def test_get_bot_credentials_not_found(self, initialized_library):
        result = initialized_library.get_bot_credentials("nonexistent")
        assert result == []

    def test_get_bot_credentials_wrong_bot_id(self, initialized_library):
        result = initialized_library.get_bot_credentials("test_user", bot_id="wrong_bot")
        assert result == []

    def test_remove_bot_credential(self, initialized_library):
        initialized_library.remove_bot_credential("test_user", "bot_001")
        initialized_library._bot_credentials_store.remove.assert_called_once_with(
            "test_user", bot_id="bot_001"
        )


class TestUserCredentialManagement:

    def test_add_user_credential(self, initialized_library, user_credential):
        initialized_library.add_user_credential(user_credential)
        initialized_library._user_credentials_store.add.assert_called_once_with(user_credential)

    def test_get_user_credentials_by_user(self, initialized_library):
        result = initialized_library.get_user_credentials("test_user")
        assert len(result) == 1
        assert result[0].user_token == "fake-user-token-67890"

    def test_get_user_credentials_by_discord_user_id(self, initialized_library):
        result = initialized_library.get_user_credentials("test_user", discord_user_id="discord_user_001")
        assert len(result) == 1

    def test_get_user_credentials_not_found(self, initialized_library):
        result = initialized_library.get_user_credentials("nonexistent")
        assert result == []

    def test_remove_user_credential(self, initialized_library):
        initialized_library.remove_user_credential("test_user", "discord_user_001")
        initialized_library._user_credentials_store.remove.assert_called_once_with(
            "test_user", discord_user_id="discord_user_001"
        )


class TestSharedBotGuildManagement:

    def test_add_shared_bot_guild(self, initialized_library, shared_guild_credential):
        initialized_library.add_shared_bot_guild(shared_guild_credential)
        initialized_library._shared_bot_guild_store.add.assert_called_once_with(shared_guild_credential)

    def test_get_shared_bot_guilds_by_user(self, initialized_library):
        result = initialized_library.get_shared_bot_guilds("test_user")
        assert len(result) == 1
        assert result[0].guild_id == "guild_001"

    def test_get_shared_bot_guilds_by_guild_id(self, initialized_library):
        result = initialized_library.get_shared_bot_guilds("test_user", guild_id="guild_001")
        assert len(result) == 1
        assert result[0].guild_name == "Test Server"

    def test_get_shared_bot_guilds_not_found(self, initialized_library):
        result = initialized_library.get_shared_bot_guilds("nonexistent")
        assert result == []

    def test_get_shared_bot_guilds_wrong_guild_id(self, initialized_library):
        result = initialized_library.get_shared_bot_guilds("test_user", guild_id="wrong_guild")
        assert result == []

    def test_remove_shared_bot_guild(self, initialized_library):
        initialized_library.remove_shared_bot_guild("test_user", "guild_001")
        initialized_library._shared_bot_guild_store.remove.assert_called_once_with(
            "test_user", guild_id="guild_001"
        )


class TestGetBotTokenForGuild:

    def test_returns_own_bot_token(self, initialized_library, bot_credential):
        """User's own bot credentials should be preferred."""
        result = initialized_library.get_bot_token_for_guild("test_user", "any_guild")
        assert result is not None
        token, bot_id = result
        assert token == "fake-bot-token-12345"
        assert bot_id == "bot_001"

    def test_returns_own_bot_token_with_explicit_bot_id(self, initialized_library, bot_credential):
        result = initialized_library.get_bot_token_for_guild("test_user", "any_guild", bot_id="bot_001")
        assert result is not None
        assert result[0] == "fake-bot-token-12345"

    def test_falls_back_to_shared_bot(self, initialized_library, shared_guild_credential):
        """When user has no own bot but has shared guild, use shared bot."""
        # Make bot_store return empty for this user
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []

        with patch.dict("sys.modules", {}):
            import core.config as config_mod
            with patch.object(config_mod, "DISCORD_SHARED_BOT_TOKEN", "shared-token-xyz"), \
                 patch.object(config_mod, "DISCORD_SHARED_BOT_ID", "shared_bot_999"):
                result = initialized_library.get_bot_token_for_guild("test_user", "guild_001")

        assert result is not None
        token, bot_id = result
        assert token == "shared-token-xyz"
        assert bot_id == "shared_shared_bot_999"

    def test_returns_none_when_no_credentials(self, initialized_library):
        """No own bot + no shared guild = None."""
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []
        initialized_library._shared_bot_guild_store.get.side_effect = lambda uid, **kw: []

        result = initialized_library.get_bot_token_for_guild("nonexistent", "guild_001")
        assert result is None

    def test_returns_none_when_shared_token_empty(self, initialized_library):
        """Shared guild exists but shared bot token is empty."""
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []

        import core.config as config_mod
        with patch.object(config_mod, "DISCORD_SHARED_BOT_TOKEN", ""), \
             patch.object(config_mod, "DISCORD_SHARED_BOT_ID", ""):
            result = initialized_library.get_bot_token_for_guild("test_user", "guild_001")

        assert result is None


# ---------------------------------------------------------------------------
# Bot Operations Tests
# ---------------------------------------------------------------------------

class TestGetBotInfo:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.get_bot_user.return_value = {
            "ok": True,
            "result": {
                "id": "bot_001",
                "username": "TestBot",
                "discriminator": "1234",
                "avatar": "abc",
                "bot": True,
            },
        }

        result = initialized_library.get_bot_info("test_user")

        assert result["status"] == "success"
        assert result["bot"]["id"] == "bot_001"
        assert result["bot"]["username"] == "TestBot"
        mock_bot_api.get_bot_user.assert_called_once_with("fake-bot-token-12345")

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.get_bot_user.return_value = {
            "error": "API error: 401",
        }

        result = initialized_library.get_bot_info("test_user")

        assert result["status"] == "error"
        assert "401" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_bot_info("nonexistent")

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_with_specific_bot_id(self, mock_bot_api, initialized_library):
        mock_bot_api.get_bot_user.return_value = {
            "ok": True,
            "result": {"id": "bot_001", "username": "TestBot"},
        }

        result = initialized_library.get_bot_info("test_user", bot_id="bot_001")

        assert result["status"] == "success"


class TestGetBotGuilds:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.get_bot_guilds.return_value = {
            "ok": True,
            "result": {
                "guilds": [
                    {"id": "g1", "name": "Server 1"},
                    {"id": "g2", "name": "Server 2"},
                ],
            },
        }

        result = initialized_library.get_bot_guilds("test_user")

        assert result["status"] == "success"
        assert len(result["guilds"]) == 2
        assert result["guilds"][0]["name"] == "Server 1"

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.get_bot_guilds.return_value = {"error": "API error: 403"}

        result = initialized_library.get_bot_guilds("test_user")

        assert result["status"] == "error"
        assert "403" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_bot_guilds("nonexistent")

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_empty_guilds_list(self, mock_bot_api, initialized_library):
        mock_bot_api.get_bot_guilds.return_value = {
            "ok": True,
            "result": {"guilds": []},
        }

        result = initialized_library.get_bot_guilds("test_user")

        assert result["status"] == "success"
        assert result["guilds"] == []


class TestGetGuildChannels:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.get_guild_channels.return_value = {
            "ok": True,
            "result": {
                "all_channels": [{"id": "c1", "name": "general", "type": 0}],
                "text_channels": [{"id": "c1", "name": "general", "type": 0}],
                "voice_channels": [],
                "categories": [],
            },
        }

        result = initialized_library.get_guild_channels("test_user", "guild_001")

        assert result["status"] == "success"
        assert len(result["text_channels"]) == 1
        assert result["text_channels"][0]["name"] == "general"
        mock_bot_api.get_guild_channels.assert_called_once_with("fake-bot-token-12345", "guild_001")

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.get_guild_channels.return_value = {"error": "API error: 404"}

        result = initialized_library.get_guild_channels("test_user", "guild_001")

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_guild_channels("nonexistent", "guild_001")

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]


class TestSendMessage:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.send_message.return_value = {
            "ok": True,
            "result": {
                "message_id": "msg_001",
                "channel_id": "chan_001",
                "content": "Hello!",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel_id="chan_001",
            content="Hello!",
        )

        assert result["status"] == "success"
        assert result["message_id"] == "msg_001"
        assert result["content"] == "Hello!"
        mock_bot_api.send_message.assert_called_once_with(
            "fake-bot-token-12345", "chan_001", "Hello!", None, None,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_with_embed(self, mock_bot_api, initialized_library):
        embed = {"title": "Test", "description": "An embed"}
        mock_bot_api.send_message.return_value = {
            "ok": True,
            "result": {
                "message_id": "msg_002",
                "channel_id": "chan_001",
                "content": "With embed",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel_id="chan_001",
            content="With embed",
            embed=embed,
        )

        assert result["status"] == "success"
        mock_bot_api.send_message.assert_called_once_with(
            "fake-bot-token-12345", "chan_001", "With embed", embed, None,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_with_reply(self, mock_bot_api, initialized_library):
        mock_bot_api.send_message.return_value = {
            "ok": True,
            "result": {
                "message_id": "msg_003",
                "channel_id": "chan_001",
                "content": "Reply content",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel_id="chan_001",
            content="Reply content",
            reply_to="original_msg_id",
        )

        assert result["status"] == "success"
        mock_bot_api.send_message.assert_called_once_with(
            "fake-bot-token-12345", "chan_001", "Reply content", None, "original_msg_id",
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.send_message.return_value = {"error": "API error: 403"}

        result = initialized_library.send_message(
            user_id="test_user",
            channel_id="chan_001",
            content="Hello!",
        )

        assert result["status"] == "error"
        assert "403" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.send_message(
            user_id="nonexistent",
            channel_id="chan_001",
            content="Hello!",
        )

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]


class TestGetMessages:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.get_messages.return_value = {
            "ok": True,
            "result": {
                "messages": [
                    {
                        "id": "m1",
                        "content": "Hello",
                        "author": {"id": "u1", "username": "Alice", "bot": False},
                        "timestamp": "2026-01-15T12:00:00Z",
                        "attachments": [],
                        "embeds": [],
                    },
                    {
                        "id": "m2",
                        "content": "World",
                        "author": {"id": "u2", "username": "Bob", "bot": False},
                        "timestamp": "2026-01-15T12:01:00Z",
                        "attachments": [],
                        "embeds": [],
                    },
                ],
                "count": 2,
            },
        }

        result = initialized_library.get_messages(
            user_id="test_user",
            channel_id="chan_001",
            limit=50,
        )

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["messages"]) == 2
        assert result["messages"][0]["content"] == "Hello"

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_with_before_and_after(self, mock_bot_api, initialized_library):
        mock_bot_api.get_messages.return_value = {
            "ok": True,
            "result": {"messages": [], "count": 0},
        }

        initialized_library.get_messages(
            user_id="test_user",
            channel_id="chan_001",
            limit=25,
            before="msg_before_id",
            after="msg_after_id",
        )

        mock_bot_api.get_messages.assert_called_once_with(
            "fake-bot-token-12345", "chan_001", 25, "msg_before_id", "msg_after_id",
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.get_messages.return_value = {"error": "API error: 404"}

        result = initialized_library.get_messages(
            user_id="test_user",
            channel_id="chan_001",
        )

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_messages(
            user_id="nonexistent",
            channel_id="chan_001",
        )

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]


class TestSendDmBot:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.send_dm.return_value = {
            "ok": True,
            "result": {
                "message_id": "dm_001",
                "channel_id": "dm_chan_001",
                "content": "Hey there!",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_dm_bot(
            user_id="test_user",
            recipient_id="recipient_001",
            content="Hey there!",
        )

        assert result["status"] == "success"
        assert result["message_id"] == "dm_001"
        mock_bot_api.send_dm.assert_called_once_with(
            "fake-bot-token-12345", "recipient_001", "Hey there!", None,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_with_embed(self, mock_bot_api, initialized_library):
        embed = {"title": "DM Embed", "description": "test"}
        mock_bot_api.send_dm.return_value = {
            "ok": True,
            "result": {
                "message_id": "dm_002",
                "channel_id": "dm_chan_002",
                "content": "Embedded DM",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_dm_bot(
            user_id="test_user",
            recipient_id="recipient_001",
            content="Embedded DM",
            embed=embed,
        )

        assert result["status"] == "success"
        mock_bot_api.send_dm.assert_called_once_with(
            "fake-bot-token-12345", "recipient_001", "Embedded DM", embed,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.send_dm.return_value = {"error": "Cannot DM this user"}

        result = initialized_library.send_dm_bot(
            user_id="test_user",
            recipient_id="recipient_001",
            content="Hey!",
        )

        assert result["status"] == "error"
        assert "Cannot DM" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.send_dm_bot(
            user_id="nonexistent",
            recipient_id="recipient_001",
            content="Hey!",
        )

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]


class TestGetGuildMembers:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.list_guild_members.return_value = {
            "ok": True,
            "result": {
                "members": [
                    {"user": {"id": "u1", "username": "Alice"}},
                    {"user": {"id": "u2", "username": "Bob"}},
                ],
            },
        }

        result = initialized_library.get_guild_members(
            user_id="test_user",
            guild_id="guild_001",
            limit=100,
        )

        assert result["status"] == "success"
        assert len(result["members"]) == 2
        mock_bot_api.list_guild_members.assert_called_once_with(
            "fake-bot-token-12345", "guild_001", 100,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_with_custom_limit(self, mock_bot_api, initialized_library):
        mock_bot_api.list_guild_members.return_value = {
            "ok": True,
            "result": {"members": []},
        }

        initialized_library.get_guild_members(
            user_id="test_user",
            guild_id="guild_001",
            limit=10,
        )

        mock_bot_api.list_guild_members.assert_called_once_with(
            "fake-bot-token-12345", "guild_001", 10,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.list_guild_members.return_value = {"error": "API error: 403"}

        result = initialized_library.get_guild_members(
            user_id="test_user",
            guild_id="guild_001",
        )

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_guild_members(
            user_id="nonexistent",
            guild_id="guild_001",
        )

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]


class TestAddReaction:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_success(self, mock_bot_api, initialized_library):
        mock_bot_api.add_reaction.return_value = {
            "ok": True,
            "result": {"added": True, "emoji": "thumbsup"},
        }

        result = initialized_library.add_reaction(
            user_id="test_user",
            channel_id="chan_001",
            message_id="msg_001",
            emoji="thumbsup",
        )

        assert result["status"] == "success"
        assert result["added"] is True
        assert result["emoji"] == "thumbsup"
        mock_bot_api.add_reaction.assert_called_once_with(
            "fake-bot-token-12345", "chan_001", "msg_001", "thumbsup",
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_unicode_emoji(self, mock_bot_api, initialized_library):
        mock_bot_api.add_reaction.return_value = {
            "ok": True,
            "result": {"added": True, "emoji": "\U0001f44d"},
        }

        result = initialized_library.add_reaction(
            user_id="test_user",
            channel_id="chan_001",
            message_id="msg_001",
            emoji="\U0001f44d",
        )

        assert result["status"] == "success"

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_api_error(self, mock_bot_api, initialized_library):
        mock_bot_api.add_reaction.return_value = {"error": "Unknown Emoji"}

        result = initialized_library.add_reaction(
            user_id="test_user",
            channel_id="chan_001",
            message_id="msg_001",
            emoji="invalid_emoji",
        )

        assert result["status"] == "error"
        assert "Unknown Emoji" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.add_reaction(
            user_id="nonexistent",
            channel_id="chan_001",
            message_id="msg_001",
            emoji="thumbsup",
        )

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]


# ---------------------------------------------------------------------------
# User Account Operations Tests
# ---------------------------------------------------------------------------

class TestGetUserInfo:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.get_current_user.return_value = {
            "ok": True,
            "result": {
                "id": "discord_user_001",
                "username": "TestUser",
                "discriminator": "5678",
                "email": "test@example.com",
                "avatar": "avatar_hash",
            },
        }

        result = initialized_library.get_user_info("test_user")

        assert result["status"] == "success"
        assert result["user"]["username"] == "TestUser"
        assert result["user"]["email"] == "test@example.com"
        mock_user_api.get_current_user.assert_called_once_with("fake-user-token-67890")

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.get_current_user.return_value = {"error": "API error: 401"}

        result = initialized_library.get_user_info("test_user")

        assert result["status"] == "error"
        assert "401" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_user_info("nonexistent")

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_with_specific_discord_user_id(self, mock_user_api, initialized_library):
        mock_user_api.get_current_user.return_value = {
            "ok": True,
            "result": {"id": "discord_user_001", "username": "TestUser"},
        }

        result = initialized_library.get_user_info("test_user", discord_user_id="discord_user_001")

        assert result["status"] == "success"


class TestGetUserGuilds:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.get_user_guilds.return_value = {
            "ok": True,
            "result": {
                "guilds": [
                    {"id": "g1", "name": "My Server"},
                    {"id": "g2", "name": "Another Server"},
                ],
            },
        }

        result = initialized_library.get_user_guilds("test_user")

        assert result["status"] == "success"
        assert len(result["guilds"]) == 2
        mock_user_api.get_user_guilds.assert_called_once_with("fake-user-token-67890")

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.get_user_guilds.return_value = {"error": "API error: 429"}

        result = initialized_library.get_user_guilds("test_user")

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_user_guilds("nonexistent")

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_empty_guilds(self, mock_user_api, initialized_library):
        mock_user_api.get_user_guilds.return_value = {
            "ok": True,
            "result": {"guilds": []},
        }

        result = initialized_library.get_user_guilds("test_user")

        assert result["status"] == "success"
        assert result["guilds"] == []


class TestGetDmChannels:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.get_dm_channels.return_value = {
            "ok": True,
            "result": {
                "dm_channels": [
                    {
                        "id": "dm1",
                        "type": 1,
                        "recipients": [{"id": "u1", "username": "Alice"}],
                        "last_message_id": "lm1",
                    },
                ],
                "count": 1,
            },
        }

        result = initialized_library.get_dm_channels("test_user")

        assert result["status"] == "success"
        assert len(result["dm_channels"]) == 1
        assert result["count"] == 1
        mock_user_api.get_dm_channels.assert_called_once_with("fake-user-token-67890")

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.get_dm_channels.return_value = {"error": "API error: 401"}

        result = initialized_library.get_dm_channels("test_user")

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_dm_channels("nonexistent")

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]


class TestSendMessageUser:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.send_message.return_value = {
            "ok": True,
            "result": {
                "message_id": "user_msg_001",
                "channel_id": "chan_001",
                "content": "User message",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_message_user(
            user_id="test_user",
            channel_id="chan_001",
            content="User message",
        )

        assert result["status"] == "success"
        assert result["message_id"] == "user_msg_001"
        mock_user_api.send_message.assert_called_once_with(
            "fake-user-token-67890", "chan_001", "User message", None,
        )

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_with_reply(self, mock_user_api, initialized_library):
        mock_user_api.send_message.return_value = {
            "ok": True,
            "result": {
                "message_id": "user_msg_002",
                "channel_id": "chan_001",
                "content": "Reply!",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_message_user(
            user_id="test_user",
            channel_id="chan_001",
            content="Reply!",
            reply_to="orig_msg_id",
        )

        assert result["status"] == "success"
        mock_user_api.send_message.assert_called_once_with(
            "fake-user-token-67890", "chan_001", "Reply!", "orig_msg_id",
        )

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.send_message.return_value = {"error": "API error: 403"}

        result = initialized_library.send_message_user(
            user_id="test_user",
            channel_id="chan_001",
            content="Forbidden",
        )

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.send_message_user(
            user_id="nonexistent",
            channel_id="chan_001",
            content="Hello",
        )

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]


class TestGetMessagesUser:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.get_messages.return_value = {
            "ok": True,
            "result": {
                "messages": [
                    {"id": "m1", "content": "Hi", "author": {"id": "u1", "username": "Alice"}, "timestamp": "t1", "attachments": []},
                ],
                "count": 1,
            },
        }

        result = initialized_library.get_messages_user(
            user_id="test_user",
            channel_id="chan_001",
            limit=10,
        )

        assert result["status"] == "success"
        assert result["count"] == 1
        mock_user_api.get_messages.assert_called_once_with(
            "fake-user-token-67890", "chan_001", 10, None, None,
        )

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_with_before_after(self, mock_user_api, initialized_library):
        mock_user_api.get_messages.return_value = {
            "ok": True,
            "result": {"messages": [], "count": 0},
        }

        initialized_library.get_messages_user(
            user_id="test_user",
            channel_id="chan_001",
            limit=25,
            before="b_id",
            after="a_id",
        )

        mock_user_api.get_messages.assert_called_once_with(
            "fake-user-token-67890", "chan_001", 25, "b_id", "a_id",
        )

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.get_messages.return_value = {"error": "API error: 500"}

        result = initialized_library.get_messages_user(
            user_id="test_user",
            channel_id="chan_001",
        )

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_messages_user(
            user_id="nonexistent",
            channel_id="chan_001",
        )

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]


class TestSendDmUser:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.send_dm.return_value = {
            "ok": True,
            "result": {
                "message_id": "user_dm_001",
                "channel_id": "dm_chan_001",
                "content": "User DM",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_dm_user(
            user_id="test_user",
            recipient_id="recipient_001",
            content="User DM",
        )

        assert result["status"] == "success"
        assert result["message_id"] == "user_dm_001"
        mock_user_api.send_dm.assert_called_once_with(
            "fake-user-token-67890", "recipient_001", "User DM",
        )

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.send_dm.return_value = {"error": "Cannot send DM"}

        result = initialized_library.send_dm_user(
            user_id="test_user",
            recipient_id="recipient_001",
            content="Hello",
        )

        assert result["status"] == "error"
        assert "Cannot send DM" in result["message"]

    def test_no_credentials(self, initialized_library):
        result = initialized_library.send_dm_user(
            user_id="nonexistent",
            recipient_id="recipient_001",
            content="Hello",
        )

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]


class TestGetFriends:

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_success(self, mock_user_api, initialized_library):
        mock_user_api.get_relationships.return_value = {
            "ok": True,
            "result": {
                "friends": [
                    {"id": "f1", "username": "FriendOne"},
                    {"id": "f2", "username": "FriendTwo"},
                ],
                "blocked": [],
                "incoming_requests": [],
                "outgoing_requests": [],
                "total_friends": 2,
            },
        }

        result = initialized_library.get_friends("test_user")

        assert result["status"] == "success"
        assert result["total_friends"] == 2
        assert len(result["friends"]) == 2
        mock_user_api.get_relationships.assert_called_once_with("fake-user-token-67890")

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_api_error(self, mock_user_api, initialized_library):
        mock_user_api.get_relationships.return_value = {"error": "API error: 401"}

        result = initialized_library.get_friends("test_user")

        assert result["status"] == "error"

    def test_no_credentials(self, initialized_library):
        result = initialized_library.get_friends("nonexistent")

        assert result["status"] == "error"
        assert "No Discord user credentials found" in result["message"]

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_empty_friends_list(self, mock_user_api, initialized_library):
        mock_user_api.get_relationships.return_value = {
            "ok": True,
            "result": {
                "friends": [],
                "blocked": [],
                "incoming_requests": [],
                "outgoing_requests": [],
                "total_friends": 0,
            },
        }

        result = initialized_library.get_friends("test_user")

        assert result["status"] == "success"
        assert result["total_friends"] == 0
        assert result["friends"] == []


# ---------------------------------------------------------------------------
# Voice Operations Tests
# ---------------------------------------------------------------------------

class TestJoinVoiceChannel:

    def test_no_credentials(self, initialized_library):
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []
        initialized_library._shared_bot_guild_store.get.side_effect = lambda uid, **kw: []

        result = asyncio.run(initialized_library.join_voice_channel(
            user_id="nonexistent",
            guild_id="guild_001",
            channel_id="vc_001",
        ))

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]

    def test_success(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.start.return_value = {"ok": True, "result": {"status": "connected"}}
        mock_manager.join_voice.return_value = {
            "ok": True,
            "result": {
                "status": "connected",
                "guild_id": "guild_001",
                "channel_id": "vc_001",
                "channel_name": "General Voice",
            },
        }

        with patch(
            "core.external_libraries.discord.external_app_library.DiscordVoiceManager",
            return_value=mock_manager,
        ):
            result = asyncio.run(initialized_library.join_voice_channel(
                user_id="test_user",
                guild_id="guild_001",
                channel_id="vc_001",
            ))

        # Inner result's "status" key ("connected") overwrites the outer "success"
        assert result["status"] == "connected"
        assert result["channel_id"] == "vc_001"

    def test_voice_manager_start_error(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.start.return_value = {"error": "Bot failed to connect within timeout"}

        with patch(
            "core.external_libraries.discord.external_app_library.DiscordVoiceManager",
            return_value=mock_manager,
        ):
            result = asyncio.run(initialized_library.join_voice_channel(
                user_id="test_user",
                guild_id="guild_001",
                channel_id="vc_001",
            ))

        assert result["status"] == "error"
        assert "timeout" in result["message"].lower()

    def test_import_error(self, initialized_library):
        with patch(
            "core.external_libraries.discord.external_app_library.DiscordVoiceManager",
            side_effect=ImportError("discord.py is required for voice features"),
        ):
            result = asyncio.run(initialized_library.join_voice_channel(
                user_id="test_user",
                guild_id="guild_001",
                channel_id="vc_001",
            ))

        assert result["status"] == "error"
        assert "discord.py" in result["message"]

    def test_reuses_existing_voice_manager(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.join_voice.return_value = {
            "ok": True,
            "result": {"status": "connected", "guild_id": "guild_001", "channel_id": "vc_001"},
        }

        # Pre-register the voice manager
        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.join_voice_channel(
            user_id="test_user",
            guild_id="guild_001",
            channel_id="vc_001",
        ))

        # Inner result's "status" key overwrites the outer "success"
        assert result["status"] == "connected"
        mock_manager.join_voice.assert_called_once_with("guild_001", "vc_001")

    def test_join_voice_error(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.join_voice.return_value = {"error": "Channel not found"}

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.join_voice_channel(
            user_id="test_user",
            guild_id="guild_001",
            channel_id="vc_001",
        ))

        assert result["status"] == "error"
        assert "Channel not found" in result["message"]


class TestLeaveVoiceChannel:

    def test_no_credentials(self, initialized_library):
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []
        initialized_library._shared_bot_guild_store.get.side_effect = lambda uid, **kw: []

        result = asyncio.run(initialized_library.leave_voice_channel(
            user_id="nonexistent",
            guild_id="guild_001",
        ))

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]

    def test_not_connected(self, initialized_library):
        """Bot has credentials but is not in voice."""
        result = asyncio.run(initialized_library.leave_voice_channel(
            user_id="test_user",
            guild_id="guild_001",
        ))

        assert result["status"] == "error"
        assert "not connected to voice" in result["message"].lower()

    def test_success(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.leave_voice.return_value = {
            "ok": True,
            "result": {"status": "disconnected", "guild_id": "guild_001"},
        }

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.leave_voice_channel(
            user_id="test_user",
            guild_id="guild_001",
        ))

        # Inner result's "status" key ("disconnected") overwrites the outer "success"
        assert result["status"] == "disconnected"
        assert result["guild_id"] == "guild_001"
        mock_manager.leave_voice.assert_called_once_with("guild_001")

    def test_leave_error(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.leave_voice.return_value = {"error": "Guild not found"}

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.leave_voice_channel(
            user_id="test_user",
            guild_id="guild_001",
        ))

        assert result["status"] == "error"
        assert "Guild not found" in result["message"]


class TestSpeakInVoice:

    def test_no_credentials(self, initialized_library):
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []
        initialized_library._shared_bot_guild_store.get.side_effect = lambda uid, **kw: []

        result = asyncio.run(initialized_library.speak_in_voice(
            user_id="nonexistent",
            guild_id="guild_001",
            text="Hello voice!",
        ))

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]

    def test_not_connected(self, initialized_library):
        result = asyncio.run(initialized_library.speak_in_voice(
            user_id="test_user",
            guild_id="guild_001",
            text="Hello voice!",
        ))

        assert result["status"] == "error"
        assert "not connected to voice" in result["message"].lower()

    def test_success(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.speak_text.return_value = {
            "ok": True,
            "result": {"status": "spoken", "text": "Hello voice!"},
        }

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.speak_in_voice(
            user_id="test_user",
            guild_id="guild_001",
            text="Hello voice!",
        ))

        # Inner result's "status" key ("spoken") overwrites the outer "success"
        assert result["status"] == "spoken"
        assert result["text"] == "Hello voice!"
        mock_manager.speak_text.assert_called_once_with("guild_001", "Hello voice!")

    def test_speak_error(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.speak_text.return_value = {"error": "TTS failed"}

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.speak_in_voice(
            user_id="test_user",
            guild_id="guild_001",
            text="Hello!",
        ))

        assert result["status"] == "error"
        assert "TTS failed" in result["message"]


class TestPlayAudioInVoice:

    def test_no_credentials(self, initialized_library):
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []
        initialized_library._shared_bot_guild_store.get.side_effect = lambda uid, **kw: []

        result = asyncio.run(initialized_library.play_audio_in_voice(
            user_id="nonexistent",
            guild_id="guild_001",
            audio_path="/path/to/audio.mp3",
        ))

        assert result["status"] == "error"

    def test_not_connected(self, initialized_library):
        result = asyncio.run(initialized_library.play_audio_in_voice(
            user_id="test_user",
            guild_id="guild_001",
            audio_path="/path/to/audio.mp3",
        ))

        assert result["status"] == "error"
        assert "not connected to voice" in result["message"].lower()

    def test_success(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.play_audio.return_value = {
            "ok": True,
            "result": {"status": "playing", "audio_path": "/path/to/audio.mp3"},
        }

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.play_audio_in_voice(
            user_id="test_user",
            guild_id="guild_001",
            audio_path="/path/to/audio.mp3",
        ))

        # Inner result's "status" key ("playing") overwrites the outer "success"
        assert result["status"] == "playing"
        assert result["audio_path"] == "/path/to/audio.mp3"
        mock_manager.play_audio.assert_called_once_with("guild_001", "/path/to/audio.mp3")

    def test_play_error(self, initialized_library):
        mock_manager = AsyncMock()
        mock_manager.play_audio.return_value = {"error": "File not found"}

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = asyncio.run(initialized_library.play_audio_in_voice(
            user_id="test_user",
            guild_id="guild_001",
            audio_path="/bad/path.mp3",
        ))

        assert result["status"] == "error"
        assert "File not found" in result["message"]


class TestGetVoiceStatus:

    def test_no_credentials(self, initialized_library):
        initialized_library._bot_credentials_store.get.side_effect = lambda uid, **kw: []
        initialized_library._shared_bot_guild_store.get.side_effect = lambda uid, **kw: []

        result = initialized_library.get_voice_status(
            user_id="nonexistent",
            guild_id="guild_001",
        )

        assert result["status"] == "error"
        assert "No Discord bot credentials found" in result["message"]

    def test_not_connected_returns_false(self, initialized_library):
        """Voice manager not registered means not connected."""
        result = initialized_library.get_voice_status(
            user_id="test_user",
            guild_id="guild_001",
        )

        assert result["status"] == "success"
        assert result["connected"] is False

    def test_connected(self, initialized_library):
        mock_manager = MagicMock()
        mock_manager.get_voice_status.return_value = {
            "ok": True,
            "result": {
                "connected": True,
                "guild_id": "guild_001",
                "channel_id": "vc_001",
                "is_recording": False,
                "is_speaking": False,
                "connected_at": "2026-01-15T12:00:00",
            },
        }

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = initialized_library.get_voice_status(
            user_id="test_user",
            guild_id="guild_001",
        )

        assert result["status"] == "success"
        assert result["connected"] is True
        assert result["channel_id"] == "vc_001"

    def test_voice_status_error(self, initialized_library):
        mock_manager = MagicMock()
        mock_manager.get_voice_status.return_value = {"error": "Internal error"}

        initialized_library._voice_managers["bot_001"] = mock_manager

        result = initialized_library.get_voice_status(
            user_id="test_user",
            guild_id="guild_001",
        )

        assert result["status"] == "error"
        assert "Internal error" in result["message"]


# ---------------------------------------------------------------------------
# Credential Model Tests
# ---------------------------------------------------------------------------

class TestDiscordBotCredential:

    def test_defaults(self):
        cred = DiscordBotCredential(user_id="u1")
        assert cred.bot_token == ""
        assert cred.bot_id == ""
        assert cred.bot_username == ""

    def test_all_fields(self):
        cred = DiscordBotCredential(
            user_id="u1",
            bot_token="token123",
            bot_id="b1",
            bot_username="Bot#0001",
        )
        assert cred.bot_token == "token123"
        assert cred.bot_id == "b1"
        assert cred.bot_username == "Bot#0001"

    def test_unique_keys(self):
        assert DiscordBotCredential.UNIQUE_KEYS == ("user_id", "bot_id")

    def test_to_dict(self):
        cred = DiscordBotCredential(user_id="u1", bot_token="t", bot_id="b1")
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["bot_token"] == "t"
        assert d["bot_id"] == "b1"


class TestDiscordUserCredential:

    def test_defaults(self):
        cred = DiscordUserCredential(user_id="u1")
        assert cred.user_token == ""
        assert cred.discord_user_id == ""
        assert cred.username == ""
        assert cred.discriminator == ""

    def test_all_fields(self):
        cred = DiscordUserCredential(
            user_id="u1",
            user_token="utoken",
            discord_user_id="du1",
            username="MyUser",
            discriminator="9999",
        )
        assert cred.user_token == "utoken"
        assert cred.discord_user_id == "du1"
        assert cred.username == "MyUser"
        assert cred.discriminator == "9999"

    def test_unique_keys(self):
        assert DiscordUserCredential.UNIQUE_KEYS == ("user_id", "discord_user_id")

    def test_to_dict(self):
        cred = DiscordUserCredential(
            user_id="u1",
            user_token="tok",
            discord_user_id="du1",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["user_token"] == "tok"
        assert d["discord_user_id"] == "du1"


class TestDiscordSharedBotGuildCredential:

    def test_defaults(self):
        cred = DiscordSharedBotGuildCredential(user_id="u1")
        assert cred.guild_id == ""
        assert cred.guild_name == ""
        assert cred.guild_icon == ""
        assert cred.connected_at == ""

    def test_all_fields(self):
        cred = DiscordSharedBotGuildCredential(
            user_id="u1",
            guild_id="g1",
            guild_name="My Server",
            guild_icon="icon_hash",
            connected_at="2026-01-01T00:00:00Z",
        )
        assert cred.guild_id == "g1"
        assert cred.guild_name == "My Server"
        assert cred.guild_icon == "icon_hash"
        assert cred.connected_at == "2026-01-01T00:00:00Z"

    def test_unique_keys(self):
        assert DiscordSharedBotGuildCredential.UNIQUE_KEYS == ("user_id", "guild_id")

    def test_to_dict(self):
        cred = DiscordSharedBotGuildCredential(
            user_id="u1",
            guild_id="g1",
            guild_name="Server",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["guild_id"] == "g1"
        assert d["guild_name"] == "Server"


# ---------------------------------------------------------------------------
# Edge Cases & Error Responses
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_bot_info_error_message_key_present(self, mock_bot_api, initialized_library):
        """When the helper returns an error dict without 'error' key, message defaults to None."""
        mock_bot_api.get_bot_user.return_value = {"some_other_key": "value"}

        result = initialized_library.get_bot_info("test_user")

        # No "ok" key means error path, result.get("error") returns None
        assert result["status"] == "error"
        assert result["message"] is None

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_send_message_empty_content(self, mock_bot_api, initialized_library):
        """Sending an empty message should still delegate to bot_api."""
        mock_bot_api.send_message.return_value = {
            "ok": True,
            "result": {
                "message_id": "msg_empty",
                "channel_id": "chan_001",
                "content": "",
                "timestamp": "2026-01-15T12:00:00Z",
            },
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel_id="chan_001",
            content="",
        )

        assert result["status"] == "success"
        assert result["content"] == ""

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_user_info_error_message_fallback(self, mock_user_api, initialized_library):
        mock_user_api.get_current_user.return_value = {}

        result = initialized_library.get_user_info("test_user")

        assert result["status"] == "error"
        assert result["message"] is None

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_get_messages_default_limit(self, mock_bot_api, initialized_library):
        """When limit is not specified, default 50 should be passed."""
        mock_bot_api.get_messages.return_value = {
            "ok": True,
            "result": {"messages": [], "count": 0},
        }

        initialized_library.get_messages(
            user_id="test_user",
            channel_id="chan_001",
        )

        mock_bot_api.get_messages.assert_called_once_with(
            "fake-bot-token-12345", "chan_001", 50, None, None,
        )

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_get_messages_user_default_limit(self, mock_user_api, initialized_library):
        mock_user_api.get_messages.return_value = {
            "ok": True,
            "result": {"messages": [], "count": 0},
        }

        initialized_library.get_messages_user(
            user_id="test_user",
            channel_id="chan_001",
        )

        mock_user_api.get_messages.assert_called_once_with(
            "fake-user-token-67890", "chan_001", 50, None, None,
        )

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_get_guild_members_default_limit(self, mock_bot_api, initialized_library):
        mock_bot_api.list_guild_members.return_value = {
            "ok": True,
            "result": {"members": []},
        }

        initialized_library.get_guild_members(
            user_id="test_user",
            guild_id="guild_001",
        )

        mock_bot_api.list_guild_members.assert_called_once_with(
            "fake-bot-token-12345", "guild_001", 100,
        )

    def test_multiple_bot_credentials_uses_first(self, initialized_library, bot_credential):
        """When multiple credentials exist, the first one is used."""
        second_cred = DiscordBotCredential(
            user_id="test_user",
            bot_token="second-token",
            bot_id="bot_002",
            bot_username="SecondBot#5678",
        )

        # Override mock to return two credentials
        initialized_library._bot_credentials_store.get.side_effect = (
            lambda uid, **kw: [bot_credential, second_cred] if uid == "test_user" else []
        )

        with patch("core.external_libraries.discord.external_app_library.bot_api") as mock_bot_api:
            mock_bot_api.get_bot_user.return_value = {
                "ok": True,
                "result": {"id": "bot_001", "username": "TestBot"},
            }

            initialized_library.get_bot_info("test_user")

            # Should use the first credential's token
            mock_bot_api.get_bot_user.assert_called_once_with("fake-bot-token-12345")

    @patch("core.external_libraries.discord.external_app_library.bot_api")
    def test_guild_channels_result_unpacking(self, mock_bot_api, initialized_library):
        """The guild channels result should be merged with status via ** unpacking."""
        mock_bot_api.get_guild_channels.return_value = {
            "ok": True,
            "result": {
                "all_channels": [{"id": "c1"}, {"id": "c2"}],
                "text_channels": [{"id": "c1"}],
                "voice_channels": [{"id": "c2"}],
                "categories": [],
            },
        }

        result = initialized_library.get_guild_channels("test_user", "guild_001")

        assert result["status"] == "success"
        assert "all_channels" in result
        assert "text_channels" in result
        assert "voice_channels" in result
        assert "categories" in result
        assert len(result["all_channels"]) == 2

    @patch("core.external_libraries.discord.external_app_library.user_api")
    def test_dm_channels_result_unpacking(self, mock_user_api, initialized_library):
        """The DM channels result should be merged with status via ** unpacking."""
        mock_user_api.get_dm_channels.return_value = {
            "ok": True,
            "result": {
                "dm_channels": [{"id": "dm1"}, {"id": "dm2"}],
                "count": 2,
            },
        }

        result = initialized_library.get_dm_channels("test_user")

        assert result["status"] == "success"
        assert "dm_channels" in result
        assert result["count"] == 2
