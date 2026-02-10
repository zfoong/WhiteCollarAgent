"""
Tests for Recall.ai external library.

Uses pytest with unittest.mock to mock the Recall.ai helper functions,
allowing all library methods to be tested without a live Recall.ai API
connection or any network access.

Usage:
    pytest core/external_libraries/recall/tests/test_recall_library.py -v
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.recall.credentials import RecallCredential
from core.external_libraries.recall.external_app_library import RecallAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset RecallAppLibrary state before each test."""
    RecallAppLibrary._initialized = False
    RecallAppLibrary._credential_store = None
    yield
    RecallAppLibrary._initialized = False
    RecallAppLibrary._credential_store = None


@pytest.fixture
def mock_credential():
    """Return a sample Recall.ai credential."""
    return RecallCredential(
        user_id="test_user",
        api_key="test_api_key_abc123",
        region="us",
    )


@pytest.fixture
def mock_credential_eu():
    """Return a sample Recall.ai credential for the EU region."""
    return RecallCredential(
        user_id="eu_user",
        api_key="eu_api_key_xyz789",
        region="eu",
    )


@pytest.fixture
def initialized_library(mock_credential):
    """Initialize the library and inject a mock credential store."""
    RecallAppLibrary.initialize()
    RecallAppLibrary.get_credential_store().add(mock_credential)
    return RecallAppLibrary


@pytest.fixture
def initialized_library_eu(mock_credential_eu):
    """Initialize the library and inject an EU credential."""
    RecallAppLibrary.initialize()
    RecallAppLibrary.get_credential_store().add(mock_credential_eu)
    return RecallAppLibrary


# ---------------------------------------------------------------------------
# Helper constants
# ---------------------------------------------------------------------------

HELPERS_MODULE = "core.external_libraries.recall.external_app_library"

SAMPLE_BOT_RESULT = {
    "bot_id": "bot_12345",
    "status": "joining_call",
    "meeting_url": "https://zoom.us/j/123456789",
    "video_url": None,
    "join_at": "2026-01-15T10:00:00Z",
}

SAMPLE_BOT_STATUS_RESULT = {
    "bot_id": "bot_12345",
    "status": "in_call_recording",
    "status_changes": [
        {"code": "ready", "created_at": "2026-01-15T09:59:00Z"},
        {"code": "joining_call", "created_at": "2026-01-15T10:00:00Z"},
        {"code": "in_call_recording", "created_at": "2026-01-15T10:00:30Z"},
    ],
    "meeting_url": "https://zoom.us/j/123456789",
    "video_url": "https://recall.ai/recordings/abc.mp4",
    "meeting_participants": [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ],
    "transcript": None,
}

SAMPLE_TRANSCRIPT = [
    {"speaker": "Alice", "words": [{"text": "Hello", "start_time": 0.0, "end_time": 0.5}]},
    {"speaker": "Bob", "words": [{"text": "Hi there", "start_time": 1.0, "end_time": 1.5}]},
]

SAMPLE_LIST_BOTS_RESULT = {
    "bots": [
        {"id": "bot_001", "status": "done"},
        {"id": "bot_002", "status": "in_call_recording"},
    ],
    "count": 2,
    "next": None,
    "previous": None,
}


# ===========================================================================
# Initialization & Credential Tests
# ===========================================================================

class TestInitialization:

    def test_initialize(self):
        assert not RecallAppLibrary._initialized
        RecallAppLibrary.initialize()
        assert RecallAppLibrary._initialized
        assert RecallAppLibrary._credential_store is not None

    def test_initialize_idempotent(self):
        RecallAppLibrary.initialize()
        store = RecallAppLibrary._credential_store
        RecallAppLibrary.initialize()
        assert RecallAppLibrary._credential_store is store

    def test_get_name(self):
        assert RecallAppLibrary.get_name() == "Recall"

    def test_get_credential_store_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            RecallAppLibrary.get_credential_store()

    def test_get_credential_store_after_init(self):
        RecallAppLibrary.initialize()
        store = RecallAppLibrary.get_credential_store()
        assert store is not None


