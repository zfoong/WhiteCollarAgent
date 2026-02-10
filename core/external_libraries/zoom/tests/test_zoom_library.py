"""
Tests for Zoom external library.

Uses pytest with unittest.mock to mock the Zoom helper functions,
allowing all library methods to be tested without network access.

Usage:
    pytest core/external_libraries/zoom/tests/test_zoom_library.py -v
"""
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.zoom.credentials import ZoomCredential
from core.external_libraries.zoom.external_app_library import ZoomAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset ZoomAppLibrary state before each test."""
    ZoomAppLibrary._initialized = False
    ZoomAppLibrary._credential_store = None
    yield
    ZoomAppLibrary._initialized = False
    ZoomAppLibrary._credential_store = None


@pytest.fixture
def mock_credential():
    """Return a sample Zoom credential with a valid (non-expired) token."""
    return ZoomCredential(
        user_id="test_user",
        access_token="fake_access_token_abc123",
        refresh_token="fake_refresh_token_xyz789",
        token_expiry=time.time() + 3600,  # 1 hour from now
        zoom_user_id="zoom_user_001",
        email="testuser@example.com",
        display_name="Test User",
        account_id="account_001",
    )


@pytest.fixture
def expired_credential():
    """Return a sample Zoom credential with an expired token."""
    return ZoomCredential(
        user_id="test_user",
        access_token="old_access_token",
        refresh_token="fake_refresh_token_xyz789",
        token_expiry=time.time() - 600,  # expired 10 minutes ago
        zoom_user_id="zoom_user_001",
        email="testuser@example.com",
        display_name="Test User",
        account_id="account_001",
    )


@pytest.fixture
def initialized_library(mock_credential):
    """Initialize the library and inject a mock credential store."""
    ZoomAppLibrary.initialize()
    ZoomAppLibrary.get_credential_store().add(mock_credential)
    return ZoomAppLibrary


# ---------------------------------------------------------------------------
# Initialization & Credential Tests
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_initialize(self):
        assert not ZoomAppLibrary._initialized
        ZoomAppLibrary.initialize()
        assert ZoomAppLibrary._initialized
        assert ZoomAppLibrary._credential_store is not None

    def test_initialize_idempotent(self):
        ZoomAppLibrary.initialize()
        store = ZoomAppLibrary._credential_store
        ZoomAppLibrary.initialize()
        assert ZoomAppLibrary._credential_store is store

    def test_get_name(self):
        assert ZoomAppLibrary.get_name() == "Zoom"

    def test_get_credential_store_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            ZoomAppLibrary.get_credential_store()

    def test_get_credential_store_after_init(self):
        ZoomAppLibrary.initialize()
        store = ZoomAppLibrary.get_credential_store()
        assert store is not None


class TestValidateConnection:

    def test_validate_no_credentials(self):
        ZoomAppLibrary.initialize()
        assert ZoomAppLibrary.validate_connection(user_id="nonexistent") is False

    def test_validate_with_credentials(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(user_id="test_user") is True

    def test_validate_with_wrong_user(self, initialized_library):
        assert initialized_library.validate_connection(user_id="other_user") is False

    def test_validate_with_zoom_user_id(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(
            user_id="test_user",
            zoom_user_id="zoom_user_001"
        ) is True

    def test_validate_with_wrong_zoom_user_id(self, initialized_library):
        assert initialized_library.validate_connection(
            user_id="test_user",
            zoom_user_id="wrong_zoom_id"
        ) is False


class TestGetCredentials:

    def test_get_credentials_found(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.user_id == "test_user"
        assert cred.zoom_user_id == "zoom_user_001"
        assert cred.access_token == "fake_access_token_abc123"

    def test_get_credentials_not_found(self, initialized_library):
        cred = initialized_library.get_credentials(user_id="nonexistent")
        assert cred is None

    def test_get_credentials_with_zoom_user_id(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            zoom_user_id="zoom_user_001"
        )
        assert cred is not None
        assert cred.zoom_user_id == "zoom_user_001"

    def test_get_credentials_wrong_zoom_user_id(self, initialized_library):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            zoom_user_id="nonexistent_zoom_id"
        )
        assert cred is None


# ---------------------------------------------------------------------------
# Token Management Tests
# ---------------------------------------------------------------------------

class TestEnsureValidToken:

    def test_returns_none_when_no_credential(self, initialized_library):
        result = initialized_library.ensure_valid_token(user_id="nonexistent")
        assert result is None

    def test_returns_credential_when_token_valid(self, initialized_library, mock_credential):
        result = initialized_library.ensure_valid_token(user_id="test_user")
        assert result is not None
        assert result.access_token == "fake_access_token_abc123"

    @patch("core.external_libraries.zoom.external_app_library.refresh_access_token")
    def test_refreshes_expired_token(self, mock_refresh, expired_credential):
        """When token is expired and refresh succeeds, credential is updated."""
        ZoomAppLibrary.initialize()
        ZoomAppLibrary.get_credential_store().add(expired_credential)

        new_expiry = time.time() + 3600
        mock_refresh.return_value = ("new_access_token", "new_refresh_token", new_expiry)

        with patch("core.config.ZOOM_CLIENT_ID", "cid"), \
             patch("core.config.ZOOM_CLIENT_SECRET", "csec"):
            result = ZoomAppLibrary.ensure_valid_token(user_id="test_user")

        assert result is not None
        assert result.access_token == "new_access_token"
        assert result.refresh_token == "new_refresh_token"
        assert result.token_expiry == new_expiry
        mock_refresh.assert_called_once_with(
            client_id="cid",
            client_secret="csec",
            refresh_token="fake_refresh_token_xyz789",
        )

    @patch("core.external_libraries.zoom.external_app_library.refresh_access_token")
    def test_refresh_failure_returns_original_credential(self, mock_refresh, expired_credential):
        """When token refresh fails, the original (expired) credential is still returned."""
        ZoomAppLibrary.initialize()
        ZoomAppLibrary.get_credential_store().add(expired_credential)

        mock_refresh.return_value = None

        with patch("core.config.ZOOM_CLIENT_ID", "cid"), \
             patch("core.config.ZOOM_CLIENT_SECRET", "csec"):
            result = ZoomAppLibrary.ensure_valid_token(user_id="test_user")

        assert result is not None
        assert result.access_token == "old_access_token"  # unchanged

    def test_no_refresh_when_token_not_expired(self, initialized_library, mock_credential):
        """When token is still valid, no refresh is attempted."""
        with patch("core.external_libraries.zoom.external_app_library.refresh_access_token") as mock_refresh:
            result = initialized_library.ensure_valid_token(user_id="test_user")

        assert result is not None
        assert result.access_token == "fake_access_token_abc123"
        mock_refresh.assert_not_called()

    @patch("core.external_libraries.zoom.external_app_library.refresh_access_token")
    def test_token_expiry_none_triggers_refresh(self, mock_refresh):
        """When token_expiry is None, the token is treated as expired."""
        cred = ZoomCredential(
            user_id="test_user",
            access_token="old_token",
            refresh_token="ref_tok",
            token_expiry=None,
            zoom_user_id="zoom_user_001",
        )
        ZoomAppLibrary.initialize()
        ZoomAppLibrary.get_credential_store().add(cred)

        new_expiry = time.time() + 3600
        mock_refresh.return_value = ("refreshed_token", "new_ref", new_expiry)

        with patch("core.config.ZOOM_CLIENT_ID", "cid"), \
             patch("core.config.ZOOM_CLIENT_SECRET", "csec"):
            result = ZoomAppLibrary.ensure_valid_token(user_id="test_user")

        assert result.access_token == "refreshed_token"
        mock_refresh.assert_called_once()

    @patch("core.external_libraries.zoom.external_app_library.refresh_access_token")
    def test_no_refresh_token_means_no_refresh_attempt(self, mock_refresh):
        """When refresh_token is empty, no refresh is attempted even if token is expired."""
        cred = ZoomCredential(
            user_id="test_user",
            access_token="old_token",
            refresh_token="",
            token_expiry=time.time() - 600,  # expired
            zoom_user_id="zoom_user_001",
        )
        ZoomAppLibrary.initialize()
        ZoomAppLibrary.get_credential_store().add(cred)

        result = ZoomAppLibrary.ensure_valid_token(user_id="test_user")

        assert result is not None
        assert result.access_token == "old_token"
        mock_refresh.assert_not_called()

    def test_ensure_valid_token_with_zoom_user_id(self, initialized_library, mock_credential):
        result = initialized_library.ensure_valid_token(
            user_id="test_user",
            zoom_user_id="zoom_user_001"
        )
        assert result is not None
        assert result.zoom_user_id == "zoom_user_001"


# ---------------------------------------------------------------------------
# User Operations Tests
# ---------------------------------------------------------------------------

class TestGetMyProfile:

    @patch("core.external_libraries.zoom.external_app_library.get_user_profile")
    def test_get_profile_success(self, mock_profile, initialized_library):
        mock_profile.return_value = {
            "ok": True,
            "result": {
                "zoom_user_id": "zoom_user_001",
                "email": "testuser@example.com",
                "display_name": "Test User",
                "first_name": "Test",
                "last_name": "User",
                "account_id": "account_001",
                "type": 2,
                "pic_url": "https://example.com/pic.jpg",
                "timezone": "America/New_York",
                "pmi": 1234567890,
            },
        }

        result = initialized_library.get_my_profile(user_id="test_user")

        assert result["status"] == "success"
        assert result["profile"]["zoom_user_id"] == "zoom_user_001"
        assert result["profile"]["email"] == "testuser@example.com"
        mock_profile.assert_called_once_with(access_token="fake_access_token_abc123")

    def test_get_profile_no_credential(self, initialized_library):
        result = initialized_library.get_my_profile(user_id="nonexistent")

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_user_profile")
    def test_get_profile_api_error(self, mock_profile, initialized_library):
        mock_profile.return_value = {
            "error": "API error: 401",
            "details": "Invalid access token",
        }

        result = initialized_library.get_my_profile(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.get_user_profile")
    def test_get_profile_exception(self, mock_profile, initialized_library):
        mock_profile.side_effect = Exception("Network timeout")

        result = initialized_library.get_my_profile(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_user_profile")
    def test_get_profile_with_zoom_user_id(self, mock_profile, initialized_library):
        mock_profile.return_value = {
            "ok": True,
            "result": {"zoom_user_id": "zoom_user_001", "email": "test@test.com"},
        }

        result = initialized_library.get_my_profile(
            user_id="test_user",
            zoom_user_id="zoom_user_001"
        )

        assert result["status"] == "success"


class TestListUsers:

    @patch("core.external_libraries.zoom.external_app_library.list_users")
    def test_list_users_success(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "result": {
                "users": [
                    {"id": "u1", "email": "user1@example.com"},
                    {"id": "u2", "email": "user2@example.com"},
                ],
                "page_count": 1,
                "page_number": 1,
                "page_size": 30,
                "total_records": 2,
            },
        }

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "success"
        assert len(result["users"]["users"]) == 2
        assert result["users"]["total_records"] == 2
        mock_list.assert_called_once_with(
            access_token="fake_access_token_abc123",
            status="active",
            page_size=30,
        )

    def test_list_users_no_credential(self, initialized_library):
        result = initialized_library.list_users(user_id="nonexistent")

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.list_users")
    def test_list_users_api_error(self, mock_list, initialized_library):
        mock_list.return_value = {
            "error": "API error: 403",
            "details": "Insufficient permissions",
        }

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.list_users")
    def test_list_users_exception(self, mock_list, initialized_library):
        mock_list.side_effect = Exception("Connection error")

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.list_users")
    def test_list_users_custom_params(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "result": {"users": [], "page_count": 0, "page_number": 1, "page_size": 10, "total_records": 0},
        }

        result = initialized_library.list_users(
            user_id="test_user",
            status="inactive",
            page_size=10,
        )

        assert result["status"] == "success"
        mock_list.assert_called_once_with(
            access_token="fake_access_token_abc123",
            status="inactive",
            page_size=10,
        )


# ---------------------------------------------------------------------------
# Meeting Operations Tests
# ---------------------------------------------------------------------------

class TestListMeetings:

    @patch("core.external_libraries.zoom.external_app_library.list_meetings")
    def test_list_meetings_success(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "result": {
                "meetings": [
                    {"id": 111, "topic": "Standup", "start_time": "2026-02-10T09:00:00Z"},
                    {"id": 222, "topic": "Sprint Review", "start_time": "2026-02-11T14:00:00Z"},
                ],
                "page_count": 1,
                "page_number": 1,
                "page_size": 30,
                "total_records": 2,
            },
        }

        result = initialized_library.list_meetings(user_id="test_user")

        assert result["status"] == "success"
        assert len(result["meetings"]["meetings"]) == 2
        mock_list.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_type="scheduled",
            page_size=30,
        )

    def test_list_meetings_no_credential(self, initialized_library):
        result = initialized_library.list_meetings(user_id="nonexistent")

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.list_meetings")
    def test_list_meetings_api_error(self, mock_list, initialized_library):
        mock_list.return_value = {
            "error": "API error: 404",
            "details": "User not found",
        }

        result = initialized_library.list_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.list_meetings")
    def test_list_meetings_exception(self, mock_list, initialized_library):
        mock_list.side_effect = Exception("Timeout")

        result = initialized_library.list_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.list_meetings")
    def test_list_meetings_custom_type(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "result": {"meetings": [], "page_count": 0, "page_number": 1, "page_size": 50, "total_records": 0},
        }

        result = initialized_library.list_meetings(
            user_id="test_user",
            meeting_type="live",
            page_size=50,
        )

        assert result["status"] == "success"
        mock_list.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_type="live",
            page_size=50,
        )

    @patch("core.external_libraries.zoom.external_app_library.list_meetings")
    def test_list_meetings_empty_result(self, mock_list, initialized_library):
        mock_list.return_value = {
            "ok": True,
            "result": {"meetings": [], "page_count": 0, "page_number": 1, "page_size": 30, "total_records": 0},
        }

        result = initialized_library.list_meetings(user_id="test_user")

        assert result["status"] == "success"
        assert result["meetings"]["meetings"] == []


class TestGetUpcomingMeetings:

    @patch("core.external_libraries.zoom.external_app_library.get_upcoming_meetings")
    def test_get_upcoming_success(self, mock_upcoming, initialized_library):
        mock_upcoming.return_value = {
            "ok": True,
            "result": {
                "meetings": [
                    {"id": 333, "topic": "1-on-1", "start_time": "2026-02-12T10:00:00Z"},
                ],
                "total_records": 1,
            },
        }

        result = initialized_library.get_upcoming_meetings(user_id="test_user")

        assert result["status"] == "success"
        assert len(result["meetings"]["meetings"]) == 1
        mock_upcoming.assert_called_once_with(
            access_token="fake_access_token_abc123",
            page_size=30,
        )

    def test_get_upcoming_no_credential(self, initialized_library):
        result = initialized_library.get_upcoming_meetings(user_id="nonexistent")

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_upcoming_meetings")
    def test_get_upcoming_api_error(self, mock_upcoming, initialized_library):
        mock_upcoming.return_value = {"error": "API error: 500", "details": "Internal error"}

        result = initialized_library.get_upcoming_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.get_upcoming_meetings")
    def test_get_upcoming_exception(self, mock_upcoming, initialized_library):
        mock_upcoming.side_effect = Exception("DNS failure")

        result = initialized_library.get_upcoming_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_upcoming_meetings")
    def test_get_upcoming_custom_page_size(self, mock_upcoming, initialized_library):
        mock_upcoming.return_value = {
            "ok": True,
            "result": {"meetings": [], "total_records": 0},
        }

        result = initialized_library.get_upcoming_meetings(
            user_id="test_user",
            page_size=10,
        )

        assert result["status"] == "success"
        mock_upcoming.assert_called_once_with(
            access_token="fake_access_token_abc123",
            page_size=10,
        )


class TestGetLiveMeetings:

    @patch("core.external_libraries.zoom.external_app_library.get_live_meetings")
    def test_get_live_success(self, mock_live, initialized_library):
        mock_live.return_value = {
            "ok": True,
            "result": {
                "meetings": [
                    {"id": 444, "topic": "Live Webinar", "status": "started"},
                ],
                "total_records": 1,
            },
        }

        result = initialized_library.get_live_meetings(user_id="test_user")

        assert result["status"] == "success"
        assert len(result["meetings"]["meetings"]) == 1
        mock_live.assert_called_once_with(access_token="fake_access_token_abc123")

    def test_get_live_no_credential(self, initialized_library):
        result = initialized_library.get_live_meetings(user_id="nonexistent")

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_live_meetings")
    def test_get_live_api_error(self, mock_live, initialized_library):
        mock_live.return_value = {"error": "API error: 429", "details": "Rate limited"}

        result = initialized_library.get_live_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.get_live_meetings")
    def test_get_live_exception(self, mock_live, initialized_library):
        mock_live.side_effect = Exception("Service unavailable")

        result = initialized_library.get_live_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_live_meetings")
    def test_get_live_no_meetings(self, mock_live, initialized_library):
        mock_live.return_value = {
            "ok": True,
            "result": {"meetings": [], "total_records": 0},
        }

        result = initialized_library.get_live_meetings(user_id="test_user")

        assert result["status"] == "success"
        assert result["meetings"]["meetings"] == []


class TestGetMeeting:

    @patch("core.external_libraries.zoom.external_app_library.get_meeting")
    def test_get_meeting_success(self, mock_get, initialized_library):
        mock_get.return_value = {
            "ok": True,
            "result": {
                "id": 555,
                "topic": "Design Review",
                "start_time": "2026-02-15T15:00:00Z",
                "duration": 45,
                "timezone": "America/New_York",
                "join_url": "https://zoom.us/j/555",
                "password": "abc123",
                "host_email": "testuser@example.com",
            },
        }

        result = initialized_library.get_meeting(
            user_id="test_user",
            meeting_id="555"
        )

        assert result["status"] == "success"
        assert result["meeting"]["id"] == 555
        assert result["meeting"]["topic"] == "Design Review"
        mock_get.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_id="555",
        )

    def test_get_meeting_no_credential(self, initialized_library):
        result = initialized_library.get_meeting(
            user_id="nonexistent",
            meeting_id="555"
        )

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_meeting")
    def test_get_meeting_api_error(self, mock_get, initialized_library):
        mock_get.return_value = {
            "error": "API error: 404",
            "details": "Meeting not found",
        }

        result = initialized_library.get_meeting(
            user_id="test_user",
            meeting_id="999999"
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.get_meeting")
    def test_get_meeting_exception(self, mock_get, initialized_library):
        mock_get.side_effect = Exception("Unexpected API response")

        result = initialized_library.get_meeting(
            user_id="test_user",
            meeting_id="555"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


class TestCreateMeeting:

    @patch("core.external_libraries.zoom.external_app_library.create_meeting")
    def test_create_meeting_success(self, mock_create, initialized_library):
        mock_create.return_value = {
            "ok": True,
            "result": {
                "meeting_id": 777,
                "topic": "Team Sync",
                "start_time": "2026-03-01T09:00:00Z",
                "duration": 60,
                "timezone": "UTC",
                "join_url": "https://zoom.us/j/777",
                "start_url": "https://zoom.us/s/777",
                "password": "pass123",
                "host_email": "testuser@example.com",
            },
        }

        result = initialized_library.create_meeting(
            user_id="test_user",
            topic="Team Sync",
            start_time="2026-03-01T09:00:00Z",
            duration=60,
        )

        assert result["status"] == "success"
        assert result["meeting"]["meeting_id"] == 777
        assert result["meeting"]["join_url"] == "https://zoom.us/j/777"
        mock_create.assert_called_once_with(
            access_token="fake_access_token_abc123",
            topic="Team Sync",
            start_time="2026-03-01T09:00:00Z",
            duration=60,
            timezone="UTC",
            agenda="",
            meeting_type=2,
            password=None,
            settings=None,
        )

    def test_create_meeting_no_credential(self, initialized_library):
        result = initialized_library.create_meeting(
            user_id="nonexistent",
            topic="Test Meeting"
        )

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.create_meeting")
    def test_create_meeting_api_error(self, mock_create, initialized_library):
        mock_create.return_value = {
            "error": "API error: 400",
            "details": "Validation failed",
        }

        result = initialized_library.create_meeting(
            user_id="test_user",
            topic="Bad Meeting"
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.create_meeting")
    def test_create_meeting_exception(self, mock_create, initialized_library):
        mock_create.side_effect = Exception("Request failed")

        result = initialized_library.create_meeting(
            user_id="test_user",
            topic="Team Sync"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.create_meeting")
    def test_create_meeting_with_all_params(self, mock_create, initialized_library):
        custom_settings = {"waiting_room": False, "host_video": False}
        mock_create.return_value = {
            "ok": True,
            "result": {
                "meeting_id": 888,
                "topic": "All Options",
                "join_url": "https://zoom.us/j/888",
            },
        }

        result = initialized_library.create_meeting(
            user_id="test_user",
            topic="All Options",
            start_time="2026-04-01T10:00:00Z",
            duration=120,
            timezone="America/Los_Angeles",
            agenda="Full featured meeting",
            meeting_type=2,
            password="secret",
            settings=custom_settings,
        )

        assert result["status"] == "success"
        mock_create.assert_called_once_with(
            access_token="fake_access_token_abc123",
            topic="All Options",
            start_time="2026-04-01T10:00:00Z",
            duration=120,
            timezone="America/Los_Angeles",
            agenda="Full featured meeting",
            meeting_type=2,
            password="secret",
            settings=custom_settings,
        )

    @patch("core.external_libraries.zoom.external_app_library.create_meeting")
    def test_create_instant_meeting(self, mock_create, initialized_library):
        mock_create.return_value = {
            "ok": True,
            "result": {
                "meeting_id": 999,
                "topic": "Quick Call",
                "join_url": "https://zoom.us/j/999",
            },
        }

        result = initialized_library.create_meeting(
            user_id="test_user",
            topic="Quick Call",
            meeting_type=1,
        )

        assert result["status"] == "success"
        mock_create.assert_called_once_with(
            access_token="fake_access_token_abc123",
            topic="Quick Call",
            start_time=None,
            duration=60,
            timezone="UTC",
            agenda="",
            meeting_type=1,
            password=None,
            settings=None,
        )


class TestUpdateMeeting:

    @patch("core.external_libraries.zoom.external_app_library.update_meeting")
    def test_update_meeting_success(self, mock_update, initialized_library):
        mock_update.return_value = {
            "ok": True,
            "result": {"meeting_id": "555", "updated": True},
        }

        result = initialized_library.update_meeting(
            user_id="test_user",
            meeting_id="555",
            topic="Updated Topic",
            duration=90,
        )

        assert result["status"] == "success"
        assert result["result"]["updated"] is True
        mock_update.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_id="555",
            topic="Updated Topic",
            start_time=None,
            duration=90,
            timezone=None,
            agenda=None,
            password=None,
            settings=None,
        )

    def test_update_meeting_no_credential(self, initialized_library):
        result = initialized_library.update_meeting(
            user_id="nonexistent",
            meeting_id="555",
            topic="Updated"
        )

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.update_meeting")
    def test_update_meeting_api_error(self, mock_update, initialized_library):
        mock_update.return_value = {
            "error": "API error: 404",
            "details": "Meeting not found",
        }

        result = initialized_library.update_meeting(
            user_id="test_user",
            meeting_id="invalid",
            topic="Updated"
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.update_meeting")
    def test_update_meeting_exception(self, mock_update, initialized_library):
        mock_update.side_effect = Exception("Patch failed")

        result = initialized_library.update_meeting(
            user_id="test_user",
            meeting_id="555",
            topic="Updated"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.update_meeting")
    def test_update_meeting_partial_params(self, mock_update, initialized_library):
        """Update only specific fields, leaving others as None."""
        mock_update.return_value = {
            "ok": True,
            "result": {"meeting_id": "555", "updated": True},
        }

        result = initialized_library.update_meeting(
            user_id="test_user",
            meeting_id="555",
            agenda="New agenda only",
        )

        assert result["status"] == "success"
        mock_update.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_id="555",
            topic=None,
            start_time=None,
            duration=None,
            timezone=None,
            agenda="New agenda only",
            password=None,
            settings=None,
        )

    @patch("core.external_libraries.zoom.external_app_library.update_meeting")
    def test_update_meeting_all_params(self, mock_update, initialized_library):
        custom_settings = {"mute_upon_entry": True}
        mock_update.return_value = {
            "ok": True,
            "result": {"meeting_id": "555", "updated": True},
        }

        result = initialized_library.update_meeting(
            user_id="test_user",
            meeting_id="555",
            topic="Full Update",
            start_time="2026-05-01T08:00:00Z",
            duration=120,
            timezone="Europe/London",
            agenda="Updated agenda",
            password="newpass",
            settings=custom_settings,
        )

        assert result["status"] == "success"
        mock_update.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_id="555",
            topic="Full Update",
            start_time="2026-05-01T08:00:00Z",
            duration=120,
            timezone="Europe/London",
            agenda="Updated agenda",
            password="newpass",
            settings=custom_settings,
        )


class TestDeleteMeeting:

    @patch("core.external_libraries.zoom.external_app_library.delete_meeting")
    def test_delete_meeting_success(self, mock_delete, initialized_library):
        mock_delete.return_value = {
            "ok": True,
            "result": {"meeting_id": "555", "deleted": True},
        }

        result = initialized_library.delete_meeting(
            user_id="test_user",
            meeting_id="555"
        )

        assert result["status"] == "success"
        assert result["deleted"] is True
        mock_delete.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_id="555",
        )

    def test_delete_meeting_no_credential(self, initialized_library):
        result = initialized_library.delete_meeting(
            user_id="nonexistent",
            meeting_id="555"
        )

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.delete_meeting")
    def test_delete_meeting_api_error(self, mock_delete, initialized_library):
        mock_delete.return_value = {
            "error": "API error: 404",
            "details": "Meeting does not exist",
        }

        result = initialized_library.delete_meeting(
            user_id="test_user",
            meeting_id="nonexistent_id"
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.delete_meeting")
    def test_delete_meeting_exception(self, mock_delete, initialized_library):
        mock_delete.side_effect = Exception("Delete failed")

        result = initialized_library.delete_meeting(
            user_id="test_user",
            meeting_id="555"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


class TestGetMeetingInvitation:

    @patch("core.external_libraries.zoom.external_app_library.get_meeting_invitation")
    def test_get_invitation_success(self, mock_invite, initialized_library):
        mock_invite.return_value = {
            "ok": True,
            "result": {
                "invitation": "You are invited to a Zoom meeting.\n\nTopic: Team Sync\nTime: Mar 1, 2026 09:00 AM UTC\n\nJoin URL: https://zoom.us/j/777",
            },
        }

        result = initialized_library.get_meeting_invitation(
            user_id="test_user",
            meeting_id="777"
        )

        assert result["status"] == "success"
        assert "invitation" in result
        assert "Team Sync" in result["invitation"]["invitation"]
        mock_invite.assert_called_once_with(
            access_token="fake_access_token_abc123",
            meeting_id="777",
        )

    def test_get_invitation_no_credential(self, initialized_library):
        result = initialized_library.get_meeting_invitation(
            user_id="nonexistent",
            meeting_id="777"
        )

        assert result["status"] == "error"
        assert "No valid Zoom credential" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_meeting_invitation")
    def test_get_invitation_api_error(self, mock_invite, initialized_library):
        mock_invite.return_value = {
            "error": "API error: 404",
            "details": "Meeting not found",
        }

        result = initialized_library.get_meeting_invitation(
            user_id="test_user",
            meeting_id="invalid"
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.zoom.external_app_library.get_meeting_invitation")
    def test_get_invitation_exception(self, mock_invite, initialized_library):
        mock_invite.side_effect = Exception("Invitation fetch failed")

        result = initialized_library.get_meeting_invitation(
            user_id="test_user",
            meeting_id="777"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


# ---------------------------------------------------------------------------
# Credential Model Tests
# ---------------------------------------------------------------------------

class TestZoomCredential:

    def test_credential_defaults(self):
        cred = ZoomCredential(user_id="u1")
        assert cred.access_token == ""
        assert cred.refresh_token == ""
        assert cred.token_expiry is None
        assert cred.zoom_user_id == ""
        assert cred.email == ""
        assert cred.display_name == ""
        assert cred.account_id == ""

    def test_credential_with_all_fields(self):
        cred = ZoomCredential(
            user_id="u1",
            access_token="at",
            refresh_token="rt",
            token_expiry=1700000000.0,
            zoom_user_id="z1",
            email="test@example.com",
            display_name="Test",
            account_id="a1",
        )
        assert cred.access_token == "at"
        assert cred.refresh_token == "rt"
        assert cred.token_expiry == 1700000000.0
        assert cred.zoom_user_id == "z1"
        assert cred.email == "test@example.com"
        assert cred.display_name == "Test"
        assert cred.account_id == "a1"

    def test_credential_unique_keys(self):
        assert ZoomCredential.UNIQUE_KEYS == ("user_id", "zoom_user_id")

    def test_credential_to_dict(self):
        cred = ZoomCredential(
            user_id="u1",
            access_token="at",
            zoom_user_id="z1",
            email="test@example.com",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["access_token"] == "at"
        assert d["zoom_user_id"] == "z1"
        assert d["email"] == "test@example.com"
        assert d["refresh_token"] == ""  # default
        assert d["token_expiry"] is None  # default

    def test_credential_to_dict_contains_all_keys(self):
        cred = ZoomCredential(user_id="u1")
        d = cred.to_dict()
        expected_keys = {
            "user_id", "access_token", "refresh_token", "token_expiry",
            "zoom_user_id", "email", "display_name", "account_id",
        }
        assert expected_keys == set(d.keys())


# ---------------------------------------------------------------------------
# Edge Cases & Error Handling Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch("core.external_libraries.zoom.external_app_library.get_user_profile")
    def test_profile_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Network error")

        result = initialized_library.get_my_profile(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.list_users")
    def test_list_users_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Timeout")

        result = initialized_library.list_users(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.list_meetings")
    def test_list_meetings_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Connection refused")

        result = initialized_library.list_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_upcoming_meetings")
    def test_upcoming_meetings_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("SSL error")

        result = initialized_library.get_upcoming_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_live_meetings")
    def test_live_meetings_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Socket closed")

        result = initialized_library.get_live_meetings(user_id="test_user")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_meeting")
    def test_get_meeting_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Bad gateway")

        result = initialized_library.get_meeting(user_id="test_user", meeting_id="123")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.create_meeting")
    def test_create_meeting_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("JSON decode error")

        result = initialized_library.create_meeting(user_id="test_user", topic="Test")

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.update_meeting")
    def test_update_meeting_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Serialization error")

        result = initialized_library.update_meeting(
            user_id="test_user", meeting_id="123", topic="Updated"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.delete_meeting")
    def test_delete_meeting_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Permission denied")

        result = initialized_library.delete_meeting(
            user_id="test_user", meeting_id="123"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.zoom.external_app_library.get_meeting_invitation")
    def test_invitation_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Invalid meeting")

        result = initialized_library.get_meeting_invitation(
            user_id="test_user", meeting_id="123"
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]


class TestMultipleCredentials:
    """Test behavior when multiple credentials exist for a user."""

    def test_multiple_zoom_accounts(self):
        """User has two Zoom accounts; get_credentials returns the first."""
        ZoomAppLibrary.initialize()
        store = ZoomAppLibrary.get_credential_store()
        store.credentials.clear()  # clear any persisted data
        cred1 = ZoomCredential(
            user_id="test_user",
            access_token="token_a",
            zoom_user_id="zoom_a",
            token_expiry=time.time() + 3600,
        )
        cred2 = ZoomCredential(
            user_id="test_user",
            access_token="token_b",
            zoom_user_id="zoom_b",
            token_expiry=time.time() + 3600,
        )
        store.add(cred1)
        store.add(cred2)

        # Without zoom_user_id, returns the first one
        cred = ZoomAppLibrary.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.zoom_user_id == "zoom_a"

    def test_select_specific_zoom_account(self):
        """Select a specific Zoom account by zoom_user_id."""
        ZoomAppLibrary.initialize()
        store = ZoomAppLibrary.get_credential_store()
        store.credentials.clear()  # clear any persisted data
        cred1 = ZoomCredential(
            user_id="test_user",
            access_token="token_a",
            zoom_user_id="zoom_a",
            token_expiry=time.time() + 3600,
        )
        cred2 = ZoomCredential(
            user_id="test_user",
            access_token="token_b",
            zoom_user_id="zoom_b",
            token_expiry=time.time() + 3600,
        )
        store.add(cred1)
        store.add(cred2)

        cred = ZoomAppLibrary.get_credentials(
            user_id="test_user",
            zoom_user_id="zoom_b"
        )
        assert cred is not None
        assert cred.zoom_user_id == "zoom_b"
        assert cred.access_token == "token_b"

    def test_validate_connection_with_multiple_accounts(self):
        """Validate connection works correctly with multiple zoom accounts."""
        ZoomAppLibrary.initialize()
        store = ZoomAppLibrary.get_credential_store()
        store.credentials.clear()  # clear any persisted data
        cred1 = ZoomCredential(
            user_id="test_user",
            access_token="token_a",
            zoom_user_id="zoom_a",
        )
        cred2 = ZoomCredential(
            user_id="test_user",
            access_token="token_b",
            zoom_user_id="zoom_b",
        )
        store.add(cred1)
        store.add(cred2)

        assert ZoomAppLibrary.validate_connection(user_id="test_user") is True
        assert ZoomAppLibrary.validate_connection(
            user_id="test_user", zoom_user_id="zoom_a"
        ) is True
        assert ZoomAppLibrary.validate_connection(
            user_id="test_user", zoom_user_id="zoom_b"
        ) is True
        assert ZoomAppLibrary.validate_connection(
            user_id="test_user", zoom_user_id="zoom_c"
        ) is False


# ---------------------------------------------------------------------------
# Zoom Helper Function Tests (unit tests for helpers/zoom_helpers.py)
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    """Test the refresh_access_token helper function directly."""

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_refresh_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import refresh_access_token

        result = refresh_access_token(
            client_id="cid",
            client_secret="csec",
            refresh_token="old_refresh"
        )

        assert result is not None
        new_token, new_refresh, expiry = result
        assert new_token == "new_token"
        assert new_refresh == "new_refresh"
        assert expiry > time.time()
        mock_post.assert_called_once()

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_refresh_api_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid refresh token"
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import refresh_access_token

        result = refresh_access_token(
            client_id="cid",
            client_secret="csec",
            refresh_token="bad_refresh"
        )

        assert result is None

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_refresh_network_exception(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        from core.external_libraries.zoom.helpers.zoom_helpers import refresh_access_token

        result = refresh_access_token(
            client_id="cid",
            client_secret="csec",
            refresh_token="refresh_tok"
        )

        assert result is None

    def test_refresh_missing_params(self):
        from core.external_libraries.zoom.helpers.zoom_helpers import refresh_access_token

        assert refresh_access_token("", "csec", "rt") is None
        assert refresh_access_token("cid", "", "rt") is None
        assert refresh_access_token("cid", "csec", "") is None

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_refresh_uses_basic_auth(self, mock_post):
        """Verify that Basic auth credentials are sent correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import refresh_access_token
        from base64 import b64encode

        refresh_access_token(
            client_id="my_client",
            client_secret="my_secret",
            refresh_token="ref_tok"
        )

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        expected_credentials = b64encode(b"my_client:my_secret").decode()
        assert headers["Authorization"] == f"Basic {expected_credentials}"

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_refresh_preserves_old_refresh_token_when_not_returned(self, mock_post):
        """If Zoom response omits refresh_token, the old one is kept."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
            # No "refresh_token" key
        }
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import refresh_access_token

        result = refresh_access_token(
            client_id="cid",
            client_secret="csec",
            refresh_token="original_refresh"
        )

        assert result is not None
        _, new_refresh, _ = result
        assert new_refresh == "original_refresh"


class TestGetUserProfileHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_profile_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "z_001",
            "email": "user@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "account_id": "acc_1",
            "type": 2,
            "pic_url": "https://example.com/pic.jpg",
            "timezone": "America/New_York",
            "pmi": 123456789,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_user_profile

        result = get_user_profile(access_token="token123")

        assert result["ok"] is True
        assert result["result"]["zoom_user_id"] == "z_001"
        assert result["result"]["display_name"] == "John Doe"

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_profile_api_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_user_profile

        result = get_user_profile(access_token="bad_token")

        assert "error" in result
        assert "401" in result["error"]

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_profile_exception(self, mock_get):
        mock_get.side_effect = Exception("Connection error")

        from core.external_libraries.zoom.helpers.zoom_helpers import get_user_profile

        result = get_user_profile(access_token="token123")

        assert "error" in result
        assert "Connection error" in result["error"]


class TestListUsersHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_list_users_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "users": [{"id": "u1", "email": "a@b.com"}],
            "page_count": 1,
            "page_number": 1,
            "page_size": 30,
            "total_records": 1,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import list_users

        result = list_users(access_token="token123")

        assert result["ok"] is True
        assert len(result["result"]["users"]) == 1

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_list_users_caps_page_size(self, mock_get):
        """Page size is capped at 300."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "users": [],
            "page_count": 0,
            "page_number": 1,
            "page_size": 300,
            "total_records": 0,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import list_users

        list_users(access_token="tok", page_size=500)

        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["page_size"] == 300


class TestListMeetingsHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_list_meetings_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "meetings": [{"id": 111, "topic": "Standup"}],
            "page_count": 1,
            "page_number": 1,
            "page_size": 30,
            "total_records": 1,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import list_meetings

        result = list_meetings(access_token="tok")

        assert result["ok"] is True
        assert len(result["result"]["meetings"]) == 1

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_list_meetings_api_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import list_meetings

        result = list_meetings(access_token="tok")

        assert "error" in result


class TestGetMeetingHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_meeting_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 555,
            "topic": "Review",
            "join_url": "https://zoom.us/j/555",
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_meeting

        result = get_meeting(access_token="tok", meeting_id="555")

        assert result["ok"] is True
        assert result["result"]["id"] == 555

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_meeting_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Meeting not found"
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_meeting

        result = get_meeting(access_token="tok", meeting_id="999")

        assert "error" in result


class TestCreateMeetingHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_create_meeting_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 777,
            "topic": "New Meeting",
            "start_time": "2026-03-01T09:00:00Z",
            "duration": 60,
            "timezone": "UTC",
            "join_url": "https://zoom.us/j/777",
            "start_url": "https://zoom.us/s/777",
            "password": "pass",
            "host_email": "host@example.com",
        }
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import create_meeting

        result = create_meeting(access_token="tok", topic="New Meeting")

        assert result["ok"] is True
        assert result["result"]["meeting_id"] == 777
        assert result["result"]["join_url"] == "https://zoom.us/j/777"

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_create_meeting_with_password_and_settings(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 888, "topic": "Custom"}
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import create_meeting

        custom_settings = {"waiting_room": True}
        create_meeting(
            access_token="tok",
            topic="Custom",
            password="secret",
            settings=custom_settings,
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["password"] == "secret"
        assert payload["settings"] == custom_settings

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_create_meeting_instant_omits_start_time(self, mock_post):
        """Instant meetings (type=1) should not include start_time."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 999, "topic": "Instant"}
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import create_meeting

        create_meeting(
            access_token="tok",
            topic="Instant",
            meeting_type=1,
            start_time="2026-03-01T09:00:00Z",
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "start_time" not in payload

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.post")
    def test_create_meeting_api_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Validation error"
        mock_post.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import create_meeting

        result = create_meeting(access_token="tok", topic="Bad")

        assert "error" in result


class TestUpdateMeetingHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.patch")
    def test_update_meeting_success(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_patch.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import update_meeting

        result = update_meeting(
            access_token="tok",
            meeting_id="555",
            topic="Updated Topic"
        )

        assert result["ok"] is True
        assert result["result"]["updated"] is True

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.patch")
    def test_update_meeting_only_sends_provided_fields(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_patch.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import update_meeting

        update_meeting(
            access_token="tok",
            meeting_id="555",
            topic="New Topic",
            duration=90,
        )

        call_kwargs = mock_patch.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload == {"topic": "New Topic", "duration": 90}

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.patch")
    def test_update_meeting_api_error(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Meeting not found"
        mock_patch.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import update_meeting

        result = update_meeting(
            access_token="tok",
            meeting_id="invalid"
        )

        assert "error" in result


class TestDeleteMeetingHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.delete")
    def test_delete_meeting_success(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import delete_meeting

        result = delete_meeting(access_token="tok", meeting_id="555")

        assert result["ok"] is True
        assert result["result"]["deleted"] is True

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.delete")
    def test_delete_meeting_api_error(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Meeting not found"
        mock_delete.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import delete_meeting

        result = delete_meeting(access_token="tok", meeting_id="invalid")

        assert "error" in result

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.delete")
    def test_delete_meeting_with_occurrence(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import delete_meeting

        delete_meeting(
            access_token="tok",
            meeting_id="555",
            occurrence_id="occ_1"
        )

        call_kwargs = mock_delete.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["occurrence_id"] == "occ_1"


class TestGetMeetingInvitationHelper:

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_invitation_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "invitation": "You are invited to a Zoom meeting...",
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_meeting_invitation

        result = get_meeting_invitation(access_token="tok", meeting_id="777")

        assert result["ok"] is True
        assert "invited" in result["result"]["invitation"]

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_invitation_api_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Meeting not found"
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_meeting_invitation

        result = get_meeting_invitation(access_token="tok", meeting_id="bad")

        assert "error" in result


class TestConvenienceHelpers:
    """Test the convenience wrapper functions that delegate to list_meetings."""

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_upcoming_meetings(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "meetings": [],
            "page_count": 0,
            "page_number": 1,
            "page_size": 30,
            "total_records": 0,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_upcoming_meetings

        result = get_upcoming_meetings(access_token="tok")

        assert result["ok"] is True
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["type"] == "upcoming"

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_scheduled_meetings(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "meetings": [],
            "page_count": 0,
            "page_number": 1,
            "page_size": 30,
            "total_records": 0,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_scheduled_meetings

        result = get_scheduled_meetings(access_token="tok")

        assert result["ok"] is True
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["type"] == "scheduled"

    @patch("core.external_libraries.zoom.helpers.zoom_helpers.requests.get")
    def test_get_live_meetings(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "meetings": [],
            "page_count": 0,
            "page_number": 1,
            "page_size": 30,
            "total_records": 0,
        }
        mock_get.return_value = mock_response

        from core.external_libraries.zoom.helpers.zoom_helpers import get_live_meetings

        result = get_live_meetings(access_token="tok")

        assert result["ok"] is True
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["type"] == "live"
