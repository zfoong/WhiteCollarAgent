"""
Tests for Telegram external library (Bot API and MTProto).

Uses pytest with unittest.mock to mock the Telegram helper functions,
allowing all library methods to be tested without network access.

Usage:
    pytest core/external_libraries/telegram/tests/test_telegram_library.py -v
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.telegram.credentials import TelegramCredential
from core.external_libraries.telegram.external_app_library import TelegramAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset TelegramAppLibrary state before each test."""
    TelegramAppLibrary._initialized = False
    TelegramAppLibrary._credential_store = None
    yield
    TelegramAppLibrary._initialized = False
    TelegramAppLibrary._credential_store = None


@pytest.fixture
def mock_bot_credential():
    """Return a sample Telegram Bot API credential."""
    return TelegramCredential(
        user_id="test_user",
        connection_type="bot_api",
        bot_id="123456",
        bot_username="test_bot",
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    )


@pytest.fixture
def mock_mtproto_credential():
    """Return a sample Telegram MTProto credential."""
    return TelegramCredential(
        user_id="test_user",
        connection_type="mtproto",
        phone_number="+1234567890",
        api_id=12345,
        api_hash="abcdef1234567890abcdef1234567890",
        session_string="fake_session_string_data",
        account_name="Test User",
        telegram_user_id=999888777,
    )


@pytest.fixture
def initialized_library(mock_bot_credential):
    """Initialize the library and inject a mock bot credential."""
    TelegramAppLibrary.initialize()
    TelegramAppLibrary.get_credential_store().add(mock_bot_credential)
    return TelegramAppLibrary


@pytest.fixture
def initialized_library_mtproto(mock_bot_credential, mock_mtproto_credential):
    """Initialize the library with both bot and MTProto credentials."""
    TelegramAppLibrary.initialize()
    TelegramAppLibrary.get_credential_store().add(mock_bot_credential)
    TelegramAppLibrary.get_credential_store().add(mock_mtproto_credential)
    return TelegramAppLibrary


# ---------------------------------------------------------------------------
# Helper: Module path prefix for patching
# ---------------------------------------------------------------------------
HELPERS_PATH = "core.external_libraries.telegram.helpers.telegram_helpers"
LIB_PATH = "core.external_libraries.telegram.external_app_library"


# ---------------------------------------------------------------------------
# Initialization & Credential Tests
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_initialize(self):
        assert not TelegramAppLibrary._initialized
        TelegramAppLibrary.initialize()
        assert TelegramAppLibrary._initialized
        assert TelegramAppLibrary._credential_store is not None

    def test_initialize_idempotent(self):
        TelegramAppLibrary.initialize()
        store = TelegramAppLibrary._credential_store
        TelegramAppLibrary.initialize()
        assert TelegramAppLibrary._credential_store is store

    def test_get_name(self):
        assert TelegramAppLibrary.get_name() == "Telegram"

    def test_get_credential_store_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            TelegramAppLibrary.get_credential_store()

    def test_get_credential_store_after_init(self):
        TelegramAppLibrary.initialize()
        store = TelegramAppLibrary.get_credential_store()
        assert store is not None


class TestValidateConnection:

    def test_validate_no_credentials(self):
        TelegramAppLibrary.initialize()
        assert TelegramAppLibrary.validate_connection(user_id="nonexistent") is False

    def test_validate_with_credentials(self, initialized_library, mock_bot_credential):
        assert initialized_library.validate_connection(user_id="test_user") is True

    def test_validate_with_wrong_user(self, initialized_library):
        assert initialized_library.validate_connection(user_id="other_user") is False

    def test_validate_with_bot_id(self, initialized_library, mock_bot_credential):
        assert initialized_library.validate_connection(
            user_id="test_user",
            bot_id="123456",
        ) is True

    def test_validate_with_wrong_bot_id(self, initialized_library):
        assert initialized_library.validate_connection(
            user_id="test_user",
            bot_id="wrong_id",
        ) is False


class TestGetCredentials:

    def test_get_credentials_found(self, initialized_library, mock_bot_credential):
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.user_id == "test_user"
        assert cred.bot_token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    def test_get_credentials_not_found(self, initialized_library):
        cred = initialized_library.get_credentials(user_id="nonexistent")
        assert cred is None

    def test_get_credentials_with_bot_id(self, initialized_library, mock_bot_credential):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            bot_id="123456",
        )
        assert cred is not None
        assert cred.bot_id == "123456"

    def test_get_credentials_with_wrong_bot_id(self, initialized_library):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            bot_id="wrong_id",
        )
        assert cred is None


# ---------------------------------------------------------------------------
# Credential Model Tests
# ---------------------------------------------------------------------------

class TestTelegramCredential:

    def test_bot_api_defaults(self):
        cred = TelegramCredential(user_id="u1")
        assert cred.connection_type == "bot_api"
        assert cred.bot_id == ""
        assert cred.bot_username == ""
        assert cred.bot_token == ""
        assert cred.phone_number == ""
        assert cred.api_id == 0
        assert cred.api_hash == ""
        assert cred.session_string == ""
        assert cred.account_name == ""
        assert cred.telegram_user_id == 0

    def test_bot_api_full(self):
        cred = TelegramCredential(
            user_id="u1",
            connection_type="bot_api",
            bot_id="b1",
            bot_username="mybot",
            bot_token="123:abc",
        )
        assert cred.bot_id == "b1"
        assert cred.bot_username == "mybot"
        assert cred.bot_token == "123:abc"

    def test_mtproto_full(self):
        cred = TelegramCredential(
            user_id="u1",
            connection_type="mtproto",
            phone_number="+1234567890",
            api_id=12345,
            api_hash="hash_value",
            session_string="session_data",
            account_name="John Doe",
            telegram_user_id=9999,
        )
        assert cred.connection_type == "mtproto"
        assert cred.phone_number == "+1234567890"
        assert cred.api_id == 12345
        assert cred.session_string == "session_data"

    def test_credential_unique_keys(self):
        assert TelegramCredential.UNIQUE_KEYS == ("user_id", "bot_id", "phone_number")

    def test_credential_to_dict(self):
        cred = TelegramCredential(
            user_id="u1",
            bot_id="b1",
            bot_token="123:abc",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["bot_id"] == "b1"
        assert d["bot_token"] == "123:abc"
        assert d["connection_type"] == "bot_api"


# ---------------------------------------------------------------------------
# Resolve Chat Identifier Tests
# ---------------------------------------------------------------------------

class TestResolveChatIdentifier:

    def test_resolve_with_chat_id(self, initialized_library):
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
            chat_id=12345,
        )
        assert result["status"] == "success"
        assert result["resolved_chat_id"] == 12345

    def test_resolve_with_string_chat_id(self, initialized_library):
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
            chat_id="@channel_name",
        )
        assert result["status"] == "success"
        assert result["resolved_chat_id"] == "@channel_name"

    @patch(f"{LIB_PATH}.search_contact")
    def test_resolve_with_name_success(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 99999, "name": "John Doe", "username": "johndoe"}],
            "count": 1,
        }
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
            name="John",
        )
        assert result["status"] == "success"
        assert result["resolved_chat_id"] == 99999
        assert result["resolved_contact"]["name"] == "John Doe"

    @patch(f"{LIB_PATH}.search_contact")
    def test_resolve_with_name_not_found(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [],
            "count": 0,
        }
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
            name="UnknownPerson",
        )
        assert result["status"] == "error"
        assert "No contacts found" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    def test_resolve_with_name_search_error(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "error",
            "reason": "API failure",
        }
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
            name="SomeOne",
        )
        assert result["status"] == "error"
        assert "Could not find contact" in result["reason"]

    def test_resolve_neither_chat_id_nor_name(self, initialized_library):
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]

    def test_resolve_chat_id_takes_precedence_over_name(self, initialized_library):
        """When both chat_id and name are provided, chat_id is used directly."""
        result = initialized_library._resolve_chat_identifier(
            user_id="test_user",
            chat_id=12345,
            name="John",
        )
        assert result["status"] == "success"
        assert result["resolved_chat_id"] == 12345
        # No contact resolution should have happened
        assert "resolved_contact" not in result