class TestValidateConnection:

    def test_validate_no_credentials(self):
        RecallAppLibrary.initialize()
        assert RecallAppLibrary.validate_connection(user_id="nonexistent") is False

    def test_validate_with_credentials(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(user_id="test_user") is True

    def test_validate_with_wrong_user(self, initialized_library):
        assert initialized_library.validate_connection(user_id="other_user") is False


class TestGetCredentials:

    def test_get_credentials_found(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.user_id == "test_user"
        assert cred.api_key == "test_api_key_abc123"
        assert cred.region == "us"

    def test_get_credentials_not_found(self, initialized_library):
        cred = initialized_library.get_credentials(user_id="nonexistent")
        assert cred is None


# ===========================================================================
# Join Meeting Tests
# ===========================================================================

class TestJoinMeeting:

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_success(self, mock_create_bot, initialized_library):
        mock_create_bot.return_value = {"ok": True, "result": SAMPLE_BOT_RESULT}

        result = initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="https://zoom.us/j/123456789",
            bot_name="My Bot",
        )

        assert result["status"] == "success"
        assert result["bot"]["bot_id"] == "bot_12345"
        assert result["bot"]["status"] == "joining_call"
        mock_create_bot.assert_called_once_with(
            api_key="test_api_key_abc123",
            meeting_url="https://zoom.us/j/123456789",
            bot_name="My Bot",
            transcription_options={"provider": "deepgram"},
            recording_mode="speaker_view",
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_with_custom_options(self, mock_create_bot, initialized_library):
        mock_create_bot.return_value = {"ok": True, "result": SAMPLE_BOT_RESULT}

        result = initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="https://meet.google.com/abc-defg-hij",
            bot_name="Custom Bot",
            transcription_provider="assembly_ai",
            recording_mode="audio_only",
        )

        assert result["status"] == "success"
        mock_create_bot.assert_called_once_with(
            api_key="test_api_key_abc123",
            meeting_url="https://meet.google.com/abc-defg-hij",
            bot_name="Custom Bot",
            transcription_options={"provider": "assembly_ai"},
            recording_mode="audio_only",
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_default_bot_name(self, mock_create_bot, initialized_library):
        mock_create_bot.return_value = {"ok": True, "result": SAMPLE_BOT_RESULT}

        initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="https://zoom.us/j/123456789",
        )

        call_kwargs = mock_create_bot.call_args[1]
        assert call_kwargs["bot_name"] == "Meeting Assistant"

    def test_join_meeting_no_credential(self, initialized_library):
        result = initialized_library.join_meeting(
            user_id="nonexistent",
            meeting_url="https://zoom.us/j/123456789",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_api_error(self, mock_create_bot, initialized_library):
        mock_create_bot.return_value = {
            "error": "API error: 401",
            "details": "Invalid API key",
        }

        result = initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="https://zoom.us/j/123456789",
        )

        assert result["status"] == "error"
        assert "details" in result
        assert result["details"]["error"] == "API error: 401"

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_exception(self, mock_create_bot, initialized_library):
        mock_create_bot.side_effect = Exception("Network timeout")

        result = initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="https://zoom.us/j/123456789",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Network timeout" in result["reason"]

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_result_none(self, mock_create_bot, initialized_library):
        """When the helper returns ok but result is None."""
        mock_create_bot.return_value = {"ok": True, "result": None}

        result = initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="https://zoom.us/j/999",
        )

        assert result["status"] == "success"
        assert result["bot"] is None


# ===========================================================================
# Get Bot Status Tests
# ===========================================================================

