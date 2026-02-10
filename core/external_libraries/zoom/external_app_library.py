import time
from typing import Optional, Dict, Any
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.zoom.credentials import ZoomCredential
from core.external_libraries.zoom.helpers.zoom_helpers import (
    refresh_access_token,
    get_user_profile,
    list_users,
    list_meetings,
    get_meeting,
    create_meeting,
    update_meeting,
    delete_meeting,
    get_meeting_invitation,
    get_upcoming_meetings,
    get_scheduled_meetings,
    get_live_meetings,
)


class ZoomAppLibrary(ExternalAppLibrary):
    """
    Zoom integration library for the CraftOS agent system.

    Supports:
    - Meeting management (list, create, update, delete)
    - Meeting invitation retrieval
    - User profile access
    - User listing (for org accounts)
    - OAuth 2.0 token management with auto-refresh
    """

    _name = "Zoom"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the Zoom library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=ZoomCredential,
            persistence_file="zoom_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("ZoomAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, zoom_user_id: Optional[str] = None) -> bool:
        """
        Check if a Zoom credential exists for the given user.
        """
        cred_store = cls.get_credential_store()
        if zoom_user_id:
            credentials = cred_store.get(user_id=user_id, zoom_user_id=zoom_user_id)
        else:
            credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        zoom_user_id: Optional[str] = None
    ) -> Optional[ZoomCredential]:
        """
        Retrieve Zoom credential for the given user.
        """
        cred_store = cls.get_credential_store()
        if zoom_user_id:
            credentials = cred_store.get(user_id=user_id, zoom_user_id=zoom_user_id)
        else:
            credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    @classmethod
    def ensure_valid_token(
        cls,
        user_id: str,
        zoom_user_id: Optional[str] = None
    ) -> Optional[ZoomCredential]:
        """
        Get credentials and ensure the access token is valid.
        Auto-refresh if expired (Zoom tokens last ~1 hour).
        """
        from core.config import ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET

        credential = cls.get_credentials(user_id=user_id, zoom_user_id=zoom_user_id)
        if not credential:
            return None

        current_time = time.time()
        is_expired = credential.token_expiry is None or credential.token_expiry <= current_time

        if is_expired and credential.refresh_token:
            result = refresh_access_token(
                client_id=ZOOM_CLIENT_ID,
                client_secret=ZOOM_CLIENT_SECRET,
                refresh_token=credential.refresh_token
            )

            if result:
                new_token, new_refresh_token, new_expiry = result
                credential.access_token = new_token
                credential.refresh_token = new_refresh_token
                credential.token_expiry = new_expiry

                cred_store = cls.get_credential_store()
                cred_store.add(credential)

                print(f"[ZOOM_TOKEN_REFRESH] Refreshed token for {credential.zoom_user_id}")
            else:
                print(f"[ZOOM_TOKEN_REFRESH] Failed for {credential.zoom_user_id}")

        return credential

    # ═══════════════════════════════════════════════════════════════════════════
    # USER OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_my_profile(
        cls,
        user_id: str,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the authenticated user's Zoom profile."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = get_user_profile(access_token=credential.access_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "profile": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def list_users(
        cls,
        user_id: str,
        status: str = "active",
        page_size: int = 30,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List users in the Zoom account (admin accounts only)."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = list_users(
                access_token=credential.access_token,
                status=status,
                page_size=page_size,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "users": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # MEETING OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def list_meetings(
        cls,
        user_id: str,
        meeting_type: str = "scheduled",
        page_size: int = 30,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List meetings for the user.

        Args:
            meeting_type: "scheduled", "live", "upcoming", "upcoming_meetings", "previous_meetings"
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = list_meetings(
                access_token=credential.access_token,
                meeting_type=meeting_type,
                page_size=page_size,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "meetings": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_upcoming_meetings(
        cls,
        user_id: str,
        page_size: int = 30,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get upcoming meetings."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = get_upcoming_meetings(
                access_token=credential.access_token,
                page_size=page_size,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "meetings": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_live_meetings(
        cls,
        user_id: str,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get currently live meetings."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = get_live_meetings(access_token=credential.access_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "meetings": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_meeting(
        cls,
        user_id: str,
        meeting_id: str,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get meeting details."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = get_meeting(
                access_token=credential.access_token,
                meeting_id=meeting_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "meeting": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def create_meeting(
        cls,
        user_id: str,
        topic: str,
        start_time: Optional[str] = None,
        duration: int = 60,
        timezone: str = "UTC",
        agenda: str = "",
        meeting_type: int = 2,
        password: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new meeting.

        Args:
            topic: Meeting topic
            start_time: Start time in ISO 8601 format (e.g., "2024-01-15T10:00:00Z")
            duration: Meeting duration in minutes
            timezone: Timezone for the meeting
            agenda: Meeting agenda/description
            meeting_type: 1=Instant, 2=Scheduled, 3=Recurring (no fixed time), 8=Recurring (fixed time)
            password: Meeting password (optional)
            settings: Additional meeting settings
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = create_meeting(
                access_token=credential.access_token,
                topic=topic,
                start_time=start_time,
                duration=duration,
                timezone=timezone,
                agenda=agenda,
                meeting_type=meeting_type,
                password=password,
                settings=settings,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "meeting": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def update_meeting(
        cls,
        user_id: str,
        meeting_id: str,
        topic: Optional[str] = None,
        start_time: Optional[str] = None,
        duration: Optional[int] = None,
        timezone: Optional[str] = None,
        agenda: Optional[str] = None,
        password: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing meeting."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = update_meeting(
                access_token=credential.access_token,
                meeting_id=meeting_id,
                topic=topic,
                start_time=start_time,
                duration=duration,
                timezone=timezone,
                agenda=agenda,
                password=password,
                settings=settings,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "result": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def delete_meeting(
        cls,
        user_id: str,
        meeting_id: str,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a meeting."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = delete_meeting(
                access_token=credential.access_token,
                meeting_id=meeting_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "deleted": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_meeting_invitation(
        cls,
        user_id: str,
        meeting_id: str,
        zoom_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the meeting invitation text."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, zoom_user_id=zoom_user_id)
            if not credential:
                return {"status": "error", "reason": "No valid Zoom credential found."}

            result = get_meeting_invitation(
                access_token=credential.access_token,
                meeting_id=meeting_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "invitation": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