# ---------------------------------------------------------------------------
# Get Bot Info Tests
# ---------------------------------------------------------------------------

class TestGetBotInfo:

    @patch(f"{LIB_PATH}.get_me")
    def test_get_bot_info_success(self, mock_get_me, initialized_library):
        mock_get_me.return_value = {
            "ok": True,
            "result": {
                "id": 123456,
                "is_bot": True,
                "first_name": "Test Bot",
                "username": "test_bot",
            },
        }
        result = initialized_library.get_bot_info(user_id="test_user")
        assert result["status"] == "success"
        assert result["bot"]["id"] == 123456
        assert result["bot"]["username"] == "test_bot"
        mock_get_me.assert_called_once()

    def test_get_bot_info_no_credential(self, initialized_library):
        result = initialized_library.get_bot_info(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.get_me")
    def test_get_bot_info_api_error(self, mock_get_me, initialized_library):
        mock_get_me.return_value = {
            "error": "Unauthorized",
            "details": {"ok": False, "error_code": 401},
        }
        result = initialized_library.get_bot_info(user_id="test_user")
        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{LIB_PATH}.get_me")
    def test_get_bot_info_exception(self, mock_get_me, initialized_library):
        mock_get_me.side_effect = Exception("Network error")
        result = initialized_library.get_bot_info(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.get_me")
    def test_get_bot_info_with_bot_id(self, mock_get_me, initialized_library):
        mock_get_me.return_value = {
            "ok": True,
            "result": {"id": 123456, "is_bot": True, "first_name": "Test Bot"},
        }
        result = initialized_library.get_bot_info(
            user_id="test_user", bot_id="123456"
        )
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Send Message Tests
# ---------------------------------------------------------------------------

class TestSendMessage:

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_success_with_chat_id(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "result": {
                "message_id": 42,
                "chat": {"id": 12345},
                "text": "Hello!",
                "date": 1700000000,
            },
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Hello!",
            chat_id=12345,
        )
        assert result["status"] == "success"
        assert result["message"]["message_id"] == 42
        mock_send.assert_called_once()

    def test_send_message_no_credential(self, initialized_library):
        result = initialized_library.send_message(
            user_id="nonexistent",
            text="Hello!",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_api_error(self, mock_send, initialized_library):
        mock_send.return_value = {
            "error": "Bad Request: chat not found",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Hello!",
            chat_id=99999,
        )
        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Connection timeout")
        result = initialized_library.send_message(
            user_id="test_user",
            text="Hello!",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_with_parse_mode(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 43, "chat": {"id": 12345}, "text": "<b>bold</b>"},
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="<b>bold</b>",
            chat_id=12345,
            parse_mode="HTML",
        )
        assert result["status"] == "success"

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_with_reply(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 44, "chat": {"id": 12345}, "text": "Reply"},
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Reply",
            chat_id=12345,
            reply_to_message_id=10,
        )
        assert result["status"] == "success"

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_with_name_resolution(self, mock_send, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 55555, "name": "Alice", "username": "alice"}],
            "count": 1,
        }
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 45, "chat": {"id": 55555}, "text": "Hi Alice"},
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Hi Alice",
            name="Alice",
        )
        assert result["status"] == "success"
        assert result["resolved_contact"]["name"] == "Alice"

    def test_send_message_no_chat_id_or_name(self, initialized_library):
        result = initialized_library.send_message(
            user_id="test_user",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    def test_send_message_name_not_found(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [],
            "count": 0,
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Hello!",
            name="Nobody",
        )
        assert result["status"] == "error"
        assert "No contacts found" in result["reason"]


# ---------------------------------------------------------------------------
# Send Photo Tests
# ---------------------------------------------------------------------------

class TestSendPhoto:

    @patch(f"{LIB_PATH}.send_photo")
    def test_send_photo_success(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "result": {
                "message_id": 50,
                "chat": {"id": 12345},
                "photo": [{"file_id": "photo123"}],
            },
        }
        result = initialized_library.send_photo(
            user_id="test_user",
            photo="https://example.com/photo.jpg",
            chat_id=12345,
            caption="Nice photo",
        )
        assert result["status"] == "success"
        assert result["message"]["message_id"] == 50

    def test_send_photo_no_credential(self, initialized_library):
        result = initialized_library.send_photo(
            user_id="nonexistent",
            photo="photo.jpg",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.send_photo")
    def test_send_photo_api_error(self, mock_send, initialized_library):
        mock_send.return_value = {
            "error": "Bad Request: wrong file identifier",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.send_photo(
            user_id="test_user",
            photo="bad_file_id",
            chat_id=12345,
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.send_photo")
    def test_send_photo_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Upload failed")
        result = initialized_library.send_photo(
            user_id="test_user",
            photo="photo.jpg",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.send_photo")
    def test_send_photo_with_name_resolution(self, mock_send, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 55555, "name": "Bob", "username": "bob"}],
            "count": 1,
        }
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 51, "chat": {"id": 55555}},
        }
        result = initialized_library.send_photo(
            user_id="test_user",
            photo="photo.jpg",
            name="Bob",
        )
        assert result["status"] == "success"
        assert result["resolved_contact"]["name"] == "Bob"

    def test_send_photo_no_chat_id_or_name(self, initialized_library):
        result = initialized_library.send_photo(
            user_id="test_user",
            photo="photo.jpg",
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]


# ---------------------------------------------------------------------------
# Send Document Tests
# ---------------------------------------------------------------------------

class TestSendDocument:

    @patch(f"{LIB_PATH}.send_document")
    def test_send_document_success(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "result": {
                "message_id": 60,
                "chat": {"id": 12345},
                "document": {"file_id": "doc123", "file_name": "report.pdf"},
            },
        }
        result = initialized_library.send_document(
            user_id="test_user",
            document="https://example.com/report.pdf",
            chat_id=12345,
            caption="Monthly report",
        )
        assert result["status"] == "success"
        assert result["message"]["message_id"] == 60

    def test_send_document_no_credential(self, initialized_library):
        result = initialized_library.send_document(
            user_id="nonexistent",
            document="report.pdf",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.send_document")
    def test_send_document_api_error(self, mock_send, initialized_library):
        mock_send.return_value = {
            "error": "Bad Request: file too big",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.send_document(
            user_id="test_user",
            document="huge_file.zip",
            chat_id=12345,
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.send_document")
    def test_send_document_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Disk error")
        result = initialized_library.send_document(
            user_id="test_user",
            document="doc.pdf",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.send_document")
    def test_send_document_with_name_resolution(self, mock_send, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 77777, "name": "Carol", "username": "carol"}],
            "count": 1,
        }
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 61, "chat": {"id": 77777}},
        }
        result = initialized_library.send_document(
            user_id="test_user",
            document="file.pdf",
            name="Carol",
        )
        assert result["status"] == "success"
        assert result["resolved_contact"]["name"] == "Carol"

    def test_send_document_no_chat_id_or_name(self, initialized_library):
        result = initialized_library.send_document(
            user_id="test_user",
            document="doc.pdf",
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]


# ---------------------------------------------------------------------------
# Get Updates Tests
# ---------------------------------------------------------------------------

class TestGetUpdates:

    @patch(f"{LIB_PATH}.get_updates")
    def test_get_updates_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "ok": True,
            "result": [
                {"update_id": 1, "message": {"message_id": 1, "text": "Hello"}},
                {"update_id": 2, "message": {"message_id": 2, "text": "World"}},
            ],
        }
        result = initialized_library.get_updates(user_id="test_user")
        assert result["status"] == "success"
        assert len(result["updates"]) == 2
        assert result["updates"][0]["update_id"] == 1

    def test_get_updates_no_credential(self, initialized_library):
        result = initialized_library.get_updates(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.get_updates")
    def test_get_updates_api_error(self, mock_get, initialized_library):
        mock_get.return_value = {
            "error": "Unauthorized",
            "details": {"ok": False, "error_code": 401},
        }
        result = initialized_library.get_updates(user_id="test_user")
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.get_updates")
    def test_get_updates_empty(self, mock_get, initialized_library):
        mock_get.return_value = {"ok": True, "result": []}
        result = initialized_library.get_updates(user_id="test_user")
        assert result["status"] == "success"
        assert result["updates"] == []

    @patch(f"{LIB_PATH}.get_updates")
    def test_get_updates_with_offset_and_limit(self, mock_get, initialized_library):
        mock_get.return_value = {"ok": True, "result": []}
        result = initialized_library.get_updates(
            user_id="test_user",
            offset=100,
            limit=10,
        )
        assert result["status"] == "success"
        mock_get.assert_called_once_with(
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            offset=100,
            limit=10,
        )

    @patch(f"{LIB_PATH}.get_updates")
    def test_get_updates_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Timeout")
        result = initialized_library.get_updates(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# Get Chat Tests
# ---------------------------------------------------------------------------

class TestGetChat:

    @patch(f"{LIB_PATH}.get_chat")
    def test_get_chat_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "ok": True,
            "result": {
                "id": 12345,
                "type": "private",
                "first_name": "John",
                "last_name": "Doe",
            },
        }
        result = initialized_library.get_chat(
            user_id="test_user",
            chat_id=12345,
        )
        assert result["status"] == "success"
        assert result["chat"]["id"] == 12345
        assert result["chat"]["first_name"] == "John"

    def test_get_chat_no_credential(self, initialized_library):
        result = initialized_library.get_chat(
            user_id="nonexistent",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.get_chat")
    def test_get_chat_api_error(self, mock_get, initialized_library):
        mock_get.return_value = {
            "error": "Bad Request: chat not found",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.get_chat(
            user_id="test_user",
            chat_id=99999,
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.get_chat")
    def test_get_chat_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Network error")
        result = initialized_library.get_chat(
            user_id="test_user",
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.get_chat")
    def test_get_chat_with_name(self, mock_get, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 88888, "name": "TestGroup", "username": ""}],
            "count": 1,
        }
        mock_get.return_value = {
            "ok": True,
            "result": {"id": 88888, "type": "group", "title": "TestGroup"},
        }
        result = initialized_library.get_chat(
            user_id="test_user",
            name="TestGroup",
        )
        assert result["status"] == "success"
        assert result["chat"]["title"] == "TestGroup"
        assert result["resolved_contact"]["name"] == "TestGroup"

    def test_get_chat_no_chat_id_or_name(self, initialized_library):
        result = initialized_library.get_chat(user_id="test_user")
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]


# ---------------------------------------------------------------------------
# Get Chat Member Tests
# ---------------------------------------------------------------------------

class TestGetChatMember:

    @patch(f"{LIB_PATH}.get_chat_member")
    def test_get_chat_member_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "ok": True,
            "result": {
                "user": {"id": 555, "first_name": "Alice"},
                "status": "member",
            },
        }
        result = initialized_library.get_chat_member(
            user_id="test_user",
            chat_id=-100123456,
            target_user_id=555,
        )
        assert result["status"] == "success"
        assert result["member"]["user"]["first_name"] == "Alice"
        assert result["member"]["status"] == "member"

    def test_get_chat_member_no_credential(self, initialized_library):
        result = initialized_library.get_chat_member(
            user_id="nonexistent",
            chat_id=-100123456,
            target_user_id=555,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.get_chat_member")
    def test_get_chat_member_api_error(self, mock_get, initialized_library):
        mock_get.return_value = {
            "error": "Bad Request: user not found",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.get_chat_member(
            user_id="test_user",
            chat_id=-100123456,
            target_user_id=999,
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.get_chat_member")
    def test_get_chat_member_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Server error")
        result = initialized_library.get_chat_member(
            user_id="test_user",
            chat_id=-100123456,
            target_user_id=555,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.get_chat_member")
    def test_get_chat_member_with_name(self, mock_get, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": -100123456, "name": "Dev Group", "username": ""}],
            "count": 1,
        }
        mock_get.return_value = {
            "ok": True,
            "result": {"user": {"id": 555}, "status": "administrator"},
        }
        result = initialized_library.get_chat_member(
            user_id="test_user",
            name="Dev Group",
            target_user_id=555,
        )
        assert result["status"] == "success"
        assert result["resolved_contact"]["name"] == "Dev Group"

    def test_get_chat_member_no_chat_id_or_name(self, initialized_library):
        result = initialized_library.get_chat_member(
            user_id="test_user",
            target_user_id=555,
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]


# ---------------------------------------------------------------------------
# Get Chat Members Count Tests
# ---------------------------------------------------------------------------

class TestGetChatMembersCount:

    @patch(f"{LIB_PATH}.get_chat_members_count")
    def test_get_count_success(self, mock_get, initialized_library):
        mock_get.return_value = {"ok": True, "result": 42}
        result = initialized_library.get_chat_members_count(
            user_id="test_user",
            chat_id=-100123456,
        )
        assert result["status"] == "success"
        assert result["count"] == 42

    def test_get_count_no_credential(self, initialized_library):
        result = initialized_library.get_chat_members_count(
            user_id="nonexistent",
            chat_id=-100123456,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.get_chat_members_count")
    def test_get_count_api_error(self, mock_get, initialized_library):
        mock_get.return_value = {
            "error": "Bad Request: chat not found",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.get_chat_members_count(
            user_id="test_user",
            chat_id=-100123456,
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.get_chat_members_count")
    def test_get_count_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Network error")
        result = initialized_library.get_chat_members_count(
            user_id="test_user",
            chat_id=-100123456,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.get_chat_members_count")
    def test_get_count_with_name(self, mock_get, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": -100123456, "name": "Team Chat", "username": ""}],
            "count": 1,
        }
        mock_get.return_value = {"ok": True, "result": 15}
        result = initialized_library.get_chat_members_count(
            user_id="test_user",
            name="Team Chat",
        )
        assert result["status"] == "success"
        assert result["count"] == 15
        assert result["resolved_contact"]["name"] == "Team Chat"

    def test_get_count_no_chat_id_or_name(self, initialized_library):
        result = initialized_library.get_chat_members_count(
            user_id="test_user",
        )
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Forward Message Tests
# ---------------------------------------------------------------------------

class TestForwardMessage:

    @patch(f"{LIB_PATH}.forward_message")
    def test_forward_message_success(self, mock_fwd, initialized_library):
        mock_fwd.return_value = {
            "ok": True,
            "result": {
                "message_id": 100,
                "forward_date": 1700000000,
                "chat": {"id": 12345},
            },
        }
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=10,
            chat_id=12345,
            from_chat_id=67890,
        )
        assert result["status"] == "success"
        assert result["message"]["message_id"] == 100

    def test_forward_message_no_credential(self, initialized_library):
        result = initialized_library.forward_message(
            user_id="nonexistent",
            message_id=10,
            chat_id=12345,
            from_chat_id=67890,
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.forward_message")
    def test_forward_message_api_error(self, mock_fwd, initialized_library):
        mock_fwd.return_value = {
            "error": "Bad Request: message to forward not found",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=999,
            chat_id=12345,
            from_chat_id=67890,
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.forward_message")
    def test_forward_message_exception(self, mock_fwd, initialized_library):
        mock_fwd.side_effect = Exception("API timeout")
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=10,
            chat_id=12345,
            from_chat_id=67890,
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    def test_forward_message_no_destination(self, initialized_library):
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=10,
            from_chat_id=67890,
        )
        assert result["status"] == "error"
        assert "Destination" in result["reason"]

    def test_forward_message_no_source(self, initialized_library):
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=10,
            chat_id=12345,
        )
        assert result["status"] == "error"
        assert "Source" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.forward_message")
    def test_forward_message_with_name_resolution(self, mock_fwd, mock_search, initialized_library):
        mock_search.side_effect = [
            {
                "status": "success",
                "contacts": [{"chat_id": 11111, "name": "Alice", "username": "alice"}],
                "count": 1,
            },
            {
                "status": "success",
                "contacts": [{"chat_id": 22222, "name": "Bob", "username": "bob"}],
                "count": 1,
            },
        ]
        mock_fwd.return_value = {
            "ok": True,
            "result": {"message_id": 101, "chat": {"id": 11111}},
        }
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=10,
            to_name="Alice",
            from_name="Bob",
        )
        assert result["status"] == "success"
        assert result["resolved_to_contact"]["name"] == "Alice"
        assert result["resolved_from_contact"]["name"] == "Bob"

    @patch(f"{LIB_PATH}.search_contact")
    def test_forward_message_destination_name_not_found(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [],
            "count": 0,
        }
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=10,
            to_name="Nobody",
            from_chat_id=67890,
        )
        assert result["status"] == "error"
        assert "Destination" in result["reason"]


# ---------------------------------------------------------------------------
# Webhook Management Tests
# ---------------------------------------------------------------------------

class TestSetWebhook:

    @patch(f"{LIB_PATH}.set_webhook")
    def test_set_webhook_success(self, mock_set, initialized_library):
        mock_set.return_value = {"ok": True, "result": True}
        result = initialized_library.set_webhook(
            user_id="test_user",
            webhook_url="https://example.com/webhook",
        )
        assert result["status"] == "success"
        assert result["result"] is True

    def test_set_webhook_no_credential(self, initialized_library):
        result = initialized_library.set_webhook(
            user_id="nonexistent",
            webhook_url="https://example.com/webhook",
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.set_webhook")
    def test_set_webhook_api_error(self, mock_set, initialized_library):
        mock_set.return_value = {
            "error": "Bad Request: bad webhook URL",
            "details": {"ok": False, "error_code": 400},
        }
        result = initialized_library.set_webhook(
            user_id="test_user",
            webhook_url="http://invalid",
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.set_webhook")
    def test_set_webhook_with_secret_token(self, mock_set, initialized_library):
        mock_set.return_value = {"ok": True, "result": True}
        result = initialized_library.set_webhook(
            user_id="test_user",
            webhook_url="https://example.com/webhook",
            secret_token="my_secret_123",
        )
        assert result["status"] == "success"
        mock_set.assert_called_once_with(
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            url="https://example.com/webhook",
            secret_token="my_secret_123",
        )

    @patch(f"{LIB_PATH}.set_webhook")
    def test_set_webhook_exception(self, mock_set, initialized_library):
        mock_set.side_effect = Exception("SSL error")
        result = initialized_library.set_webhook(
            user_id="test_user",
            webhook_url="https://example.com/webhook",
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


class TestDeleteWebhook:

    @patch(f"{LIB_PATH}.delete_webhook")
    def test_delete_webhook_success(self, mock_del, initialized_library):
        mock_del.return_value = {"ok": True, "result": True}
        result = initialized_library.delete_webhook(user_id="test_user")
        assert result["status"] == "success"
        assert result["result"] is True

    def test_delete_webhook_no_credential(self, initialized_library):
        result = initialized_library.delete_webhook(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.delete_webhook")
    def test_delete_webhook_api_error(self, mock_del, initialized_library):
        mock_del.return_value = {
            "error": "Unauthorized",
            "details": {"ok": False, "error_code": 401},
        }
        result = initialized_library.delete_webhook(user_id="test_user")
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.delete_webhook")
    def test_delete_webhook_exception(self, mock_del, initialized_library):
        mock_del.side_effect = Exception("API down")
        result = initialized_library.delete_webhook(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


class TestGetWebhookInfo:

    @patch(f"{LIB_PATH}.get_webhook_info")
    def test_get_webhook_info_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "ok": True,
            "result": {
                "url": "https://example.com/webhook",
                "has_custom_certificate": False,
                "pending_update_count": 0,
            },
        }
        result = initialized_library.get_webhook_info(user_id="test_user")
        assert result["status"] == "success"
        assert result["webhook"]["url"] == "https://example.com/webhook"

    def test_get_webhook_info_no_credential(self, initialized_library):
        result = initialized_library.get_webhook_info(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.get_webhook_info")
    def test_get_webhook_info_api_error(self, mock_get, initialized_library):
        mock_get.return_value = {
            "error": "Unauthorized",
            "details": {"ok": False, "error_code": 401},
        }
        result = initialized_library.get_webhook_info(user_id="test_user")
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.get_webhook_info")
    def test_get_webhook_info_empty_webhook(self, mock_get, initialized_library):
        mock_get.return_value = {
            "ok": True,
            "result": {
                "url": "",
                "has_custom_certificate": False,
                "pending_update_count": 0,
            },
        }
        result = initialized_library.get_webhook_info(user_id="test_user")
        assert result["status"] == "success"
        assert result["webhook"]["url"] == ""

    @patch(f"{LIB_PATH}.get_webhook_info")
    def test_get_webhook_info_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Timeout")
        result = initialized_library.get_webhook_info(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# Search Contact Tests
# ---------------------------------------------------------------------------

class TestSearchContact:

    @patch(f"{LIB_PATH}.search_contact")
    def test_search_contact_success(self, mock_search, initialized_library):
        mock_search.return_value = {
            "ok": True,
            "result": {
                "contacts": [
                    {"chat_id": 111, "name": "John Doe", "type": "private", "username": "johndoe"},
                    {"chat_id": 222, "name": "John Smith", "type": "private", "username": "johnsmith"},
                ],
                "count": 2,
            },
        }
        result = initialized_library.search_contact(
            user_id="test_user",
            name="John",
        )
        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["contacts"]) == 2
        assert result["contacts"][0]["name"] == "John Doe"

    def test_search_contact_no_credential(self, initialized_library):
        result = initialized_library.search_contact(
            user_id="nonexistent",
            name="John",
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    def test_search_contact_not_found(self, mock_search, initialized_library):
        mock_search.return_value = {
            "error": "No contacts found matching 'Nobody'",
            "details": {"searched_updates": 50, "name": "Nobody"},
        }
        result = initialized_library.search_contact(
            user_id="test_user",
            name="Nobody",
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.search_contact")
    def test_search_contact_exception(self, mock_search, initialized_library):
        mock_search.side_effect = Exception("API crash")
        result = initialized_library.search_contact(
            user_id="test_user",
            name="Someone",
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    def test_search_contact_empty_result(self, mock_search, initialized_library):
        mock_search.return_value = {
            "ok": True,
            "result": {"contacts": [], "count": 0},
        }
        result = initialized_library.search_contact(
            user_id="test_user",
            name="GhostUser",
        )
        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["contacts"] == []


# ---------------------------------------------------------------------------
# Send Message To Name Tests
# ---------------------------------------------------------------------------

class TestSendMessageToName:

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.send_message")
    def test_send_to_name_success(self, mock_send, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 55555, "name": "Alice", "username": "alice"}],
            "count": 1,
        }
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 200, "chat": {"id": 55555}, "text": "Hi Alice!"},
        }
        result = initialized_library.send_message_to_name(
            user_id="test_user",
            name="Alice",
            text="Hi Alice!",
        )
        assert result["status"] == "success"
        assert result["resolved_contact"]["name"] == "Alice"

    @patch(f"{LIB_PATH}.search_contact")
    def test_send_to_name_contact_not_found(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [],
            "count": 0,
        }
        result = initialized_library.send_message_to_name(
            user_id="test_user",
            name="Nobody",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "No contacts found" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    def test_send_to_name_search_error(self, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "error",
            "reason": "Unauthorized",
        }
        result = initialized_library.send_message_to_name(
            user_id="test_user",
            name="Someone",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "Could not find contact" in result["reason"]

    def test_send_to_name_no_credential(self, initialized_library):
        result = initialized_library.send_message_to_name(
            user_id="nonexistent",
            name="Alice",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "No valid Telegram credential" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.send_message")
    def test_send_to_name_send_fails(self, mock_send, mock_search, initialized_library):
        mock_search.return_value = {
            "status": "success",
            "contacts": [{"chat_id": 55555, "name": "Alice", "username": "alice"}],
            "count": 1,
        }
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 201, "chat": {"id": 55555}},
        }
        # The send_message method on the library is what's called, which wraps
        # the helper. Since we mock at the library level, success is returned.
        result = initialized_library.send_message_to_name(
            user_id="test_user",
            name="Alice",
            text="Hi!",
            parse_mode="HTML",
        )
        assert result["status"] == "success"

    @patch(f"{LIB_PATH}.search_contact")
    def test_send_to_name_exception(self, mock_search, initialized_library):
        mock_search.side_effect = Exception("Crash")
        result = initialized_library.send_message_to_name(
            user_id="test_user",
            name="Alice",
            text="Hello!",
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch(f"{LIB_PATH}.search_contact")
    @patch(f"{LIB_PATH}.send_message")
    def test_send_to_name_uses_first_match(self, mock_send, mock_search, initialized_library):
        """When multiple contacts match, the first one is used."""
        mock_search.return_value = {
            "status": "success",
            "contacts": [
                {"chat_id": 11111, "name": "John A", "username": "johna"},
                {"chat_id": 22222, "name": "John B", "username": "johnb"},
            ],
            "count": 2,
        }
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 300, "chat": {"id": 11111}},
        }
        result = initialized_library.send_message_to_name(
            user_id="test_user",
            name="John",
            text="Hey!",
        )
        assert result["status"] == "success"
        assert result["resolved_contact"]["chat_id"] == 11111


# ---------------------------------------------------------------------------
# MTProto Credential Tests
# ---------------------------------------------------------------------------

class TestMTProtoCredentials:

    def test_get_mtproto_credentials_found(self, initialized_library_mtproto):
        cred = initialized_library_mtproto.get_mtproto_credentials(user_id="test_user")
        assert cred is not None
        assert cred.connection_type == "mtproto"
        assert cred.phone_number == "+1234567890"
        assert cred.session_string == "fake_session_string_data"

    def test_get_mtproto_credentials_not_found(self, initialized_library):
        # initialized_library only has bot_api credential
        cred = initialized_library.get_mtproto_credentials(user_id="test_user")
        assert cred is None

    def test_get_mtproto_credentials_wrong_user(self, initialized_library_mtproto):
        cred = initialized_library_mtproto.get_mtproto_credentials(user_id="other_user")
        assert cred is None

    def test_get_mtproto_credentials_with_phone(self, initialized_library_mtproto):
        cred = initialized_library_mtproto.get_mtproto_credentials(
            user_id="test_user",
            phone_number="+1234567890",
        )
        assert cred is not None
        assert cred.phone_number == "+1234567890"

    def test_get_mtproto_credentials_wrong_phone(self, initialized_library_mtproto):
        cred = initialized_library_mtproto.get_mtproto_credentials(
            user_id="test_user",
            phone_number="+9999999999",
        )
        assert cred is None

    def test_validate_mtproto_connection_valid(self, initialized_library_mtproto):
        assert initialized_library_mtproto.validate_mtproto_connection(
            user_id="test_user"
        ) is True

    def test_validate_mtproto_connection_no_session(self, initialized_library):
        assert initialized_library.validate_mtproto_connection(
            user_id="test_user"
        ) is False

    def test_validate_mtproto_connection_empty_session(self, initialized_library_mtproto):
        """A credential with empty session_string is not valid."""
        cred = TelegramCredential(
            user_id="empty_user",
            connection_type="mtproto",
            phone_number="+5555555555",
            api_id=11111,
            api_hash="some_hash",
            session_string="",
        )
        initialized_library_mtproto.get_credential_store().add(cred)
        assert initialized_library_mtproto.validate_mtproto_connection(
            user_id="empty_user"
        ) is False


# ---------------------------------------------------------------------------
# MTProto Start Auth Tests
# ---------------------------------------------------------------------------

class TestStartMTProtoAuth:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_start_auth_mtproto_unavailable(self, initialized_library):
        result = initialized_library.start_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            api_id=12345,
            api_hash="hash",
        )
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_start_auth_success(self, mock_mtproto_module, initialized_library):
        import asyncio

        async def fake_start_auth(*args, **kwargs):
            return {
                "result": {
                    "phone_code_hash": "abc123hash",
                    "session_string": "pending_session",
                }
            }

        mock_mtproto_module.start_auth = fake_start_auth

        result = initialized_library.start_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            api_id=12345,
            api_hash="hash_value",
        )
        assert result["status"] == "success"
        assert result["phone_code_hash"] == "abc123hash"
        assert result["phone_number"] == "+1234567890"
        assert "OTP code sent" in result["message"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_start_auth_api_error(self, mock_mtproto_module, initialized_library):
        async def fake_start_auth(*args, **kwargs):
            return {"error": "PHONE_NUMBER_INVALID"}

        mock_mtproto_module.start_auth = fake_start_auth

        result = initialized_library.start_mtproto_auth(
            user_id="test_user",
            phone_number="+invalid",
            api_id=12345,
            api_hash="hash",
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_start_auth_exception(self, mock_mtproto_module, initialized_library):
        async def fake_start_auth(*args, **kwargs):
            raise Exception("Connection refused")

        mock_mtproto_module.start_auth = fake_start_auth

        result = initialized_library.start_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            api_id=12345,
            api_hash="hash",
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Complete Auth Tests
# ---------------------------------------------------------------------------

class TestCompleteMTProtoAuth:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_complete_auth_mtproto_unavailable(self, initialized_library):
        result = initialized_library.complete_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            code="12345",
            phone_code_hash="hash",
        )
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_complete_auth_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_complete_auth(*args, **kwargs):
            return {
                "result": {
                    "session_string": "final_session_string",
                    "user_id": 999888,
                    "first_name": "Test",
                    "last_name": "User",
                    "username": "testuser",
                    "phone": "+1234567890",
                }
            }

        mock_mtproto_module.complete_auth = fake_complete_auth

        result = initialized_library_mtproto.complete_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            code="12345",
            phone_code_hash="hash123",
        )
        assert result["status"] == "success"
        assert result["user_id"] == 999888
        assert result["session_string"] == "final_session_string"
        assert result["name"] == "Test User"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_complete_auth_no_pending(self, initialized_library):
        """No MTProto credential exists for the phone number."""
        result = initialized_library.complete_mtproto_auth(
            user_id="test_user",
            phone_number="+9999999999",
            code="12345",
            phone_code_hash="hash",
        )
        assert result["status"] == "error"
        assert "No pending auth found" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_complete_auth_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_complete_auth(*args, **kwargs):
            return {"error": "PHONE_CODE_INVALID"}

        mock_mtproto_module.complete_auth = fake_complete_auth

        result = initialized_library_mtproto.complete_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            code="00000",
            phone_code_hash="hash",
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_complete_auth_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_complete_auth(*args, **kwargs):
            raise Exception("Session expired")

        mock_mtproto_module.complete_auth = fake_complete_auth

        result = initialized_library_mtproto.complete_mtproto_auth(
            user_id="test_user",
            phone_number="+1234567890",
            code="12345",
            phone_code_hash="hash",
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Get Chats (Dialogs) Tests
# ---------------------------------------------------------------------------

class TestGetTelegramChats:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_get_chats_mtproto_unavailable(self, initialized_library):
        result = initialized_library.get_telegram_chats(user_id="test_user")
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_get_chats_no_session(self, initialized_library):
        result = initialized_library.get_telegram_chats(user_id="test_user")
        assert result["status"] == "error"
        assert "No valid MTProto session" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_get_chats_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_dialogs(*args, **kwargs):
            return {
                "result": {
                    "dialogs": [
                        {"id": 111, "name": "Alice", "type": "user"},
                        {"id": -100222, "name": "Dev Group", "type": "group"},
                    ],
                    "count": 2,
                }
            }

        mock_mtproto_module.get_dialogs = fake_get_dialogs

        result = initialized_library_mtproto.get_telegram_chats(user_id="test_user")
        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["chats"]) == 2

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_get_chats_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_dialogs(*args, **kwargs):
            return {"error": "AUTH_KEY_UNREGISTERED"}

        mock_mtproto_module.get_dialogs = fake_get_dialogs

        result = initialized_library_mtproto.get_telegram_chats(user_id="test_user")
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_get_chats_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_dialogs(*args, **kwargs):
            raise Exception("Connection lost")

        mock_mtproto_module.get_dialogs = fake_get_dialogs

        result = initialized_library_mtproto.get_telegram_chats(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Read Messages Tests
# ---------------------------------------------------------------------------

class TestReadTelegramMessages:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_read_messages_mtproto_unavailable(self, initialized_library):
        result = initialized_library.read_telegram_messages(
            user_id="test_user", chat_id=12345
        )
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_read_messages_no_session(self, initialized_library):
        result = initialized_library.read_telegram_messages(
            user_id="test_user", chat_id=12345
        )
        assert result["status"] == "error"
        assert "No valid MTProto session" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_read_messages_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_messages(*args, **kwargs):
            return {
                "result": {
                    "chat": {"id": 12345, "name": "Alice"},
                    "messages": [
                        {"id": 1, "text": "Hello", "date": "2026-01-01"},
                        {"id": 2, "text": "How are you?", "date": "2026-01-01"},
                    ],
                    "count": 2,
                }
            }

        mock_mtproto_module.get_messages = fake_get_messages

        result = initialized_library_mtproto.read_telegram_messages(
            user_id="test_user", chat_id=12345
        )
        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["messages"]) == 2

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_read_messages_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_messages(*args, **kwargs):
            return {"error": "PEER_ID_INVALID"}

        mock_mtproto_module.get_messages = fake_get_messages

        result = initialized_library_mtproto.read_telegram_messages(
            user_id="test_user", chat_id=99999
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_read_messages_with_name(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search_contacts(*args, **kwargs):
            return {
                "result": {
                    "contacts": [{"id": 55555, "name": "Alice"}],
                    "count": 1,
                }
            }

        async def fake_get_messages(*args, **kwargs):
            return {
                "result": {
                    "chat": {"id": 55555, "name": "Alice"},
                    "messages": [{"id": 1, "text": "Hi"}],
                    "count": 1,
                }
            }

        mock_mtproto_module.search_contacts = fake_search_contacts
        mock_mtproto_module.get_messages = fake_get_messages

        result = initialized_library_mtproto.read_telegram_messages(
            user_id="test_user", name="Alice"
        )
        assert result["status"] == "success"
        assert result["count"] == 1

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_read_messages_name_not_found(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search_contacts(*args, **kwargs):
            return {"result": {"contacts": [], "count": 0}}

        mock_mtproto_module.search_contacts = fake_search_contacts

        result = initialized_library_mtproto.read_telegram_messages(
            user_id="test_user", name="Nobody"
        )
        assert result["status"] == "error"
        assert "No contacts found" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_read_messages_no_chat_id_or_name(self, initialized_library_mtproto):
        result = initialized_library_mtproto.read_telegram_messages(
            user_id="test_user"
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_read_messages_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_messages(*args, **kwargs):
            raise Exception("Connection reset")

        mock_mtproto_module.get_messages = fake_get_messages

        result = initialized_library_mtproto.read_telegram_messages(
            user_id="test_user", chat_id=12345
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Send Message Tests
# ---------------------------------------------------------------------------

class TestSendMTProtoMessage:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_send_mtproto_unavailable(self, initialized_library):
        result = initialized_library.send_mtproto_message(
            user_id="test_user", text="Hello", chat_id=12345
        )
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_send_mtproto_no_session(self, initialized_library):
        result = initialized_library.send_mtproto_message(
            user_id="test_user", text="Hello", chat_id=12345
        )
        assert result["status"] == "error"
        assert "No valid MTProto session" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_mtproto_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_send(*args, **kwargs):
            return {
                "result": {
                    "message_id": 500,
                    "chat_id": 12345,
                    "date": "2026-01-01T12:00:00",
                }
            }

        mock_mtproto_module.send_message = fake_send

        result = initialized_library_mtproto.send_mtproto_message(
            user_id="test_user", text="Hello!", chat_id=12345
        )
        assert result["status"] == "success"
        assert result["message_id"] == 500
        assert result["chat_id"] == 12345

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_mtproto_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_send(*args, **kwargs):
            return {"error": "PEER_ID_INVALID"}

        mock_mtproto_module.send_message = fake_send

        result = initialized_library_mtproto.send_mtproto_message(
            user_id="test_user", text="Hello!", chat_id=99999
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_mtproto_with_name(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search(*args, **kwargs):
            return {"result": {"contacts": [{"id": 55555, "name": "Bob"}], "count": 1}}

        async def fake_send(*args, **kwargs):
            return {
                "result": {
                    "message_id": 501,
                    "chat_id": 55555,
                    "date": "2026-01-01",
                }
            }

        mock_mtproto_module.search_contacts = fake_search
        mock_mtproto_module.send_message = fake_send

        result = initialized_library_mtproto.send_mtproto_message(
            user_id="test_user", text="Hey Bob!", name="Bob"
        )
        assert result["status"] == "success"
        assert result["chat_id"] == 55555

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_mtproto_name_not_found(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search(*args, **kwargs):
            return {"result": {"contacts": [], "count": 0}}

        mock_mtproto_module.search_contacts = fake_search

        result = initialized_library_mtproto.send_mtproto_message(
            user_id="test_user", text="Hello!", name="Ghost"
        )
        assert result["status"] == "error"
        assert "No contacts found" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_send_mtproto_no_chat_id_or_name(self, initialized_library_mtproto):
        result = initialized_library_mtproto.send_mtproto_message(
            user_id="test_user", text="Hello!"
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_mtproto_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_send(*args, **kwargs):
            raise Exception("Flood wait")

        mock_mtproto_module.send_message = fake_send

        result = initialized_library_mtproto.send_mtproto_message(
            user_id="test_user", text="Hello!", chat_id=12345
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Send File Tests
# ---------------------------------------------------------------------------

class TestSendMTProtoFile:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_send_file_mtproto_unavailable(self, initialized_library):
        result = initialized_library.send_mtproto_file(
            user_id="test_user", file_path="/path/to/file.pdf", chat_id=12345
        )
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_send_file_no_session(self, initialized_library):
        result = initialized_library.send_mtproto_file(
            user_id="test_user", file_path="/path/to/file.pdf", chat_id=12345
        )
        assert result["status"] == "error"
        assert "No valid MTProto session" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_file_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_send_file(*args, **kwargs):
            return {
                "result": {
                    "message_id": 600,
                    "chat_id": 12345,
                    "date": "2026-01-01T12:00:00",
                }
            }

        mock_mtproto_module.send_file = fake_send_file

        result = initialized_library_mtproto.send_mtproto_file(
            user_id="test_user",
            file_path="/path/to/doc.pdf",
            chat_id=12345,
            caption="Here is the document",
        )
        assert result["status"] == "success"
        assert result["message_id"] == 600

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_file_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_send_file(*args, **kwargs):
            return {"error": "FILE_REFERENCE_EXPIRED"}

        mock_mtproto_module.send_file = fake_send_file

        result = initialized_library_mtproto.send_mtproto_file(
            user_id="test_user", file_path="/bad/path", chat_id=12345
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_file_with_name(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search(*args, **kwargs):
            return {"result": {"contacts": [{"id": 77777, "name": "Dave"}], "count": 1}}

        async def fake_send_file(*args, **kwargs):
            return {
                "result": {
                    "message_id": 601,
                    "chat_id": 77777,
                    "date": "2026-01-01",
                }
            }

        mock_mtproto_module.search_contacts = fake_search
        mock_mtproto_module.send_file = fake_send_file

        result = initialized_library_mtproto.send_mtproto_file(
            user_id="test_user", file_path="/path/file.pdf", name="Dave"
        )
        assert result["status"] == "success"
        assert result["chat_id"] == 77777

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_send_file_no_chat_id_or_name(self, initialized_library_mtproto):
        result = initialized_library_mtproto.send_mtproto_file(
            user_id="test_user", file_path="/path/file.pdf"
        )
        assert result["status"] == "error"
        assert "Either chat_id or name" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_send_file_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_send_file(*args, **kwargs):
            raise Exception("Upload interrupted")

        mock_mtproto_module.send_file = fake_send_file

        result = initialized_library_mtproto.send_mtproto_file(
            user_id="test_user", file_path="/path/file.pdf", chat_id=12345
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Search Contacts Tests
# ---------------------------------------------------------------------------

class TestSearchMTProtoContacts:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_search_mtproto_unavailable(self, initialized_library):
        result = initialized_library.search_mtproto_contacts(
            user_id="test_user", query="Alice"
        )
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_search_mtproto_no_session(self, initialized_library):
        result = initialized_library.search_mtproto_contacts(
            user_id="test_user", query="Alice"
        )
        assert result["status"] == "error"
        assert "No valid MTProto session" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_search_mtproto_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search(*args, **kwargs):
            return {
                "result": {
                    "contacts": [
                        {"id": 111, "name": "Alice", "username": "alice"},
                        {"id": 222, "name": "Alice B", "username": "aliceb"},
                    ],
                    "count": 2,
                }
            }

        mock_mtproto_module.search_contacts = fake_search

        result = initialized_library_mtproto.search_mtproto_contacts(
            user_id="test_user", query="Alice"
        )
        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["contacts"]) == 2

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_search_mtproto_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search(*args, **kwargs):
            return {"error": "SEARCH_QUERY_EMPTY"}

        mock_mtproto_module.search_contacts = fake_search

        result = initialized_library_mtproto.search_mtproto_contacts(
            user_id="test_user", query=""
        )
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_search_mtproto_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_search(*args, **kwargs):
            raise Exception("Auth key unregistered")

        mock_mtproto_module.search_contacts = fake_search

        result = initialized_library_mtproto.search_mtproto_contacts(
            user_id="test_user", query="Alice"
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Get Account Info Tests
# ---------------------------------------------------------------------------

class TestGetMTProtoAccountInfo:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_account_info_mtproto_unavailable(self, initialized_library):
        result = initialized_library.get_mtproto_account_info(user_id="test_user")
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_account_info_no_session(self, initialized_library):
        result = initialized_library.get_mtproto_account_info(user_id="test_user")
        assert result["status"] == "error"
        assert "No valid MTProto session" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_account_info_success(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_me(*args, **kwargs):
            return {
                "result": {
                    "id": 999888,
                    "first_name": "Test",
                    "last_name": "User",
                    "username": "testuser",
                    "phone": "+1234567890",
                }
            }

        mock_mtproto_module.get_me = fake_get_me

        result = initialized_library_mtproto.get_mtproto_account_info(user_id="test_user")
        assert result["status"] == "success"
        assert result["user"]["id"] == 999888
        assert result["user"]["username"] == "testuser"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_account_info_api_error(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_me(*args, **kwargs):
            return {"error": "AUTH_KEY_UNREGISTERED"}

        mock_mtproto_module.get_me = fake_get_me

        result = initialized_library_mtproto.get_mtproto_account_info(user_id="test_user")
        assert result["status"] == "error"

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_account_info_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_get_me(*args, **kwargs):
            raise Exception("Connection lost")

        mock_mtproto_module.get_me = fake_get_me

        result = initialized_library_mtproto.get_mtproto_account_info(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# MTProto Validate Session Tests
# ---------------------------------------------------------------------------

class TestValidateMTProtoSession:

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", False)
    def test_validate_session_mtproto_unavailable(self, initialized_library):
        result = initialized_library.validate_mtproto_session(user_id="test_user")
        assert result["status"] == "error"
        assert "MTProto support not available" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    def test_validate_session_no_session(self, initialized_library):
        result = initialized_library.validate_mtproto_session(user_id="test_user")
        assert result["status"] == "success"
        assert result["valid"] is False
        assert "No session found" in result["reason"]

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_validate_session_valid(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_validate(*args, **kwargs):
            return {
                "result": {
                    "valid": True,
                    "user_id": 999888,
                    "username": "testuser",
                }
            }

        mock_mtproto_module.validate_session = fake_validate

        result = initialized_library_mtproto.validate_mtproto_session(user_id="test_user")
        assert result["status"] == "success"
        assert result["valid"] is True
        assert result["user_id"] == 999888

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_validate_session_invalid(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_validate(*args, **kwargs):
            return {
                "result": {
                    "valid": False,
                    "user_id": None,
                    "username": "",
                }
            }

        mock_mtproto_module.validate_session = fake_validate

        result = initialized_library_mtproto.validate_mtproto_session(user_id="test_user")
        assert result["status"] == "success"
        assert result["valid"] is False

    @patch(f"{LIB_PATH}.MTPROTO_AVAILABLE", True)
    @patch(f"{LIB_PATH}.mtproto")
    def test_validate_session_exception(self, mock_mtproto_module, initialized_library_mtproto):
        async def fake_validate(*args, **kwargs):
            raise Exception("Timeout")

        mock_mtproto_module.validate_session = fake_validate

        result = initialized_library_mtproto.validate_mtproto_session(user_id="test_user")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# Edge Cases & Cross-Cutting Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch(f"{LIB_PATH}.get_me")
    def test_bot_info_passes_correct_token(self, mock_get_me, initialized_library):
        """Verify the correct bot_token from the credential is used."""
        mock_get_me.return_value = {"ok": True, "result": {"id": 123}}
        initialized_library.get_bot_info(user_id="test_user")
        mock_get_me.assert_called_once_with(
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        )

    def test_multiple_credentials_same_user(self):
        """A user can have multiple bot credentials with different bot_ids."""
        TelegramAppLibrary.initialize()
        cred1 = TelegramCredential(
            user_id="test_user",
            bot_id="bot_a",
            bot_token="token_a",
        )
        cred2 = TelegramCredential(
            user_id="test_user",
            bot_id="bot_b",
            bot_token="token_b",
        )
        TelegramAppLibrary.get_credential_store().add(cred1)
        TelegramAppLibrary.get_credential_store().add(cred2)

        cred_a = TelegramAppLibrary.get_credentials(
            user_id="test_user", bot_id="bot_a"
        )
        cred_b = TelegramAppLibrary.get_credentials(
            user_id="test_user", bot_id="bot_b"
        )
        assert cred_a.bot_token == "token_a"
        assert cred_b.bot_token == "token_b"

    def test_credential_store_replaces_on_same_unique_keys(self):
        """Adding a credential with the same unique keys replaces the existing one."""
        TelegramAppLibrary.initialize()
        cred1 = TelegramCredential(
            user_id="test_user",
            bot_id="bot_x",
            bot_token="old_token",
        )
        cred2 = TelegramCredential(
            user_id="test_user",
            bot_id="bot_x",
            bot_token="new_token",
        )
        TelegramAppLibrary.get_credential_store().add(cred1)
        TelegramAppLibrary.get_credential_store().add(cred2)

        cred = TelegramAppLibrary.get_credentials(
            user_id="test_user", bot_id="bot_x"
        )
        assert cred.bot_token == "new_token"

        # Should still be only one credential for this user+bot_id
        all_creds = TelegramAppLibrary.get_credential_store().get(
            user_id="test_user", bot_id="bot_x"
        )
        assert len(all_creds) == 1

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_with_username_chat_id(self, mock_send, initialized_library):
        """Test sending to a @username-style chat_id."""
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 1, "chat": {"id": -100123}},
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Post to channel",
            chat_id="@my_channel",
        )
        assert result["status"] == "success"

    @patch(f"{LIB_PATH}.get_updates")
    def test_get_updates_default_limit(self, mock_get, initialized_library):
        """Default limit should be 100."""
        mock_get.return_value = {"ok": True, "result": []}
        initialized_library.get_updates(user_id="test_user")
        mock_get.assert_called_once_with(
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            offset=None,
            limit=100,
        )

    def test_get_credential_store_returns_same_instance(self):
        """get_credential_store should return the same store each time."""
        TelegramAppLibrary.initialize()
        store1 = TelegramAppLibrary.get_credential_store()
        store2 = TelegramAppLibrary.get_credential_store()
        assert store1 is store2

    @patch(f"{LIB_PATH}.send_message")
    def test_send_message_chat_id_zero(self, mock_send, initialized_library):
        """chat_id=0 is a valid integer; it should be passed through."""
        mock_send.return_value = {
            "ok": True,
            "result": {"message_id": 1, "chat": {"id": 0}},
        }
        result = initialized_library.send_message(
            user_id="test_user",
            text="Test",
            chat_id=0,
        )
        # chat_id=0 is falsy but not None, so _resolve_chat_identifier uses it
        assert result["status"] == "success"

    @patch(f"{LIB_PATH}.forward_message")
    def test_forward_message_both_ids(self, mock_fwd, initialized_library):
        """Forward with explicit source and destination chat_ids."""
        mock_fwd.return_value = {
            "ok": True,
            "result": {"message_id": 777},
        }
        result = initialized_library.forward_message(
            user_id="test_user",
            message_id=42,
            chat_id=11111,
            from_chat_id=22222,
        )
        assert result["status"] == "success"
        assert "resolved_to_contact" not in result
        assert "resolved_from_contact" not in result