class TestGetBotStatus:

    @patch(f"{HELPERS_MODULE}.get_bot")
    def test_get_bot_status_success(self, mock_get_bot, initialized_library):
        mock_get_bot.return_value = {"ok": True, "result": SAMPLE_BOT_STATUS_RESULT}

        result = initialized_library.get_bot_status(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["bot"]["bot_id"] == "bot_12345"
        assert result["bot"]["status"] == "in_call_recording"
        assert len(result["bot"]["meeting_participants"]) == 2
        mock_get_bot.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            region="us",
        )

    def test_get_bot_status_no_credential(self, initialized_library):
        result = initialized_library.get_bot_status(
            user_id="nonexistent",
            bot_id="bot_12345",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.get_bot")
    def test_get_bot_status_api_error(self, mock_get_bot, initialized_library):
        mock_get_bot.return_value = {
            "error": "API error: 404",
            "details": "Bot not found",
        }

        result = initialized_library.get_bot_status(
            user_id="test_user",
            bot_id="bot_nonexistent",
        )

        assert result["status"] == "error"
        assert "details" in result
        assert result["details"]["error"] == "API error: 404"

    @patch(f"{HELPERS_MODULE}.get_bot")
    def test_get_bot_status_exception(self, mock_get_bot, initialized_library):
        mock_get_bot.side_effect = Exception("Connection refused")

        result = initialized_library.get_bot_status(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Connection refused" in result["reason"]


# ===========================================================================
# List Bots Tests
# ===========================================================================

class TestListBots:

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_success(self, mock_list_bots, initialized_library):
        mock_list_bots.return_value = {"ok": True, "result": SAMPLE_LIST_BOTS_RESULT}

        result = initialized_library.list_bots(user_id="test_user")

        assert result["status"] == "success"
        assert result["bots"]["count"] == 2
        assert len(result["bots"]["bots"]) == 2
        mock_list_bots.assert_called_once_with(
            api_key="test_api_key_abc123",
            page_size=50,
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_custom_page_size(self, mock_list_bots, initialized_library):
        mock_list_bots.return_value = {"ok": True, "result": SAMPLE_LIST_BOTS_RESULT}

        initialized_library.list_bots(user_id="test_user", page_size=10)

        mock_list_bots.assert_called_once_with(
            api_key="test_api_key_abc123",
            page_size=10,
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_empty(self, mock_list_bots, initialized_library):
        mock_list_bots.return_value = {
            "ok": True,
            "result": {"bots": [], "count": 0, "next": None, "previous": None},
        }

        result = initialized_library.list_bots(user_id="test_user")

        assert result["status"] == "success"
        assert result["bots"]["count"] == 0
        assert result["bots"]["bots"] == []

    def test_list_bots_no_credential(self, initialized_library):
        result = initialized_library.list_bots(user_id="nonexistent")
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_api_error(self, mock_list_bots, initialized_library):
        mock_list_bots.return_value = {
            "error": "API error: 500",
            "details": "Internal server error",
        }

        result = initialized_library.list_bots(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_exception(self, mock_list_bots, initialized_library):
        mock_list_bots.side_effect = Exception("DNS failure")

        result = initialized_library.list_bots(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ===========================================================================
# Leave Meeting Tests
# ===========================================================================

class TestLeaveMeeting:

    @patch(f"{HELPERS_MODULE}.leave_meeting")
    def test_leave_meeting_success(self, mock_leave, initialized_library):
        mock_leave.return_value = {
            "ok": True,
            "result": {"left": True, "bot_id": "bot_12345"},
        }

        result = initialized_library.leave_meeting(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["result"]["left"] is True
        mock_leave.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            region="us",
        )

    def test_leave_meeting_no_credential(self, initialized_library):
        result = initialized_library.leave_meeting(
            user_id="nonexistent",
            bot_id="bot_12345",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.leave_meeting")
    def test_leave_meeting_api_error(self, mock_leave, initialized_library):
        mock_leave.return_value = {
            "error": "API error: 409",
            "details": "Bot already left",
        }

        result = initialized_library.leave_meeting(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.leave_meeting")
    def test_leave_meeting_exception(self, mock_leave, initialized_library):
        mock_leave.side_effect = Exception("Service unavailable")

        result = initialized_library.leave_meeting(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ===========================================================================
# Delete Bot Tests
# ===========================================================================

class TestDeleteBot:

    @patch(f"{HELPERS_MODULE}.delete_bot")
    def test_delete_bot_success(self, mock_delete, initialized_library):
        mock_delete.return_value = {
            "ok": True,
            "result": {"deleted": True, "bot_id": "bot_12345"},
        }

        result = initialized_library.delete_bot(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["deleted"] is True
        mock_delete.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            region="us",
        )

    def test_delete_bot_no_credential(self, initialized_library):
        result = initialized_library.delete_bot(
            user_id="nonexistent",
            bot_id="bot_12345",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.delete_bot")
    def test_delete_bot_api_error(self, mock_delete, initialized_library):
        mock_delete.return_value = {
            "error": "API error: 404",
            "details": "Bot not found",
        }

        result = initialized_library.delete_bot(
            user_id="test_user",
            bot_id="bot_nonexistent",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.delete_bot")
    def test_delete_bot_exception(self, mock_delete, initialized_library):
        mock_delete.side_effect = Exception("Permission denied")

        result = initialized_library.delete_bot(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ===========================================================================
# Get Transcript Tests
# ===========================================================================

class TestGetTranscript:

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_success(self, mock_get_transcript, initialized_library):
        mock_get_transcript.return_value = {
            "ok": True,
            "result": {"transcript": SAMPLE_TRANSCRIPT},
        }

        result = initialized_library.get_transcript(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["transcript"] == SAMPLE_TRANSCRIPT
        assert len(result["transcript"]) == 2
        assert result["transcript"][0]["speaker"] == "Alice"
        mock_get_transcript.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_empty(self, mock_get_transcript, initialized_library):
        mock_get_transcript.return_value = {
            "ok": True,
            "result": {"transcript": []},
        }

        result = initialized_library.get_transcript(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["transcript"] == []

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_none_in_result(self, mock_get_transcript, initialized_library):
        """When result exists but transcript key is missing."""
        mock_get_transcript.return_value = {
            "ok": True,
            "result": {},
        }

        result = initialized_library.get_transcript(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["transcript"] is None

    def test_get_transcript_no_credential(self, initialized_library):
        result = initialized_library.get_transcript(
            user_id="nonexistent",
            bot_id="bot_12345",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_api_error(self, mock_get_transcript, initialized_library):
        mock_get_transcript.return_value = {
            "error": "API error: 404",
            "details": "Bot not found",
        }

        result = initialized_library.get_transcript(
            user_id="test_user",
            bot_id="bot_nonexistent",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_exception(self, mock_get_transcript, initialized_library):
        mock_get_transcript.side_effect = Exception("Timeout exceeded")

        result = initialized_library.get_transcript(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ===========================================================================
# Get Recording Tests
# ===========================================================================

class TestGetRecording:

    @patch(f"{HELPERS_MODULE}.get_recording")
    def test_get_recording_success(self, mock_get_recording, initialized_library):
        mock_get_recording.return_value = {
            "ok": True,
            "result": {
                "video_url": "https://recall.ai/recordings/abc.mp4",
                "status": "done",
            },
        }

        result = initialized_library.get_recording(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["recording"]["video_url"] == "https://recall.ai/recordings/abc.mp4"
        assert result["recording"]["status"] == "done"
        mock_get_recording.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.get_recording")
    def test_get_recording_not_ready(self, mock_get_recording, initialized_library):
        """Recording is not yet available (video_url is None)."""
        mock_get_recording.return_value = {
            "ok": True,
            "result": {
                "video_url": None,
                "status": "in_call_recording",
            },
        }

        result = initialized_library.get_recording(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "success"
        assert result["recording"]["video_url"] is None

    def test_get_recording_no_credential(self, initialized_library):
        result = initialized_library.get_recording(
            user_id="nonexistent",
            bot_id="bot_12345",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.get_recording")
    def test_get_recording_api_error(self, mock_get_recording, initialized_library):
        mock_get_recording.return_value = {
            "error": "API error: 404",
            "details": "Bot not found",
        }

        result = initialized_library.get_recording(
            user_id="test_user",
            bot_id="bot_nonexistent",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.get_recording")
    def test_get_recording_exception(self, mock_get_recording, initialized_library):
        mock_get_recording.side_effect = Exception("SSL error")

        result = initialized_library.get_recording(
            user_id="test_user",
            bot_id="bot_12345",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ===========================================================================
# Send Chat Message Tests
# ===========================================================================

class TestSendChatMessage:

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_success(self, mock_send, initialized_library):
        mock_send.return_value = {
            "ok": True,
            "result": {"sent": True, "message": "Hello everyone!"},
        }

        result = initialized_library.send_chat_message(
            user_id="test_user",
            bot_id="bot_12345",
            message="Hello everyone!",
        )

        assert result["status"] == "success"
        assert result["sent"] is True
        assert result["message"] == "Hello everyone!"
        mock_send.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            message="Hello everyone!",
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_empty_string(self, mock_send, initialized_library):
        """Sending an empty message should still forward to the helper."""
        mock_send.return_value = {"ok": True, "result": {"sent": True, "message": ""}}

        result = initialized_library.send_chat_message(
            user_id="test_user",
            bot_id="bot_12345",
            message="",
        )

        assert result["status"] == "success"
        assert result["message"] == ""

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_long_text(self, mock_send, initialized_library):
        """Send a very long message."""
        long_message = "A" * 5000
        mock_send.return_value = {
            "ok": True,
            "result": {"sent": True, "message": long_message},
        }

        result = initialized_library.send_chat_message(
            user_id="test_user",
            bot_id="bot_12345",
            message=long_message,
        )

        assert result["status"] == "success"
        assert result["message"] == long_message

    def test_send_chat_message_no_credential(self, initialized_library):
        result = initialized_library.send_chat_message(
            user_id="nonexistent",
            bot_id="bot_12345",
            message="Hello!",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_api_error(self, mock_send, initialized_library):
        mock_send.return_value = {
            "error": "API error: 400",
            "details": "Bot not in a meeting",
        }

        result = initialized_library.send_chat_message(
            user_id="test_user",
            bot_id="bot_12345",
            message="Hello!",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_exception(self, mock_send, initialized_library):
        mock_send.side_effect = Exception("Write error")

        result = initialized_library.send_chat_message(
            user_id="test_user",
            bot_id="bot_12345",
            message="Hello!",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ===========================================================================
# Speak In Meeting Tests
# ===========================================================================

class TestSpeakInMeeting:

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_success(self, mock_output, initialized_library):
        mock_output.return_value = {"ok": True, "result": {"audio_sent": True}}

        result = initialized_library.speak_in_meeting(
            user_id="test_user",
            bot_id="bot_12345",
            audio_data="base64encodedaudiodata==",
        )

        assert result["status"] == "success"
        assert result["audio_sent"] is True
        mock_output.assert_called_once_with(
            api_key="test_api_key_abc123",
            bot_id="bot_12345",
            audio_data="base64encodedaudiodata==",
            audio_format="wav",
            region="us",
        )

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_mp3_format(self, mock_output, initialized_library):
        mock_output.return_value = {"ok": True, "result": {"audio_sent": True}}

        initialized_library.speak_in_meeting(
            user_id="test_user",
            bot_id="bot_12345",
            audio_data="base64mp3data==",
            audio_format="mp3",
        )

        call_kwargs = mock_output.call_args[1]
        assert call_kwargs["audio_format"] == "mp3"

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_default_format_is_wav(self, mock_output, initialized_library):
        mock_output.return_value = {"ok": True, "result": {"audio_sent": True}}

        initialized_library.speak_in_meeting(
            user_id="test_user",
            bot_id="bot_12345",
            audio_data="base64data==",
        )

        call_kwargs = mock_output.call_args[1]
        assert call_kwargs["audio_format"] == "wav"

    def test_speak_in_meeting_no_credential(self, initialized_library):
        result = initialized_library.speak_in_meeting(
            user_id="nonexistent",
            bot_id="bot_12345",
            audio_data="base64data==",
        )
        assert result["status"] == "error"
        assert "No Recall.ai API key found" in result["reason"]

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_api_error(self, mock_output, initialized_library):
        mock_output.return_value = {
            "error": "API error: 400",
            "details": "Audio output not enabled",
        }

        result = initialized_library.speak_in_meeting(
            user_id="test_user",
            bot_id="bot_12345",
            audio_data="base64data==",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_exception(self, mock_output, initialized_library):
        mock_output.side_effect = Exception("Audio codec error")

        result = initialized_library.speak_in_meeting(
            user_id="test_user",
            bot_id="bot_12345",
            audio_data="base64data==",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Audio codec error" in result["reason"]


# ===========================================================================
# Credential Model Tests
# ===========================================================================

class TestRecallCredential:

    def test_credential_defaults(self):
        cred = RecallCredential(user_id="u1")
        assert cred.api_key == ""
        assert cred.region == "us"

    def test_credential_with_all_fields(self):
        cred = RecallCredential(
            user_id="u1",
            api_key="key123",
            region="eu",
        )
        assert cred.user_id == "u1"
        assert cred.api_key == "key123"
        assert cred.region == "eu"

    def test_credential_unique_keys(self):
        assert RecallCredential.UNIQUE_KEYS == ("user_id",)

    def test_credential_to_dict(self):
        cred = RecallCredential(
            user_id="u1",
            api_key="key123",
            region="us",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["api_key"] == "key123"
        assert d["region"] == "us"

    def test_credential_to_dict_default_values(self):
        cred = RecallCredential(user_id="u1")
        d = cred.to_dict()
        assert d["api_key"] == ""
        assert d["region"] == "us"


# ===========================================================================
# Region / EU Credential Tests
# ===========================================================================

class TestRegionHandling:

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_eu_region(self, mock_create_bot, initialized_library_eu):
        mock_create_bot.return_value = {"ok": True, "result": SAMPLE_BOT_RESULT}

        initialized_library_eu.join_meeting(
            user_id="eu_user",
            meeting_url="https://teams.microsoft.com/meeting/123",
        )

        call_kwargs = mock_create_bot.call_args[1]
        assert call_kwargs["region"] == "eu"
        assert call_kwargs["api_key"] == "eu_api_key_xyz789"

    @patch(f"{HELPERS_MODULE}.get_bot")
    def test_get_bot_status_eu_region(self, mock_get_bot, initialized_library_eu):
        mock_get_bot.return_value = {"ok": True, "result": SAMPLE_BOT_STATUS_RESULT}

        initialized_library_eu.get_bot_status(
            user_id="eu_user",
            bot_id="bot_eu_001",
        )

        call_kwargs = mock_get_bot.call_args[1]
        assert call_kwargs["region"] == "eu"

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_eu_region(self, mock_list_bots, initialized_library_eu):
        mock_list_bots.return_value = {"ok": True, "result": SAMPLE_LIST_BOTS_RESULT}

        initialized_library_eu.list_bots(user_id="eu_user")

        call_kwargs = mock_list_bots.call_args[1]
        assert call_kwargs["region"] == "eu"

    @patch(f"{HELPERS_MODULE}.leave_meeting")
    def test_leave_meeting_eu_region(self, mock_leave, initialized_library_eu):
        mock_leave.return_value = {"ok": True, "result": {"left": True, "bot_id": "bot_eu_001"}}

        initialized_library_eu.leave_meeting(
            user_id="eu_user",
            bot_id="bot_eu_001",
        )

        call_kwargs = mock_leave.call_args[1]
        assert call_kwargs["region"] == "eu"

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_eu_region(self, mock_send, initialized_library_eu):
        mock_send.return_value = {"ok": True, "result": {"sent": True, "message": "Hi"}}

        initialized_library_eu.send_chat_message(
            user_id="eu_user",
            bot_id="bot_eu_001",
            message="Hi",
        )

        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["region"] == "eu"

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_eu_region(self, mock_get_transcript, initialized_library_eu):
        mock_get_transcript.return_value = {"ok": True, "result": {"transcript": []}}

        initialized_library_eu.get_transcript(
            user_id="eu_user",
            bot_id="bot_eu_001",
        )

        call_kwargs = mock_get_transcript.call_args[1]
        assert call_kwargs["region"] == "eu"

    @patch(f"{HELPERS_MODULE}.get_recording")
    def test_get_recording_eu_region(self, mock_get_recording, initialized_library_eu):
        mock_get_recording.return_value = {
            "ok": True,
            "result": {"video_url": "https://eu.recall.ai/rec.mp4", "status": "done"},
        }

        initialized_library_eu.get_recording(
            user_id="eu_user",
            bot_id="bot_eu_001",
        )

        call_kwargs = mock_get_recording.call_args[1]
        assert call_kwargs["region"] == "eu"

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_eu_region(self, mock_output, initialized_library_eu):
        mock_output.return_value = {"ok": True, "result": {"audio_sent": True}}

        initialized_library_eu.speak_in_meeting(
            user_id="eu_user",
            bot_id="bot_eu_001",
            audio_data="data==",
        )

        call_kwargs = mock_output.call_args[1]
        assert call_kwargs["region"] == "eu"


# ===========================================================================
# Edge Cases & Error Handling Tests
# ===========================================================================

class TestEdgeCases:

    def test_all_methods_fail_before_init(self):
        """All methods should raise RuntimeError if initialize() was not called."""
        with pytest.raises(RuntimeError, match="not initialized"):
            RecallAppLibrary.validate_connection(user_id="test_user")

        with pytest.raises(RuntimeError, match="not initialized"):
            RecallAppLibrary.get_credentials(user_id="test_user")

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_handles_exception_from_get_credentials(
        self, mock_create_bot, initialized_library
    ):
        """If get_credentials raises, join_meeting catches it."""
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Store corrupted")
        ):
            result = initialized_library.join_meeting(
                user_id="test_user",
                meeting_url="https://zoom.us/j/123",
            )
            assert result["status"] == "error"
            assert "Unexpected error" in result["reason"]

    @patch(f"{HELPERS_MODULE}.get_bot")
    def test_get_bot_status_handles_credential_exception(
        self, mock_get_bot, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Read error")
        ):
            result = initialized_library.get_bot_status(
                user_id="test_user",
                bot_id="bot_12345",
            )
            assert result["status"] == "error"
            assert "Unexpected error" in result["reason"]

    @patch(f"{HELPERS_MODULE}.list_bots")
    def test_list_bots_handles_credential_exception(
        self, mock_list_bots, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("File locked")
        ):
            result = initialized_library.list_bots(user_id="test_user")
            assert result["status"] == "error"
            assert "Unexpected error" in result["reason"]

    @patch(f"{HELPERS_MODULE}.leave_meeting")
    def test_leave_meeting_handles_credential_exception(
        self, mock_leave, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Corrupt")
        ):
            result = initialized_library.leave_meeting(
                user_id="test_user",
                bot_id="bot_12345",
            )
            assert result["status"] == "error"

    @patch(f"{HELPERS_MODULE}.delete_bot")
    def test_delete_bot_handles_credential_exception(
        self, mock_delete, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Corrupt")
        ):
            result = initialized_library.delete_bot(
                user_id="test_user",
                bot_id="bot_12345",
            )
            assert result["status"] == "error"

    @patch(f"{HELPERS_MODULE}.get_transcript")
    def test_get_transcript_handles_credential_exception(
        self, mock_get_transcript, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Corrupt")
        ):
            result = initialized_library.get_transcript(
                user_id="test_user",
                bot_id="bot_12345",
            )
            assert result["status"] == "error"

    @patch(f"{HELPERS_MODULE}.get_recording")
    def test_get_recording_handles_credential_exception(
        self, mock_get_recording, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Corrupt")
        ):
            result = initialized_library.get_recording(
                user_id="test_user",
                bot_id="bot_12345",
            )
            assert result["status"] == "error"

    @patch(f"{HELPERS_MODULE}.send_chat_message")
    def test_send_chat_message_handles_credential_exception(
        self, mock_send, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Corrupt")
        ):
            result = initialized_library.send_chat_message(
                user_id="test_user",
                bot_id="bot_12345",
                message="hello",
            )
            assert result["status"] == "error"

    @patch(f"{HELPERS_MODULE}.output_audio")
    def test_speak_in_meeting_handles_credential_exception(
        self, mock_output, initialized_library
    ):
        with patch.object(
            RecallAppLibrary, "get_credentials", side_effect=Exception("Corrupt")
        ):
            result = initialized_library.speak_in_meeting(
                user_id="test_user",
                bot_id="bot_12345",
                audio_data="data==",
            )
            assert result["status"] == "error"

    def test_multiple_users_isolated(self):
        """Credentials for different users should not interfere."""
        RecallAppLibrary.initialize()
        store = RecallAppLibrary.get_credential_store()

        cred_a = RecallCredential(user_id="user_a", api_key="key_a", region="us")
        cred_b = RecallCredential(user_id="user_b", api_key="key_b", region="eu")
        store.add(cred_a)
        store.add(cred_b)

        assert RecallAppLibrary.validate_connection(user_id="user_a") is True
        assert RecallAppLibrary.validate_connection(user_id="user_b") is True
        assert RecallAppLibrary.validate_connection(user_id="user_c") is False

        result_a = RecallAppLibrary.get_credentials(user_id="user_a")
        result_b = RecallAppLibrary.get_credentials(user_id="user_b")

        assert result_a.api_key == "key_a"
        assert result_a.region == "us"
        assert result_b.api_key == "key_b"
        assert result_b.region == "eu"

    def test_credential_overwrite_by_unique_key(self):
        """Adding a credential with the same user_id should overwrite it."""
        RecallAppLibrary.initialize()
        store = RecallAppLibrary.get_credential_store()

        cred_v1 = RecallCredential(user_id="user_x", api_key="old_key", region="us")
        cred_v2 = RecallCredential(user_id="user_x", api_key="new_key", region="eu")
        store.add(cred_v1)
        store.add(cred_v2)

        result = RecallAppLibrary.get_credentials(user_id="user_x")
        assert result.api_key == "new_key"
        assert result.region == "eu"

    @patch(f"{HELPERS_MODULE}.create_bot")
    def test_join_meeting_returns_error_key_in_result(self, mock_create_bot, initialized_library):
        """When the helper result contains an 'error' key (not 'ok')."""
        mock_create_bot.return_value = {
            "error": "Invalid meeting URL format",
        }

        result = initialized_library.join_meeting(
            user_id="test_user",
            meeting_url="not-a-valid-url",
        )

        assert result["status"] == "error"
        assert result["details"]["error"] == "Invalid meeting URL format"

    @patch(f"{HELPERS_MODULE}.delete_bot")
    def test_delete_bot_returns_true_regardless_of_helper_result(
        self, mock_delete, initialized_library
    ):
        """delete_bot always returns {"deleted": True} on success."""
        mock_delete.return_value = {
            "ok": True,
            "result": {"deleted": True, "bot_id": "bot_xyz"},
        }

        result = initialized_library.delete_bot(
            user_id="test_user",
            bot_id="bot_xyz",
        )

        assert result["deleted"] is True
        # The library returns {"status": "success", "deleted": True}
        # regardless of the helper's result content
        assert "bot" not in result
