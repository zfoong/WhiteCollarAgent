"""
Recall.ai API helper functions.

Recall.ai provides meeting bot infrastructure that can join video calls,
record, transcribe, and interact with meetings on Zoom, Google Meet, and Teams.

API Documentation: https://docs.recall.ai/
"""
import requests
from typing import Optional, Dict, Any, List

RECALL_API_BASE_US = "https://us-west-2.recall.ai/api/v1"
RECALL_API_BASE_EU = "https://eu-central-1.recall.ai/api/v1"


def _get_base_url(region: str = "us") -> str:
    """Get the API base URL for the specified region."""
    return RECALL_API_BASE_EU if region.lower() == "eu" else RECALL_API_BASE_US


def _get_headers(api_key: str) -> Dict[str, str]:
    """Get standard headers for Recall.ai API requests."""
    return {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════════════════
# BOT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def create_bot(
    api_key: str,
    meeting_url: str,
    bot_name: str = "Meeting Assistant",
    transcription_options: Optional[Dict[str, Any]] = None,
    chat_options: Optional[Dict[str, Any]] = None,
    recording_mode: str = "speaker_view",
    automatic_leave: Optional[Dict[str, Any]] = None,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Create a bot that will join a meeting.

    Args:
        api_key: Recall.ai API key
        meeting_url: URL of the meeting to join (Zoom, Google Meet, Teams)
        bot_name: Display name for the bot in the meeting
        transcription_options: Options for transcription (provider, language, etc.)
        chat_options: Options for in-meeting chat
        recording_mode: "speaker_view", "gallery_view", or "audio_only"
        automatic_leave: Auto-leave settings (e.g., when everyone leaves)
        region: API region ("us" or "eu")

    Returns:
        Bot object with id, status, and other details
    """
    url = f"{_get_base_url(region)}/bot"
    headers = _get_headers(api_key)

    payload = {
        "meeting_url": meeting_url,
        "bot_name": bot_name,
    }

    if transcription_options:
        payload["transcription_options"] = transcription_options
    else:
        # Default: enable transcription with Deepgram
        payload["transcription_options"] = {
            "provider": "deepgram",
        }

    if chat_options:
        payload["chat"] = chat_options

    if recording_mode:
        payload["recording_mode"] = recording_mode

    if automatic_leave:
        payload["automatic_leave"] = automatic_leave
    else:
        # Default: leave when everyone else leaves
        payload["automatic_leave"] = {
            "waiting_room_timeout": 300,  # 5 minutes
            "noone_joined_timeout": 300,  # 5 minutes
            "everyone_left_timeout": 60,  # 1 minute
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "bot_id": data.get("id"),
                    "status": data.get("status_changes", [{}])[-1].get("code") if data.get("status_changes") else "starting",
                    "meeting_url": data.get("meeting_url", {}).get("url"),
                    "video_url": data.get("video_url"),
                    "join_at": data.get("join_at"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_bot(
    api_key: str,
    bot_id: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Get bot status and details.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        region: API region

    Returns:
        Bot object with current status, video_url, transcript, etc.
    """
    url = f"{_get_base_url(region)}/bot/{bot_id}"
    headers = _get_headers(api_key)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            status_changes = data.get("status_changes", [])
            current_status = status_changes[-1].get("code") if status_changes else "unknown"

            return {
                "ok": True,
                "result": {
                    "bot_id": data.get("id"),
                    "status": current_status,
                    "status_changes": status_changes,
                    "meeting_url": data.get("meeting_url", {}).get("url"),
                    "video_url": data.get("video_url"),
                    "meeting_participants": data.get("meeting_participants", []),
                    "transcript": data.get("transcript"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def list_bots(
    api_key: str,
    page_size: int = 50,
    region: str = "us",
) -> Dict[str, Any]:
    """
    List all bots.

    Args:
        api_key: Recall.ai API key
        page_size: Number of bots per page
        region: API region

    Returns:
        List of bots
    """
    url = f"{_get_base_url(region)}/bot"
    headers = _get_headers(api_key)
    params = {"page_size": page_size}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "bots": data.get("results", []),
                    "count": data.get("count"),
                    "next": data.get("next"),
                    "previous": data.get("previous"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def delete_bot(
    api_key: str,
    bot_id: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Delete a bot and its data.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID to delete
        region: API region
    """
    url = f"{_get_base_url(region)}/bot/{bot_id}"
    headers = _get_headers(api_key)

    try:
        response = requests.delete(url, headers=headers, timeout=15)

        if response.status_code in [200, 204]:
            return {"ok": True, "result": {"deleted": True, "bot_id": bot_id}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# BOT ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def leave_meeting(
    api_key: str,
    bot_id: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Make the bot leave the meeting.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        region: API region
    """
    url = f"{_get_base_url(region)}/bot/{bot_id}/leave_call"
    headers = _get_headers(api_key)

    try:
        response = requests.post(url, headers=headers, timeout=15)

        if response.status_code in [200, 204]:
            return {"ok": True, "result": {"left": True, "bot_id": bot_id}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def send_chat_message(
    api_key: str,
    bot_id: str,
    message: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Send a chat message in the meeting.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        message: Message to send in the meeting chat
        region: API region
    """
    url = f"{_get_base_url(region)}/bot/{bot_id}/send_chat_message"
    headers = _get_headers(api_key)
    payload = {"message": message}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in [200, 201, 204]:
            return {"ok": True, "result": {"sent": True, "message": message}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# TRANSCRIPTION
# ═══════════════════════════════════════════════════════════════════════════

def get_transcript(
    api_key: str,
    bot_id: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Get the meeting transcript.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        region: API region

    Returns:
        Transcript with speaker labels and timestamps
    """
    url = f"{_get_base_url(region)}/bot/{bot_id}/transcript"
    headers = _get_headers(api_key)

    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "transcript": data,
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# RECORDING
# ═══════════════════════════════════════════════════════════════════════════

def get_recording(
    api_key: str,
    bot_id: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Get the meeting recording URL.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        region: API region

    Returns:
        Recording URL (video_url)
    """
    # Recording URL is included in the bot details
    result = get_bot(api_key=api_key, bot_id=bot_id, region=region)

    if "ok" in result:
        return {
            "ok": True,
            "result": {
                "video_url": result["result"].get("video_url"),
                "status": result["result"].get("status"),
            }
        }
    return result


# ═══════════════════════════════════════════════════════════════════════════
# REAL-TIME FEATURES
# ═══════════════════════════════════════════════════════════════════════════

def get_real_time_transcript_url(
    api_key: str,
    bot_id: str,
    region: str = "us",
) -> Dict[str, Any]:
    """
    Get WebSocket URL for real-time transcript streaming.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        region: API region

    Returns:
        WebSocket URL for real-time transcript
    """
    # Get bot details which includes the real-time transcript URL
    result = get_bot(api_key=api_key, bot_id=bot_id, region=region)

    if "ok" in result:
        return {
            "ok": True,
            "result": {
                "bot_id": bot_id,
                "status": result["result"].get("status"),
                "note": "Use the Recall.ai webhook or WebSocket for real-time transcripts",
            }
        }
    return result


def output_audio(
    api_key: str,
    bot_id: str,
    audio_data: str,
    audio_format: str = "wav",
    region: str = "us",
) -> Dict[str, Any]:
    """
    Output audio through the bot (text-to-speech response).

    Note: This requires the bot to be configured with audio output enabled.

    Args:
        api_key: Recall.ai API key
        bot_id: The bot ID
        audio_data: Base64 encoded audio data
        audio_format: Audio format ("wav", "mp3", etc.)
        region: API region
    """
    url = f"{_get_base_url(region)}/bot/{bot_id}/output_audio"
    headers = _get_headers(api_key)
    payload = {
        "audio_data": audio_data,
        "audio_format": audio_format,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code in [200, 201, 204]:
            return {"ok": True, "result": {"audio_sent": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}
