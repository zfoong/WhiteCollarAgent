"""
Tests for WhatsApp external library (WhatsApp Web only).

Uses pytest with unittest.mock to mock the async WhatsApp Web helper functions,
allowing all library methods to be tested without a live WhatsApp Web session.

Usage:
    pytest core/external_libraries/whatsapp/tests/test_whatsapp_library.py -v
"""
import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.whatsapp.credentials import WhatsAppCredential
from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset WhatsAppAppLibrary state before each test."""
    WhatsAppAppLibrary._initialized = False
    WhatsAppAppLibrary._credential_store = None
    yield
    WhatsAppAppLibrary._initialized = False
    WhatsAppAppLibrary._credential_store = None


@pytest.fixture
def mock_credential():
    """Return a sample WhatsApp Web credential."""
    return WhatsAppCredential(
        user_id="test_user",
        phone_number_id="session_abc123",
        session_id="session_abc123",
        jid="1234567890@s.whatsapp.net",
        display_phone_number="+1234567890",
    )


@pytest.fixture
def initialized_library(mock_credential):
    """Initialize the library and inject a mock credential store."""
    WhatsAppAppLibrary.initialize()
    WhatsAppAppLibrary.get_credential_store().add(mock_credential)
    return WhatsAppAppLibrary


# ---------------------------------------------------------------------------
# Initialization & Credential Tests
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_initialize(self):
        assert not WhatsAppAppLibrary._initialized
        WhatsAppAppLibrary.initialize()
        assert WhatsAppAppLibrary._initialized
        assert WhatsAppAppLibrary._credential_store is not None

    def test_initialize_idempotent(self):
        WhatsAppAppLibrary.initialize()
        store = WhatsAppAppLibrary._credential_store
        WhatsAppAppLibrary.initialize()
        assert WhatsAppAppLibrary._credential_store is store

    def test_get_name(self):
        assert WhatsAppAppLibrary.get_name() == "WhatsApp"

    def test_get_credential_store_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            WhatsAppAppLibrary.get_credential_store()

    def test_get_credential_store_after_init(self):
        WhatsAppAppLibrary.initialize()
        store = WhatsAppAppLibrary.get_credential_store()
        assert store is not None


class TestValidateConnection:

    def test_validate_no_credentials(self):
        WhatsAppAppLibrary.initialize()
        assert WhatsAppAppLibrary.validate_connection(user_id="nonexistent") is False

    def test_validate_with_credentials(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(user_id="test_user") is True

    def test_validate_with_wrong_user(self, initialized_library):
        assert initialized_library.validate_connection(user_id="other_user") is False

    def test_validate_with_phone_number_id(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(
            user_id="test_user",
            phone_number_id="session_abc123"
        ) is True

    def test_validate_with_wrong_phone_number_id(self, initialized_library):
        assert initialized_library.validate_connection(
            user_id="test_user",
            phone_number_id="wrong_id"
        ) is False


class TestGetCredentials:

    def test_get_credentials_found(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.user_id == "test_user"
        assert cred.session_id == "session_abc123"

    def test_get_credentials_not_found(self, initialized_library):
        cred = initialized_library.get_credentials(user_id="nonexistent")
        assert cred is None

    def test_get_credentials_with_phone_number_id(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            phone_number_id="session_abc123"
        )
        assert cred is not None
        assert cred.phone_number_id == "session_abc123"


# ---------------------------------------------------------------------------
# Send Text Message Tests
# ---------------------------------------------------------------------------

class TestSendTextMessage:

    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_message",
           new_callable=AsyncMock)
    def test_send_text_success(self, mock_send, initialized_library):
        mock_send.return_value = {"success": True, "timestamp": "2026-01-01T00:00:00"}

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="9876543210",
            message="Hello!"
        )

        assert result["status"] == "success"
        assert result["to"] == "9876543210"
        assert result["via"] == "whatsapp_web"
        mock_send.assert_awaited_once()

    def test_send_text_no_credential(self, initialized_library):
        result = initialized_library.send_text_message(
            user_id="nonexistent",
            to="9876543210",
            message="Hello!"
        )
        assert result["status"] == "error"
        assert "No valid WhatsApp credential" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_message",
           new_callable=AsyncMock)
    def test_send_text_failure(self, mock_send, initialized_library):
        mock_send.return_value = {"success": False, "error": "Send failed"}

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="9876543210",
            message="Hello!"
        )

        assert result["status"] == "error"
        assert "Send failed" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_message",
           new_callable=AsyncMock)
    def test_send_text_resolves_contact_name(self, mock_send, mock_resolve, initialized_library):
        mock_resolve.return_value = {"success": True, "name": "John", "phone": "+1234567890"}
        mock_send.return_value = {"success": True, "timestamp": "2026-01-01T00:00:00"}

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="John",
            message="Hello!"
        )

        assert result["status"] == "success"
        mock_resolve.assert_awaited_once()
        mock_send.assert_awaited_once()

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    def test_send_text_contact_resolution_fails(self, mock_resolve, initialized_library):
        mock_resolve.return_value = {"success": False, "error": "Contact not found"}

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="UnknownPerson",
            message="Hello!"
        )

        assert result["status"] == "error"
        assert "Could not resolve contact" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_message",
           new_callable=AsyncMock)
    def test_send_text_auto_reconnect_success(self, mock_send, mock_reconnect, initialized_library):
        mock_send.side_effect = [
            {"success": False, "error": "Session not connected"},
            {"success": True, "timestamp": "2026-01-01T00:00:00"},
        ]
        mock_reconnect.return_value = {"success": True, "status": "connected"}

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="9876543210",
            message="Hello!"
        )

        assert result["status"] == "success"
        assert mock_send.await_count == 2
        mock_reconnect.assert_awaited_once()

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_message",
           new_callable=AsyncMock)
    def test_send_text_auto_reconnect_qr_required(self, mock_send, mock_reconnect, initialized_library):
        mock_send.return_value = {"success": False, "error": "Session not connected"}
        mock_reconnect.return_value = {"success": False, "status": "qr_required"}

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="9876543210",
            message="Hello!"
        )

        assert result["status"] == "error"
        assert "session expired" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Send Media Message Tests
# ---------------------------------------------------------------------------

class TestSendMediaMessage:

    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_media",
           new_callable=AsyncMock)
    def test_send_media_success(self, mock_send, initialized_library):
        mock_send.return_value = {"success": True, "timestamp": "2026-01-01T00:00:00"}

        result = initialized_library.send_media_message(
            user_id="test_user",
            to="9876543210",
            media_type="image",
            media_url="/path/to/image.jpg",
            caption="A photo"
        )

        assert result["status"] == "success"
        assert result["media_type"] == "image"
        assert result["via"] == "whatsapp_web"

    def test_send_media_no_credential(self, initialized_library):
        result = initialized_library.send_media_message(
            user_id="nonexistent",
            to="9876543210",
            media_type="image",
            media_url="/path/to/image.jpg"
        )
        assert result["status"] == "error"
        assert "No valid WhatsApp credential" in result["reason"]

    def test_send_media_no_url(self, initialized_library):
        result = initialized_library.send_media_message(
            user_id="test_user",
            to="9876543210",
            media_type="image",
        )
        assert result["status"] == "error"
        assert "requires media_url" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_media",
           new_callable=AsyncMock)
    def test_send_media_failure(self, mock_send, initialized_library):
        mock_send.return_value = {"success": False, "error": "Could not find chat"}

        result = initialized_library.send_media_message(
            user_id="test_user",
            to="9876543210",
            media_type="image",
            media_url="/path/to/image.jpg"
        )

        assert result["status"] == "error"
        assert "Could not find chat" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_media",
           new_callable=AsyncMock)
    def test_send_media_resolves_contact_name(self, mock_send, mock_resolve, initialized_library):
        mock_resolve.return_value = {"success": True, "name": "Jane", "phone": "+1234567890"}
        mock_send.return_value = {"success": True, "timestamp": "2026-01-01T00:00:00"}

        result = initialized_library.send_media_message(
            user_id="test_user",
            to="Jane",
            media_type="document",
            media_url="/path/to/doc.pdf"
        )

        assert result["status"] == "success"
        mock_resolve.assert_awaited_once()

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_media",
           new_callable=AsyncMock)
    def test_send_media_auto_reconnect(self, mock_send, mock_reconnect, initialized_library):
        mock_send.side_effect = [
            {"success": False, "error": "Session not connected"},
            {"success": True, "timestamp": "2026-01-01T00:00:00"},
        ]
        mock_reconnect.return_value = {"success": True, "status": "connected"}

        result = initialized_library.send_media_message(
            user_id="test_user",
            to="9876543210",
            media_type="video",
            media_url="/path/to/video.mp4"
        )

        assert result["status"] == "success"
        assert mock_send.await_count == 2
        mock_reconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Get Chat History Tests
# ---------------------------------------------------------------------------

class TestGetChatHistory:

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_chat_messages",
           new_callable=AsyncMock)
    def test_get_chat_history_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "success": True,
            "messages": [
                {"text": "Hello", "is_outgoing": True, "timestamp": "[10:30, 01/01/2026]", "sender": "me"},
                {"text": "Hi!", "is_outgoing": False, "timestamp": "[10:31, 01/01/2026]", "sender": "them"},
            ],
            "count": 2,
        }

        result = initialized_library.get_chat_history(
            user_id="test_user",
            phone_number="9876543210",
            limit=10
        )

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["messages"]) == 2
        assert result["via"] == "whatsapp_web"

    def test_get_chat_history_no_credential(self, initialized_library):
        result = initialized_library.get_chat_history(
            user_id="nonexistent",
            phone_number="9876543210"
        )
        assert result["status"] == "error"

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_chat_messages",
           new_callable=AsyncMock)
    def test_get_chat_history_failure(self, mock_get, initialized_library):
        mock_get.return_value = {"success": False, "error": "Chat not found"}

        result = initialized_library.get_chat_history(
            user_id="test_user",
            phone_number="0000000000"
        )

        assert result["status"] == "error"
        assert "Chat not found" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_chat_messages",
           new_callable=AsyncMock)
    def test_get_chat_history_auto_reconnect(self, mock_get, mock_reconnect, initialized_library):
        mock_get.side_effect = [
            {"success": False, "error": "Session not connected"},
            {"success": True, "messages": [], "count": 0},
        ]
        mock_reconnect.return_value = {"success": True, "status": "connected"}

        result = initialized_library.get_chat_history(
            user_id="test_user",
            phone_number="9876543210"
        )

        assert result["status"] == "success"
        mock_reconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Get Unread Chats Tests
# ---------------------------------------------------------------------------

class TestGetUnreadChats:

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_unread_chats",
           new_callable=AsyncMock)
    def test_get_unread_chats_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "success": True,
            "unread_chats": [
                {"name": "Alice", "unread_count": "3"},
                {"name": "Bob", "unread_count": "1"},
            ],
            "count": 2,
        }

        result = initialized_library.get_unread_chats(user_id="test_user")

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["unread_chats"]) == 2
        assert result["via"] == "whatsapp_web"

    def test_get_unread_chats_no_credential(self, initialized_library):
        result = initialized_library.get_unread_chats(user_id="nonexistent")
        assert result["status"] == "error"

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_unread_chats",
           new_callable=AsyncMock)
    def test_get_unread_chats_auto_reconnect(self, mock_get, mock_reconnect, initialized_library):
        mock_get.side_effect = [
            {"success": False, "error": "Session not connected"},
            {"success": True, "unread_chats": [], "count": 0},
        ]
        mock_reconnect.return_value = {"success": True, "status": "connected"}

        result = initialized_library.get_unread_chats(user_id="test_user")

        assert result["status"] == "success"
        mock_reconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Search Contact Tests
# ---------------------------------------------------------------------------

class TestSearchContact:

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    def test_search_contact_success(self, mock_search, initialized_library):
        mock_search.return_value = {"success": True, "name": "John Doe", "phone": "+1234567890"}

        result = initialized_library.search_contact(
            user_id="test_user",
            name="John"
        )

        assert result["status"] == "success"
        assert result["contact"]["name"] == "John Doe"
        assert result["contact"]["phone"] == "+1234567890"
        assert result["via"] == "whatsapp_web"

    def test_search_contact_no_credential(self, initialized_library):
        result = initialized_library.search_contact(
            user_id="nonexistent",
            name="John"
        )
        assert result["status"] == "error"

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    def test_search_contact_not_found(self, mock_search, initialized_library):
        mock_search.return_value = {"success": False, "error": "Contact not found"}

        result = initialized_library.search_contact(
            user_id="test_user",
            name="UnknownPerson"
        )

        assert result["status"] == "error"
        assert "Contact not found" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    def test_search_contact_returns_debug_info(self, mock_search, initialized_library):
        mock_search.return_value = {
            "success": False,
            "error": "Could not resolve",
            "debug": {"panel_text_preview": "some debug data"}
        }

        result = initialized_library.search_contact(
            user_id="test_user",
            name="Ambiguous"
        )

        assert result["status"] == "error"
        assert "debug" in result
        assert result["debug"]["panel_text_preview"] == "some debug data"

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    def test_search_contact_auto_reconnect(self, mock_search, mock_reconnect, initialized_library):
        mock_search.side_effect = [
            {"success": False, "error": "Session not connected"},
            {"success": True, "name": "John", "phone": "+1234567890"},
        ]
        mock_reconnect.return_value = {"success": True, "status": "connected"}

        result = initialized_library.search_contact(
            user_id="test_user",
            name="John"
        )

        assert result["status"] == "success"
        mock_reconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Session Management Tests
# ---------------------------------------------------------------------------

class TestReconnectWhatsAppWeb:

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    def test_reconnect_success(self, mock_reconnect, initialized_library):
        mock_reconnect.return_value = {
            "success": True,
            "status": "connected",
            "session_id": "session_abc123",
        }

        result = initialized_library.reconnect_whatsapp_web(
            user_id="test_user"
        )

        assert result["success"] is True
        assert result["status"] == "connected"

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    def test_reconnect_with_explicit_session_id(self, mock_reconnect, initialized_library):
        mock_reconnect.return_value = {"success": True, "status": "connected"}

        result = initialized_library.reconnect_whatsapp_web(
            user_id="test_user",
            session_id="explicit_session"
        )

        assert result["success"] is True
        mock_reconnect.assert_awaited_once_with(session_id="explicit_session", user_id="test_user")

    def test_reconnect_no_credentials(self):
        WhatsAppAppLibrary.initialize()
        result = WhatsAppAppLibrary.reconnect_whatsapp_web(user_id="nobody")

        assert result["status"] == "error"
        assert "No WhatsApp Web credentials" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    def test_reconnect_qr_required(self, mock_reconnect, initialized_library):
        mock_reconnect.return_value = {
            "success": False,
            "status": "qr_required",
            "error": "Device unlinked",
        }

        result = initialized_library.reconnect_whatsapp_web(user_id="test_user")

        assert result["success"] is False
        assert result["status"] == "qr_required"


class TestListPersistedSessions:

    @patch("core.external_libraries.whatsapp.external_app_library.list_persisted_whatsapp_web_sessions")
    def test_list_all_sessions(self, mock_list, initialized_library):
        mock_list.return_value = [
            {"session_id": "session_abc123", "path": "/data/sessions/abc", "is_active": True},
            {"session_id": "session_other", "path": "/data/sessions/other", "is_active": False},
        ]

        result = initialized_library.list_persisted_sessions()

        assert result["status"] == "success"
        assert result["count"] == 2

    @patch("core.external_libraries.whatsapp.external_app_library.list_persisted_whatsapp_web_sessions")
    def test_list_sessions_filtered_by_user(self, mock_list, initialized_library):
        mock_list.return_value = [
            {"session_id": "session_abc123", "path": "/data/sessions/abc", "is_active": True},
            {"session_id": "session_other", "path": "/data/sessions/other", "is_active": False},
        ]

        result = initialized_library.list_persisted_sessions(user_id="test_user")

        assert result["status"] == "success"
        # Only session_abc123 matches the test_user's credential
        assert result["count"] == 1
        assert result["sessions"][0]["session_id"] == "session_abc123"

    @patch("core.external_libraries.whatsapp.external_app_library.list_persisted_whatsapp_web_sessions")
    def test_list_sessions_no_match(self, mock_list, initialized_library):
        mock_list.return_value = [
            {"session_id": "unrelated_session", "path": "/data/sessions/x", "is_active": False},
        ]

        result = initialized_library.list_persisted_sessions(user_id="test_user")

        assert result["status"] == "success"
        assert result["count"] == 0


class TestGetWebSessionStatus:

    @patch("core.external_libraries.whatsapp.external_app_library.get_session_status",
           new_callable=AsyncMock)
    def test_get_status_with_session_id(self, mock_status, initialized_library):
        mock_status.return_value = {
            "session_id": "session_abc123",
            "user_id": "test_user",
            "status": "connected",
            "phone_number": "+1234567890",
        }

        result = initialized_library.get_web_session_status(
            user_id="test_user",
            session_id="session_abc123"
        )

        assert result["status"] == "connected"
        mock_status.assert_awaited_once_with("session_abc123")

    @patch("core.external_libraries.whatsapp.external_app_library.get_session_status",
           new_callable=AsyncMock)
    def test_get_status_auto_discovers_session(self, mock_status, initialized_library):
        mock_status.return_value = {
            "session_id": "session_abc123",
            "status": "connected",
        }

        result = initialized_library.get_web_session_status(user_id="test_user")

        assert result["status"] == "connected"
        mock_status.assert_awaited_once_with("session_abc123")

    @patch("core.external_libraries.whatsapp.external_app_library.list_persisted_whatsapp_web_sessions")
    def test_get_status_falls_back_to_list(self, mock_list):
        WhatsAppAppLibrary.initialize()
        mock_list.return_value = []

        result = WhatsAppAppLibrary.get_web_session_status(user_id="nobody")

        assert result["status"] == "success"
        assert result["count"] == 0

    @patch("core.external_libraries.whatsapp.external_app_library.get_session_status",
           new_callable=AsyncMock)
    def test_get_status_session_not_found(self, mock_status, initialized_library):
        mock_status.return_value = None

        result = initialized_library.get_web_session_status(
            user_id="test_user",
            session_id="session_abc123"
        )

        assert result["status"] == "error"
        assert "Session not found" in result["message"]


# ---------------------------------------------------------------------------
# Credential Model Tests
# ---------------------------------------------------------------------------

class TestWhatsAppCredential:

    def test_credential_defaults(self):
        cred = WhatsAppCredential(user_id="u1", phone_number_id="p1")
        assert cred.session_id == ""
        assert cred.session_data == ""
        assert cred.jid == ""
        assert cred.display_phone_number == ""

    def test_credential_with_all_fields(self):
        cred = WhatsAppCredential(
            user_id="u1",
            phone_number_id="p1",
            session_id="s1",
            session_data="data",
            jid="123@s.whatsapp.net",
            display_phone_number="+1234567890",
        )
        assert cred.session_id == "s1"
        assert cred.jid == "123@s.whatsapp.net"

    def test_credential_unique_keys(self):
        assert WhatsAppCredential.UNIQUE_KEYS == ("user_id", "phone_number_id")

    def test_credential_to_dict(self):
        cred = WhatsAppCredential(user_id="u1", phone_number_id="p1", session_id="s1")
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["phone_number_id"] == "p1"
        assert d["session_id"] == "s1"


# ---------------------------------------------------------------------------
# Edge Cases & Error Handling Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_message",
           new_callable=AsyncMock)
    def test_send_text_handles_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Network error")

        result = initialized_library.send_text_message(
            user_id="test_user",
            to="9876543210",
            message="Hello!"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.send_whatsapp_web_media",
           new_callable=AsyncMock)
    def test_send_media_handles_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Disk error")

        result = initialized_library.send_media_message(
            user_id="test_user",
            to="9876543210",
            media_type="image",
            media_url="/path/to/img.jpg"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_chat_messages",
           new_callable=AsyncMock)
    def test_get_chat_history_handles_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Timeout")

        result = initialized_library.get_chat_history(
            user_id="test_user",
            phone_number="9876543210"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_unread_chats",
           new_callable=AsyncMock)
    def test_get_unread_chats_handles_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Connection refused")

        result = initialized_library.get_unread_chats(user_id="test_user")

        assert result["status"] == "error"

    @patch("core.external_libraries.whatsapp.external_app_library.get_whatsapp_web_contact_phone",
           new_callable=AsyncMock)
    def test_search_contact_handles_exception(self, mock_search, initialized_library):
        mock_search.side_effect = Exception("Browser crashed")

        result = initialized_library.search_contact(
            user_id="test_user",
            name="Someone"
        )

        assert result["status"] == "error"

    @patch("core.external_libraries.whatsapp.external_app_library.reconnect_whatsapp_web_session",
           new_callable=AsyncMock)
    def test_reconnect_handles_exception(self, mock_reconnect, initialized_library):
        mock_reconnect.side_effect = Exception("Playwright error")

        result = initialized_library.reconnect_whatsapp_web(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.whatsapp.external_app_library.list_persisted_whatsapp_web_sessions")
    def test_list_sessions_handles_exception(self, mock_list, initialized_library):
        mock_list.side_effect = Exception("File system error")

        result = initialized_library.list_persisted_sessions()

        assert result["status"] == "error"
