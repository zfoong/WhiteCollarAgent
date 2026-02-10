"""
Zoom API helper functions.

These functions make direct calls to the Zoom REST API v2.
"""
import requests
import time
from typing import Optional, Dict, Any, List
from base64 import b64encode

ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_OAUTH_BASE = "https://zoom.us/oauth"


def _get_headers(access_token: str) -> Dict[str, str]:
    """Get standard headers for Zoom API requests."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Optional[tuple]:
    """
    Refresh the Zoom OAuth access token.

    Returns:
        Tuple of (new_access_token, new_refresh_token, token_expiry_timestamp) if successful, None otherwise
    """
    if not all([client_id, client_secret, refresh_token]):
        return None

    url = f"{ZOOM_OAUTH_BASE}/token"

    # Zoom uses Basic auth for token refresh
    credentials = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 3600)  # Default 1 hour
            # Subtract 5 minutes as safety buffer
            token_expiry = time.time() + expires_in - 300
            return (new_access_token, new_refresh_token, token_expiry)
        else:
            print(f"[ZOOM_TOKEN_REFRESH] Failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[ZOOM_TOKEN_REFRESH] Exception: {str(e)}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# USER OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_user_profile(access_token: str) -> Dict[str, Any]:
    """
    Get the authenticated user's profile information.
    """
    url = f"{ZOOM_API_BASE}/users/me"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "zoom_user_id": data.get("id"),
                    "email": data.get("email"),
                    "display_name": data.get("first_name", "") + " " + data.get("last_name", ""),
                    "first_name": data.get("first_name"),
                    "last_name": data.get("last_name"),
                    "account_id": data.get("account_id"),
                    "type": data.get("type"),  # 1=Basic, 2=Licensed, 3=On-prem
                    "pic_url": data.get("pic_url"),
                    "timezone": data.get("timezone"),
                    "pmi": data.get("pmi"),  # Personal Meeting ID
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def list_users(
    access_token: str,
    status: str = "active",
    page_size: int = 30,
    page_number: int = 1,
) -> Dict[str, Any]:
    """
    List users in the account (admin accounts only).

    Args:
        status: User status - "active", "inactive", or "pending"
        page_size: Number of users per page (max 300)
        page_number: Page number for pagination
    """
    url = f"{ZOOM_API_BASE}/users"
    headers = _get_headers(access_token)
    params = {
        "status": status,
        "page_size": min(page_size, 300),
        "page_number": page_number,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "users": data.get("users", []),
                    "page_count": data.get("page_count"),
                    "page_number": data.get("page_number"),
                    "page_size": data.get("page_size"),
                    "total_records": data.get("total_records"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# MEETING OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def list_meetings(
    access_token: str,
    user_id: str = "me",
    meeting_type: str = "scheduled",
    page_size: int = 30,
    page_number: int = 1,
) -> Dict[str, Any]:
    """
    List meetings for a user.

    Args:
        user_id: User ID or "me" for authenticated user
        meeting_type: "scheduled", "live", "upcoming", "upcoming_meetings", "previous_meetings"
        page_size: Number of meetings per page (max 300)
        page_number: Page number for pagination
    """
    url = f"{ZOOM_API_BASE}/users/{user_id}/meetings"
    headers = _get_headers(access_token)
    params = {
        "type": meeting_type,
        "page_size": min(page_size, 300),
        "page_number": page_number,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "meetings": data.get("meetings", []),
                    "page_count": data.get("page_count"),
                    "page_number": data.get("page_number"),
                    "page_size": data.get("page_size"),
                    "total_records": data.get("total_records"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_meeting(access_token: str, meeting_id: str) -> Dict[str, Any]:
    """
    Get meeting details.

    Args:
        meeting_id: Zoom meeting ID
    """
    url = f"{ZOOM_API_BASE}/meetings/{meeting_id}"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def create_meeting(
    access_token: str,
    topic: str,
    start_time: Optional[str] = None,
    duration: int = 60,
    timezone: str = "UTC",
    agenda: str = "",
    meeting_type: int = 2,
    password: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
    user_id: str = "me",
) -> Dict[str, Any]:
    """
    Create a new meeting.

    Args:
        topic: Meeting topic
        start_time: Start time in ISO 8601 format (e.g., "2024-01-15T10:00:00Z")
                   Required for scheduled meetings (type 2)
        duration: Meeting duration in minutes
        timezone: Timezone for the meeting
        agenda: Meeting agenda/description
        meeting_type: 1=Instant, 2=Scheduled, 3=Recurring (no fixed time), 8=Recurring (fixed time)
        password: Meeting password (optional)
        settings: Additional meeting settings
        user_id: User ID or "me" for authenticated user
    """
    url = f"{ZOOM_API_BASE}/users/{user_id}/meetings"
    headers = _get_headers(access_token)

    payload = {
        "topic": topic,
        "type": meeting_type,
        "duration": duration,
        "timezone": timezone,
        "agenda": agenda,
    }

    if start_time and meeting_type != 1:  # Not instant meeting
        payload["start_time"] = start_time

    if password:
        payload["password"] = password

    if settings:
        payload["settings"] = settings
    else:
        # Default sensible settings
        payload["settings"] = {
            "host_video": True,
            "participant_video": True,
            "join_before_host": False,
            "mute_upon_entry": False,
            "waiting_room": True,
            "audio": "both",
            "auto_recording": "none",
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "meeting_id": data.get("id"),
                    "topic": data.get("topic"),
                    "start_time": data.get("start_time"),
                    "duration": data.get("duration"),
                    "timezone": data.get("timezone"),
                    "join_url": data.get("join_url"),
                    "start_url": data.get("start_url"),
                    "password": data.get("password"),
                    "host_email": data.get("host_email"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def update_meeting(
    access_token: str,
    meeting_id: str,
    topic: Optional[str] = None,
    start_time: Optional[str] = None,
    duration: Optional[int] = None,
    timezone: Optional[str] = None,
    agenda: Optional[str] = None,
    password: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Update an existing meeting.

    Args:
        meeting_id: Zoom meeting ID
        Other args: Same as create_meeting, only non-None values will be updated
    """
    url = f"{ZOOM_API_BASE}/meetings/{meeting_id}"
    headers = _get_headers(access_token)

    payload = {}
    if topic is not None:
        payload["topic"] = topic
    if start_time is not None:
        payload["start_time"] = start_time
    if duration is not None:
        payload["duration"] = duration
    if timezone is not None:
        payload["timezone"] = timezone
    if agenda is not None:
        payload["agenda"] = agenda
    if password is not None:
        payload["password"] = password
    if settings is not None:
        payload["settings"] = settings

    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=15)

        if response.status_code == 204:
            return {"ok": True, "result": {"meeting_id": meeting_id, "updated": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def delete_meeting(
    access_token: str,
    meeting_id: str,
    occurrence_id: Optional[str] = None,
    schedule_for_reminder: bool = True,
) -> Dict[str, Any]:
    """
    Delete a meeting.

    Args:
        meeting_id: Zoom meeting ID
        occurrence_id: For recurring meetings, specify occurrence to delete
        schedule_for_reminder: Notify registrants about cancellation
    """
    url = f"{ZOOM_API_BASE}/meetings/{meeting_id}"
    headers = _get_headers(access_token)
    params = {}

    if occurrence_id:
        params["occurrence_id"] = occurrence_id
    if not schedule_for_reminder:
        params["schedule_for_reminder"] = "false"

    try:
        response = requests.delete(url, headers=headers, params=params, timeout=15)

        if response.status_code == 204:
            return {"ok": True, "result": {"meeting_id": meeting_id, "deleted": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_meeting_invitation(access_token: str, meeting_id: str) -> Dict[str, Any]:
    """
    Get the meeting invitation text.

    Args:
        meeting_id: Zoom meeting ID
    """
    url = f"{ZOOM_API_BASE}/meetings/{meeting_id}/invitation"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "invitation": data.get("invitation"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# UPCOMING/SCHEDULED HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_upcoming_meetings(
    access_token: str,
    user_id: str = "me",
    page_size: int = 30,
) -> Dict[str, Any]:
    """
    Get upcoming meetings (convenience wrapper).
    """
    return list_meetings(
        access_token=access_token,
        user_id=user_id,
        meeting_type="upcoming",
        page_size=page_size,
    )


def get_scheduled_meetings(
    access_token: str,
    user_id: str = "me",
    page_size: int = 30,
) -> Dict[str, Any]:
    """
    Get scheduled meetings (convenience wrapper).
    """
    return list_meetings(
        access_token=access_token,
        user_id=user_id,
        meeting_type="scheduled",
        page_size=page_size,
    )


def get_live_meetings(
    access_token: str,
    user_id: str = "me",
) -> Dict[str, Any]:
    """
    Get currently live meetings (convenience wrapper).
    """
    return list_meetings(
        access_token=access_token,
        user_id=user_id,
        meeting_type="live",
    )
