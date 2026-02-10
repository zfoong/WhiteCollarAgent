"""
Tests for Slack external library.

Uses pytest with unittest.mock to mock the Slack helper functions,
allowing all library methods to be tested without real API calls.

Usage:
    pytest core/external_libraries/slack/tests/test_slack_library.py -v
"""
import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.slack.credentials import SlackCredential
from core.external_libraries.slack.external_app_library import SlackAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset SlackAppLibrary state before each test."""
    SlackAppLibrary._initialized = False
    SlackAppLibrary._credential_store = None
    SlackAppLibrary._use_remote = False
    yield
    SlackAppLibrary._initialized = False
    SlackAppLibrary._credential_store = None
    SlackAppLibrary._use_remote = False


@pytest.fixture
def mock_credential():
    """Return a sample Slack credential."""
    return SlackCredential(
        user_id="test_user",
        workspace_id="W123",
        workspace_name="Test Workspace",
        bot_token="xoxb-test-token-123",
        team_id="T123",
        app_id="A123",
    )


@pytest.fixture
def initialized_library(mock_credential):
    """Initialize the library and inject a mock credential store."""
    with patch("core.external_libraries.slack.external_app_library.USE_REMOTE_CREDENTIALS", False):
        SlackAppLibrary.initialize()
    SlackAppLibrary.get_credential_store().add(mock_credential)
    return SlackAppLibrary


# ---------------------------------------------------------------------------
# Initialization & Credential Tests
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_initialize(self):
        assert not SlackAppLibrary._initialized
        with patch("core.external_libraries.slack.external_app_library.USE_REMOTE_CREDENTIALS", False):
            SlackAppLibrary.initialize()
        assert SlackAppLibrary._initialized
        assert SlackAppLibrary._credential_store is not None

    def test_initialize_idempotent(self):
        with patch("core.external_libraries.slack.external_app_library.USE_REMOTE_CREDENTIALS", False):
            SlackAppLibrary.initialize()
        store = SlackAppLibrary._credential_store
        SlackAppLibrary.initialize()
        assert SlackAppLibrary._credential_store is store

    def test_get_name(self):
        assert SlackAppLibrary.get_name() == "Slack"

    def test_get_credential_store_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            SlackAppLibrary.get_credential_store()

    def test_get_credential_store_after_init(self):
        with patch("core.external_libraries.slack.external_app_library.USE_REMOTE_CREDENTIALS", False):
            SlackAppLibrary.initialize()
        store = SlackAppLibrary.get_credential_store()
        assert store is not None

    def test_initialize_with_remote_credentials(self):
        with patch("core.external_libraries.slack.external_app_library.USE_REMOTE_CREDENTIALS", True):
            SlackAppLibrary.initialize()
        assert SlackAppLibrary._initialized
        assert SlackAppLibrary._use_remote is True
        assert SlackAppLibrary._credential_store is not None


class TestValidateConnection:

    def test_validate_no_credentials(self):
        with patch("core.external_libraries.slack.external_app_library.USE_REMOTE_CREDENTIALS", False):
            SlackAppLibrary.initialize()
        assert SlackAppLibrary.validate_connection(user_id="nonexistent") is False

    def test_validate_with_credentials(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(user_id="test_user") is True

    def test_validate_with_wrong_user(self, initialized_library):
        assert initialized_library.validate_connection(user_id="other_user") is False

    def test_validate_with_workspace_id(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(
            user_id="test_user",
            workspace_id="W123",
        ) is True

    def test_validate_with_wrong_workspace_id(self, initialized_library):
        assert initialized_library.validate_connection(
            user_id="test_user",
            workspace_id="WRONG_WS",
        ) is False


class TestGetCredentials:

    def test_get_credentials_found(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.user_id == "test_user"
        assert cred.bot_token == "xoxb-test-token-123"
        assert cred.workspace_id == "W123"

    def test_get_credentials_not_found(self, initialized_library):
        cred = initialized_library.get_credentials(user_id="nonexistent")
        assert cred is None

    def test_get_credentials_with_workspace_id(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            workspace_id="W123",
        )
        assert cred is not None
        assert cred.workspace_id == "W123"

    def test_get_credentials_with_wrong_workspace_id(self, initialized_library):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            workspace_id="WRONG_WS",
        )
        assert cred is None


# ---------------------------------------------------------------------------
# Async Validate / Get Credentials Tests
# ---------------------------------------------------------------------------

class TestAsyncValidateConnection:

    def test_validate_async_with_credentials(self, initialized_library):
        result = asyncio.run(
            initialized_library.validate_connection_async(user_id="test_user")
        )
        assert result is True

    def test_validate_async_no_credentials(self, initialized_library):
        result = asyncio.run(
            initialized_library.validate_connection_async(user_id="nonexistent")
        )
        assert result is False

    def test_validate_async_with_workspace_id(self, initialized_library):
        result = asyncio.run(
            initialized_library.validate_connection_async(
                user_id="test_user",
                workspace_id="W123",
            )
        )
        assert result is True

    def test_validate_async_with_wrong_workspace_id(self, initialized_library):
        result = asyncio.run(
            initialized_library.validate_connection_async(
                user_id="test_user",
                workspace_id="WRONG_WS",
            )
        )
        assert result is False


class TestGetCredentialsAsync:

    def test_get_credentials_async_found(self, initialized_library):
        cred = asyncio.run(
            initialized_library.get_credentials_async(user_id="test_user")
        )
        assert cred is not None
        assert cred.bot_token == "xoxb-test-token-123"

    def test_get_credentials_async_not_found(self, initialized_library):
        cred = asyncio.run(
            initialized_library.get_credentials_async(user_id="nonexistent")
        )
        assert cred is None

    def test_get_credentials_async_with_workspace_id(self, initialized_library):
        cred = asyncio.run(
            initialized_library.get_credentials_async(
                user_id="test_user",
                workspace_id="W123",
            )
        )
        assert cred is not None
        assert cred.workspace_id == "W123"


# ---------------------------------------------------------------------------
# Send Message Tests
# ---------------------------------------------------------------------------

class TestSendMessage:

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_success(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.123456",
            "message": {"text": "Hello!"},
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text="Hello!",
        )

        assert result["status"] == "success"
        assert result["message"]["ok"] is True
        assert result["message"]["channel"] == "C123"
        mock_send.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            text="Hello!",
            thread_ts=None,
        )

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_with_thread_ts(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.999999",
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text="Thread reply",
            thread_ts="1234567890.123456",
        )

        assert result["status"] == "success"
        mock_send.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            text="Thread reply",
            thread_ts="1234567890.123456",
        )

    def test_send_message_no_credential(self, initialized_library):
        result = initialized_library.send_message(
            user_id="nonexistent",
            channel="C123",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_api_error(self, mock_send, initialized_library):
        mock_send.return_value = {
            "error": "channel_not_found",
            "details": {"ok": False, "error": "channel_not_found"},
        }

        result = initialized_library.send_message(
            user_id="test_user",
            channel="INVALID",
            text="Hello!",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Network error")

        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text="Hello!",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Network error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_with_workspace_id(self, mock_send, initialized_library):
        mock_send.return_value = {"ok": True, "channel": "C123", "ts": "123.456"}

        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text="Hello!",
            workspace_id="W123",
        )

        assert result["status"] == "success"

    def test_send_message_wrong_workspace_id(self, initialized_library):
        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text="Hello!",
            workspace_id="WRONG_WS",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]


# ---------------------------------------------------------------------------
# List Channels Tests
# ---------------------------------------------------------------------------

class TestListChannels:

    @patch("core.external_libraries.slack.external_app_library.list_channels")
    def test_list_channels_success(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "channels": [
                {"id": "C001", "name": "general", "is_channel": True},
                {"id": "C002", "name": "random", "is_channel": True},
            ],
        }

        result = initialized_library.list_channels(user_id="test_user")

        assert result["status"] == "success"
        assert len(result["channels"]) == 2
        assert result["channels"][0]["name"] == "general"
        mock_list.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            types="public_channel,private_channel",
            limit=100,
        )

    @patch("core.external_libraries.slack.external_app_library.list_channels")
    def test_list_channels_custom_types_and_limit(self, mock_list, initialized_library):
        mock_list.return_value = {"ok": True, "channels": []}

        result = initialized_library.list_channels(
            user_id="test_user",
            types="im",
            limit=10,
        )

        assert result["status"] == "success"
        mock_list.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            types="im",
            limit=10,
        )

    def test_list_channels_no_credential(self, initialized_library):
        result = initialized_library.list_channels(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.list_channels")
    def test_list_channels_api_error(self, mock_list, initialized_library):
        mock_list.return_value = {
            "error": "invalid_auth",
            "details": {"ok": False, "error": "invalid_auth"},
        }

        result = initialized_library.list_channels(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.list_channels")
    def test_list_channels_exception(self, mock_list, initialized_library):
        mock_list.side_effect = Exception("Timeout")

        result = initialized_library.list_channels(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.list_channels")
    def test_list_channels_empty(self, mock_list, initialized_library):
        mock_list.return_value = {"ok": True, "channels": []}

        result = initialized_library.list_channels(user_id="test_user")

        assert result["status"] == "success"
        assert result["channels"] == []


# ---------------------------------------------------------------------------
# List Users Tests
# ---------------------------------------------------------------------------

class TestListUsers:

    @patch("core.external_libraries.slack.external_app_library.list_users")
    def test_list_users_success(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "members": [
                {"id": "U001", "name": "alice", "real_name": "Alice Smith"},
                {"id": "U002", "name": "bob", "real_name": "Bob Jones"},
            ],
        }

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "success"
        assert len(result["users"]) == 2
        assert result["users"][0]["name"] == "alice"
        mock_list.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            limit=100,
        )

    @patch("core.external_libraries.slack.external_app_library.list_users")
    def test_list_users_custom_limit(self, mock_list, initialized_library):
        mock_list.return_value = {"ok": True, "members": []}

        result = initialized_library.list_users(user_id="test_user", limit=5)

        assert result["status"] == "success"
        mock_list.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            limit=5,
        )

    def test_list_users_no_credential(self, initialized_library):
        result = initialized_library.list_users(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.list_users")
    def test_list_users_api_error(self, mock_list, initialized_library):
        mock_list.return_value = {
            "error": "invalid_auth",
            "details": {"ok": False, "error": "invalid_auth"},
        }

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.list_users")
    def test_list_users_exception(self, mock_list, initialized_library):
        mock_list.side_effect = Exception("Connection refused")

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.list_users")
    def test_list_users_empty(self, mock_list, initialized_library):
        mock_list.return_value = {"ok": True, "members": []}

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "success"
        assert result["users"] == []


# ---------------------------------------------------------------------------
# Get User Info Tests
# ---------------------------------------------------------------------------

class TestGetUserInfo:

    @patch("core.external_libraries.slack.external_app_library.get_user_info")
    def test_get_user_info_success(self, mock_info, initialized_library):
        mock_info.return_value = {
            "ok": True,
            "user": {
                "id": "U001",
                "name": "alice",
                "real_name": "Alice Smith",
                "profile": {"email": "alice@example.com"},
            },
        }

        result = initialized_library.get_user_info(
            user_id="test_user",
            slack_user_id="U001",
        )

        assert result["status"] == "success"
        assert result["user"]["name"] == "alice"
        assert result["user"]["profile"]["email"] == "alice@example.com"
        mock_info.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            user_id="U001",
        )

    def test_get_user_info_no_credential(self, initialized_library):
        result = initialized_library.get_user_info(
            user_id="nonexistent",
            slack_user_id="U001",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.get_user_info")
    def test_get_user_info_api_error(self, mock_info, initialized_library):
        mock_info.return_value = {
            "error": "user_not_found",
            "details": {"ok": False, "error": "user_not_found"},
        }

        result = initialized_library.get_user_info(
            user_id="test_user",
            slack_user_id="INVALID",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.get_user_info")
    def test_get_user_info_exception(self, mock_info, initialized_library):
        mock_info.side_effect = Exception("API unreachable")

        result = initialized_library.get_user_info(
            user_id="test_user",
            slack_user_id="U001",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.get_user_info")
    def test_get_user_info_with_workspace_id(self, mock_info, initialized_library):
        mock_info.return_value = {
            "ok": True,
            "user": {"id": "U001", "name": "alice"},
        }

        result = initialized_library.get_user_info(
            user_id="test_user",
            slack_user_id="U001",
            workspace_id="W123",
        )

        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Get Channel History Tests
# ---------------------------------------------------------------------------

class TestGetChannelHistory:

    @patch("core.external_libraries.slack.external_app_library.get_channel_history")
    def test_get_channel_history_success(self, mock_history, initialized_library):
        mock_history.return_value = {
            "ok": True,
            "messages": [
                {"type": "message", "text": "Hello!", "user": "U001", "ts": "1234567890.111"},
                {"type": "message", "text": "Hi there!", "user": "U002", "ts": "1234567890.222"},
            ],
            "has_more": False,
        }

        result = initialized_library.get_channel_history(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "success"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["text"] == "Hello!"
        mock_history.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            limit=100,
        )

    @patch("core.external_libraries.slack.external_app_library.get_channel_history")
    def test_get_channel_history_custom_limit(self, mock_history, initialized_library):
        mock_history.return_value = {"ok": True, "messages": []}

        result = initialized_library.get_channel_history(
            user_id="test_user",
            channel="C123",
            limit=10,
        )

        assert result["status"] == "success"
        mock_history.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            limit=10,
        )

    def test_get_channel_history_no_credential(self, initialized_library):
        result = initialized_library.get_channel_history(
            user_id="nonexistent",
            channel="C123",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.get_channel_history")
    def test_get_channel_history_api_error(self, mock_history, initialized_library):
        mock_history.return_value = {
            "error": "channel_not_found",
            "details": {"ok": False, "error": "channel_not_found"},
        }

        result = initialized_library.get_channel_history(
            user_id="test_user",
            channel="INVALID",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.get_channel_history")
    def test_get_channel_history_exception(self, mock_history, initialized_library):
        mock_history.side_effect = Exception("Timeout")

        result = initialized_library.get_channel_history(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.get_channel_history")
    def test_get_channel_history_empty(self, mock_history, initialized_library):
        mock_history.return_value = {"ok": True, "messages": []}

        result = initialized_library.get_channel_history(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "success"
        assert result["messages"] == []


# ---------------------------------------------------------------------------
# Get Channel Info Tests
# ---------------------------------------------------------------------------

class TestGetChannelInfo:

    @patch("core.external_libraries.slack.external_app_library.get_channel_info")
    def test_get_channel_info_success(self, mock_info, initialized_library):
        mock_info.return_value = {
            "ok": True,
            "channel": {
                "id": "C123",
                "name": "general",
                "topic": {"value": "Company-wide announcements"},
                "num_members": 42,
            },
        }

        result = initialized_library.get_channel_info(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "success"
        assert result["channel"]["name"] == "general"
        assert result["channel"]["num_members"] == 42
        mock_info.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
        )

    def test_get_channel_info_no_credential(self, initialized_library):
        result = initialized_library.get_channel_info(
            user_id="nonexistent",
            channel="C123",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.get_channel_info")
    def test_get_channel_info_api_error(self, mock_info, initialized_library):
        mock_info.return_value = {
            "error": "channel_not_found",
            "details": {"ok": False, "error": "channel_not_found"},
        }

        result = initialized_library.get_channel_info(
            user_id="test_user",
            channel="INVALID",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.get_channel_info")
    def test_get_channel_info_exception(self, mock_info, initialized_library):
        mock_info.side_effect = Exception("Connection reset")

        result = initialized_library.get_channel_info(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.get_channel_info")
    def test_get_channel_info_with_workspace_id(self, mock_info, initialized_library):
        mock_info.return_value = {
            "ok": True,
            "channel": {"id": "C123", "name": "general"},
        }

        result = initialized_library.get_channel_info(
            user_id="test_user",
            channel="C123",
            workspace_id="W123",
        )

        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Create Channel Tests
# ---------------------------------------------------------------------------

class TestCreateChannel:

    @patch("core.external_libraries.slack.external_app_library.create_channel")
    def test_create_channel_success(self, mock_create, initialized_library):
        mock_create.return_value = {
            "ok": True,
            "channel": {
                "id": "C999",
                "name": "new-project",
                "is_channel": True,
                "is_private": False,
            },
        }

        result = initialized_library.create_channel(
            user_id="test_user",
            name="new-project",
        )

        assert result["status"] == "success"
        assert result["channel"]["name"] == "new-project"
        assert result["channel"]["is_private"] is False
        mock_create.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            name="new-project",
            is_private=False,
        )

    @patch("core.external_libraries.slack.external_app_library.create_channel")
    def test_create_private_channel(self, mock_create, initialized_library):
        mock_create.return_value = {
            "ok": True,
            "channel": {
                "id": "G999",
                "name": "secret-project",
                "is_private": True,
            },
        }

        result = initialized_library.create_channel(
            user_id="test_user",
            name="secret-project",
            is_private=True,
        )

        assert result["status"] == "success"
        assert result["channel"]["is_private"] is True
        mock_create.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            name="secret-project",
            is_private=True,
        )

    def test_create_channel_no_credential(self, initialized_library):
        result = initialized_library.create_channel(
            user_id="nonexistent",
            name="new-channel",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.create_channel")
    def test_create_channel_api_error(self, mock_create, initialized_library):
        mock_create.return_value = {
            "error": "name_taken",
            "details": {"ok": False, "error": "name_taken"},
        }

        result = initialized_library.create_channel(
            user_id="test_user",
            name="general",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.create_channel")
    def test_create_channel_exception(self, mock_create, initialized_library):
        mock_create.side_effect = Exception("Server error")

        result = initialized_library.create_channel(
            user_id="test_user",
            name="new-channel",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# Invite to Channel Tests
# ---------------------------------------------------------------------------

class TestInviteToChannel:

    @patch("core.external_libraries.slack.external_app_library.invite_to_channel")
    def test_invite_to_channel_success(self, mock_invite, initialized_library):
        mock_invite.return_value = {
            "ok": True,
            "channel": {"id": "C123", "name": "general"},
        }

        result = initialized_library.invite_to_channel(
            user_id="test_user",
            channel="C123",
            users=["U001", "U002"],
        )

        assert result["status"] == "success"
        assert result["channel"]["id"] == "C123"
        mock_invite.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            users=["U001", "U002"],
        )

    @patch("core.external_libraries.slack.external_app_library.invite_to_channel")
    def test_invite_single_user(self, mock_invite, initialized_library):
        mock_invite.return_value = {
            "ok": True,
            "channel": {"id": "C123", "name": "general"},
        }

        result = initialized_library.invite_to_channel(
            user_id="test_user",
            channel="C123",
            users=["U001"],
        )

        assert result["status"] == "success"
        mock_invite.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            users=["U001"],
        )

    def test_invite_to_channel_no_credential(self, initialized_library):
        result = initialized_library.invite_to_channel(
            user_id="nonexistent",
            channel="C123",
            users=["U001"],
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.invite_to_channel")
    def test_invite_to_channel_api_error(self, mock_invite, initialized_library):
        mock_invite.return_value = {
            "error": "already_in_channel",
            "details": {"ok": False, "error": "already_in_channel"},
        }

        result = initialized_library.invite_to_channel(
            user_id="test_user",
            channel="C123",
            users=["U001"],
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.invite_to_channel")
    def test_invite_to_channel_exception(self, mock_invite, initialized_library):
        mock_invite.side_effect = Exception("Network failure")

        result = initialized_library.invite_to_channel(
            user_id="test_user",
            channel="C123",
            users=["U001"],
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# Upload File Tests
# ---------------------------------------------------------------------------

class TestUploadFile:

    @patch("core.external_libraries.slack.external_app_library.upload_file")
    def test_upload_file_with_content_success(self, mock_upload, initialized_library):
        mock_upload.return_value = {
            "ok": True,
            "file": {
                "id": "F123",
                "name": "report.txt",
                "title": "Daily Report",
                "size": 1024,
            },
        }

        result = initialized_library.upload_file(
            user_id="test_user",
            channels=["C123"],
            content="Report content here",
            filename="report.txt",
            title="Daily Report",
        )

        assert result["status"] == "success"
        assert result["file"]["name"] == "report.txt"
        mock_upload.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channels=["C123"],
            content="Report content here",
            file_path=None,
            filename="report.txt",
            title="Daily Report",
            initial_comment=None,
        )

    @patch("core.external_libraries.slack.external_app_library.upload_file")
    def test_upload_file_with_path_success(self, mock_upload, initialized_library):
        mock_upload.return_value = {
            "ok": True,
            "file": {"id": "F456", "name": "image.png"},
        }

        result = initialized_library.upload_file(
            user_id="test_user",
            channels=["C123", "C456"],
            file_path="/path/to/image.png",
            filename="image.png",
            initial_comment="Check this out!",
        )

        assert result["status"] == "success"
        mock_upload.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channels=["C123", "C456"],
            content=None,
            file_path="/path/to/image.png",
            filename="image.png",
            title=None,
            initial_comment="Check this out!",
        )

    def test_upload_file_no_credential(self, initialized_library):
        result = initialized_library.upload_file(
            user_id="nonexistent",
            channels=["C123"],
            content="Some content",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.upload_file")
    def test_upload_file_api_error(self, mock_upload, initialized_library):
        mock_upload.return_value = {
            "error": "not_allowed_token_type",
            "details": {"ok": False, "error": "not_allowed_token_type"},
        }

        result = initialized_library.upload_file(
            user_id="test_user",
            channels=["C123"],
            content="Some content",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.upload_file")
    def test_upload_file_exception(self, mock_upload, initialized_library):
        mock_upload.side_effect = Exception("File not found")

        result = initialized_library.upload_file(
            user_id="test_user",
            channels=["C123"],
            file_path="/nonexistent/file.txt",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.upload_file")
    def test_upload_file_multiple_channels(self, mock_upload, initialized_library):
        mock_upload.return_value = {
            "ok": True,
            "file": {"id": "F789", "name": "doc.pdf"},
        }

        result = initialized_library.upload_file(
            user_id="test_user",
            channels=["C001", "C002", "C003"],
            content="multi-channel content",
        )

        assert result["status"] == "success"
        call_args = mock_upload.call_args
        assert call_args.kwargs["channels"] == ["C001", "C002", "C003"]


# ---------------------------------------------------------------------------
# Search Messages Tests
# ---------------------------------------------------------------------------

class TestSearchMessages:

    @patch("core.external_libraries.slack.external_app_library.search_messages")
    def test_search_messages_success(self, mock_search, initialized_library):
        mock_search.return_value = {
            "ok": True,
            "messages": {
                "total": 2,
                "matches": [
                    {"text": "Hello world", "channel": {"name": "general"}, "ts": "123.456"},
                    {"text": "Hello there", "channel": {"name": "random"}, "ts": "123.789"},
                ],
            },
        }

        result = initialized_library.search_messages(
            user_id="test_user",
            query="Hello",
        )

        assert result["status"] == "success"
        assert result["messages"]["total"] == 2
        assert len(result["messages"]["matches"]) == 2
        mock_search.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            query="Hello",
            count=20,
        )

    @patch("core.external_libraries.slack.external_app_library.search_messages")
    def test_search_messages_custom_count(self, mock_search, initialized_library):
        mock_search.return_value = {"ok": True, "messages": {"total": 0, "matches": []}}

        result = initialized_library.search_messages(
            user_id="test_user",
            query="test query",
            count=5,
        )

        assert result["status"] == "success"
        mock_search.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            query="test query",
            count=5,
        )

    def test_search_messages_no_credential(self, initialized_library):
        result = initialized_library.search_messages(
            user_id="nonexistent",
            query="Hello",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.search_messages")
    def test_search_messages_api_error(self, mock_search, initialized_library):
        mock_search.return_value = {
            "error": "not_allowed_token_type",
            "details": {"ok": False, "error": "not_allowed_token_type"},
        }

        result = initialized_library.search_messages(
            user_id="test_user",
            query="Hello",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.search_messages")
    def test_search_messages_exception(self, mock_search, initialized_library):
        mock_search.side_effect = Exception("Search API down")

        result = initialized_library.search_messages(
            user_id="test_user",
            query="Hello",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.search_messages")
    def test_search_messages_empty_results(self, mock_search, initialized_library):
        mock_search.return_value = {"ok": True, "messages": {"total": 0, "matches": []}}

        result = initialized_library.search_messages(
            user_id="test_user",
            query="nonexistent phrase xyz",
        )

        assert result["status"] == "success"
        assert result["messages"]["total"] == 0

    @patch("core.external_libraries.slack.external_app_library.search_messages")
    def test_search_messages_no_messages_key(self, mock_search, initialized_library):
        """When the API returns ok but without a messages key, the result should use the default."""
        mock_search.return_value = {"ok": True}

        result = initialized_library.search_messages(
            user_id="test_user",
            query="test",
        )

        assert result["status"] == "success"
        assert result["messages"] == {}


# ---------------------------------------------------------------------------
# Open DM Tests
# ---------------------------------------------------------------------------

class TestOpenDM:

    @patch("core.external_libraries.slack.external_app_library.open_dm")
    def test_open_dm_success(self, mock_open, initialized_library):
        mock_open.return_value = {
            "ok": True,
            "channel": {
                "id": "D123",
                "is_im": True,
            },
        }

        result = initialized_library.open_dm(
            user_id="test_user",
            users=["U001"],
        )

        assert result["status"] == "success"
        assert result["channel"]["id"] == "D123"
        assert result["channel"]["is_im"] is True
        mock_open.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            users=["U001"],
        )

    @patch("core.external_libraries.slack.external_app_library.open_dm")
    def test_open_group_dm_success(self, mock_open, initialized_library):
        mock_open.return_value = {
            "ok": True,
            "channel": {
                "id": "G123",
                "is_mpim": True,
            },
        }

        result = initialized_library.open_dm(
            user_id="test_user",
            users=["U001", "U002", "U003"],
        )

        assert result["status"] == "success"
        assert result["channel"]["is_mpim"] is True
        mock_open.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            users=["U001", "U002", "U003"],
        )

    def test_open_dm_no_credential(self, initialized_library):
        result = initialized_library.open_dm(
            user_id="nonexistent",
            users=["U001"],
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.open_dm")
    def test_open_dm_api_error(self, mock_open, initialized_library):
        mock_open.return_value = {
            "error": "user_not_found",
            "details": {"ok": False, "error": "user_not_found"},
        }

        result = initialized_library.open_dm(
            user_id="test_user",
            users=["INVALID"],
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.slack.external_app_library.open_dm")
    def test_open_dm_exception(self, mock_open, initialized_library):
        mock_open.side_effect = Exception("Connection error")

        result = initialized_library.open_dm(
            user_id="test_user",
            users=["U001"],
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.open_dm")
    def test_open_dm_with_workspace_id(self, mock_open, initialized_library):
        mock_open.return_value = {
            "ok": True,
            "channel": {"id": "D123"},
        }

        result = initialized_library.open_dm(
            user_id="test_user",
            users=["U001"],
            workspace_id="W123",
        )

        assert result["status"] == "success"

    def test_open_dm_wrong_workspace_id(self, initialized_library):
        result = initialized_library.open_dm(
            user_id="test_user",
            users=["U001"],
            workspace_id="WRONG_WS",
        )
        assert result["status"] == "error"
        assert "No valid Slack credential" in result["reason"]


# ---------------------------------------------------------------------------
# Credential Model Tests
# ---------------------------------------------------------------------------

class TestSlackCredential:

    def test_credential_required_fields(self):
        cred = SlackCredential(
            user_id="u1",
            workspace_id="W1",
            workspace_name="My Workspace",
            bot_token="xoxb-token",
            team_id="T1",
        )
        assert cred.user_id == "u1"
        assert cred.workspace_id == "W1"
        assert cred.workspace_name == "My Workspace"
        assert cred.bot_token == "xoxb-token"
        assert cred.team_id == "T1"
        assert cred.app_id == ""

    def test_credential_with_all_fields(self):
        cred = SlackCredential(
            user_id="u1",
            workspace_id="W1",
            workspace_name="My Workspace",
            bot_token="xoxb-token",
            team_id="T1",
            app_id="A999",
        )
        assert cred.app_id == "A999"

    def test_credential_unique_keys(self):
        assert SlackCredential.UNIQUE_KEYS == ("user_id", "workspace_id")

    def test_credential_to_dict(self):
        cred = SlackCredential(
            user_id="u1",
            workspace_id="W1",
            workspace_name="Test WS",
            bot_token="xoxb-abc",
            team_id="T1",
            app_id="A1",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["workspace_id"] == "W1"
        assert d["workspace_name"] == "Test WS"
        assert d["bot_token"] == "xoxb-abc"
        assert d["team_id"] == "T1"
        assert d["app_id"] == "A1"

    def test_credential_to_dict_default_app_id(self):
        cred = SlackCredential(
            user_id="u1",
            workspace_id="W1",
            workspace_name="WS",
            bot_token="xoxb-x",
            team_id="T1",
        )
        d = cred.to_dict()
        assert d["app_id"] == ""


# ---------------------------------------------------------------------------
# Edge Cases & Error Handling Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_empty_text(self, mock_send, initialized_library):
        """Sending an empty text string should still call the helper."""
        mock_send.return_value = {"ok": True, "channel": "C123", "ts": "123.456"}

        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text="",
        )

        assert result["status"] == "success"
        mock_send.assert_called_once()

    @patch("core.external_libraries.slack.external_app_library.list_channels")
    def test_list_channels_missing_channels_key(self, mock_list, initialized_library):
        """When API returns ok but no channels key, defaults to empty list."""
        mock_list.return_value = {"ok": True}

        result = initialized_library.list_channels(user_id="test_user")

        assert result["status"] == "success"
        assert result["channels"] == []

    @patch("core.external_libraries.slack.external_app_library.list_users")
    def test_list_users_missing_members_key(self, mock_list, initialized_library):
        """When API returns ok but no members key, defaults to empty list."""
        mock_list.return_value = {"ok": True}

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "success"
        assert result["users"] == []

    @patch("core.external_libraries.slack.external_app_library.get_channel_history")
    def test_channel_history_missing_messages_key(self, mock_history, initialized_library):
        """When API returns ok but no messages key, defaults to empty list."""
        mock_history.return_value = {"ok": True}

        result = initialized_library.get_channel_history(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "success"
        assert result["messages"] == []

    @patch("core.external_libraries.slack.external_app_library.get_user_info")
    def test_get_user_info_missing_user_key(self, mock_info, initialized_library):
        """When API returns ok but no user key, channel should be None."""
        mock_info.return_value = {"ok": True}

        result = initialized_library.get_user_info(
            user_id="test_user",
            slack_user_id="U001",
        )

        assert result["status"] == "success"
        assert result["user"] is None

    @patch("core.external_libraries.slack.external_app_library.get_channel_info")
    def test_get_channel_info_missing_channel_key(self, mock_info, initialized_library):
        """When API returns ok but no channel key, result should be None."""
        mock_info.return_value = {"ok": True}

        result = initialized_library.get_channel_info(
            user_id="test_user",
            channel="C123",
        )

        assert result["status"] == "success"
        assert result["channel"] is None

    @patch("core.external_libraries.slack.external_app_library.create_channel")
    def test_create_channel_missing_channel_key(self, mock_create, initialized_library):
        """When API returns ok but no channel key, result should be None."""
        mock_create.return_value = {"ok": True}

        result = initialized_library.create_channel(
            user_id="test_user",
            name="test",
        )

        assert result["status"] == "success"
        assert result["channel"] is None

    @patch("core.external_libraries.slack.external_app_library.invite_to_channel")
    def test_invite_to_channel_missing_channel_key(self, mock_invite, initialized_library):
        """When API returns ok but no channel key, result should be None."""
        mock_invite.return_value = {"ok": True}

        result = initialized_library.invite_to_channel(
            user_id="test_user",
            channel="C123",
            users=["U001"],
        )

        assert result["status"] == "success"
        assert result["channel"] is None

    @patch("core.external_libraries.slack.external_app_library.upload_file")
    def test_upload_file_missing_file_key(self, mock_upload, initialized_library):
        """When API returns ok but no file key, result should be None."""
        mock_upload.return_value = {"ok": True}

        result = initialized_library.upload_file(
            user_id="test_user",
            channels=["C123"],
            content="data",
        )

        assert result["status"] == "success"
        assert result["file"] is None

    @patch("core.external_libraries.slack.external_app_library.open_dm")
    def test_open_dm_missing_channel_key(self, mock_open, initialized_library):
        """When API returns ok but no channel key, result should be None."""
        mock_open.return_value = {"ok": True}

        result = initialized_library.open_dm(
            user_id="test_user",
            users=["U001"],
        )

        assert result["status"] == "success"
        assert result["channel"] is None

    def test_multiple_credentials_same_user_different_workspaces(self, initialized_library):
        """User can have credentials for multiple workspaces."""
        second_cred = SlackCredential(
            user_id="test_user",
            workspace_id="W999",
            workspace_name="Other Workspace",
            bot_token="xoxb-other-token",
            team_id="T999",
        )
        initialized_library.get_credential_store().add(second_cred)

        cred1 = initialized_library.get_credentials(
            user_id="test_user", workspace_id="W123"
        )
        cred2 = initialized_library.get_credentials(
            user_id="test_user", workspace_id="W999"
        )

        assert cred1 is not None
        assert cred1.bot_token == "xoxb-test-token-123"
        assert cred2 is not None
        assert cred2.bot_token == "xoxb-other-token"

    def test_get_credentials_returns_first_when_no_workspace(self, initialized_library):
        """Without workspace_id filter, get_credentials returns the first credential."""
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.bot_token == "xoxb-test-token-123"

    def test_not_initialized_send_message_returns_error(self):
        """Calling send_message before initialize returns an error dict
        because the RuntimeError from get_credential_store is caught
        by the method's try/except."""
        result = SlackAppLibrary.send_message(
            user_id="test_user",
            channel="C123",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_not_initialized_list_channels_returns_error(self):
        """Calling list_channels before initialize returns an error dict."""
        result = SlackAppLibrary.list_channels(user_id="test_user")
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    @patch("core.external_libraries.slack.external_app_library.send_message")
    def test_send_message_special_characters(self, mock_send, initialized_library):
        """Messages with special characters should be passed through unchanged."""
        mock_send.return_value = {"ok": True, "channel": "C123", "ts": "123.456"}

        special_text = "Hello <@U001>! Here's a link: https://example.com & some *bold* text"
        result = initialized_library.send_message(
            user_id="test_user",
            channel="C123",
            text=special_text,
        )

        assert result["status"] == "success"
        mock_send.assert_called_once_with(
            bot_token="xoxb-test-token-123",
            channel="C123",
            text=special_text,
            thread_ts=None,
        )
