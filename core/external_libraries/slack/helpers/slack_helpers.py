"""
Slack API helper functions.

These functions make direct calls to the Slack Web API.
"""
import requests
from typing import Optional, Dict, Any, List

SLACK_API_BASE = "https://slack.com/api"


def _get_headers(bot_token: str) -> Dict[str, str]:
    """Get headers for Slack API requests."""
    return {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }


def send_message(
    bot_token: str,
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
    blocks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Send a message to a Slack channel or DM.

    Args:
        bot_token: Slack bot token (xoxb-)
        channel: Channel ID or user ID for DM
        text: Message text
        thread_ts: Optional thread timestamp to reply in thread
        blocks: Optional Block Kit blocks for rich formatting

    Returns:
        API response with message details or error
    """
    url = f"{SLACK_API_BASE}/chat.postMessage"
    headers = _get_headers(bot_token)

    payload: Dict[str, Any] = {
        "channel": channel,
        "text": text,
    }

    if thread_ts:
        payload["thread_ts"] = thread_ts

    if blocks:
        payload["blocks"] = blocks

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def post_message_to_channel(
    bot_token: str,
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for send_message for semantic clarity."""
    return send_message(bot_token, channel, text, thread_ts)


def list_channels(
    bot_token: str,
    types: str = "public_channel,private_channel",
    limit: int = 100,
    exclude_archived: bool = True,
) -> Dict[str, Any]:
    """
    List channels in the workspace.

    Args:
        bot_token: Slack bot token
        types: Comma-separated channel types (public_channel, private_channel, mpim, im)
        limit: Maximum number of channels to return
        exclude_archived: Whether to exclude archived channels

    Returns:
        API response with channels list or error
    """
    url = f"{SLACK_API_BASE}/conversations.list"
    headers = _get_headers(bot_token)

    params = {
        "types": types,
        "limit": limit,
        "exclude_archived": exclude_archived,
    }

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def list_users(
    bot_token: str,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List users in the workspace.

    Args:
        bot_token: Slack bot token
        limit: Maximum number of users to return

    Returns:
        API response with users list or error
    """
    url = f"{SLACK_API_BASE}/users.list"
    headers = _get_headers(bot_token)

    params = {"limit": limit}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def get_user_info(
    bot_token: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Get information about a user.

    Args:
        bot_token: Slack bot token
        user_id: The user ID

    Returns:
        API response with user info or error
    """
    url = f"{SLACK_API_BASE}/users.info"
    headers = _get_headers(bot_token)

    params = {"user": user_id}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def get_channel_history(
    bot_token: str,
    channel: str,
    limit: int = 100,
    oldest: Optional[str] = None,
    latest: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get message history from a channel.

    Args:
        bot_token: Slack bot token
        channel: Channel ID
        limit: Maximum number of messages to return
        oldest: Start of time range (Unix timestamp)
        latest: End of time range (Unix timestamp)

    Returns:
        API response with messages or error
    """
    url = f"{SLACK_API_BASE}/conversations.history"
    headers = _get_headers(bot_token)

    params: Dict[str, Any] = {
        "channel": channel,
        "limit": limit,
    }

    if oldest:
        params["oldest"] = oldest
    if latest:
        params["latest"] = latest

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def create_channel(
    bot_token: str,
    name: str,
    is_private: bool = False,
) -> Dict[str, Any]:
    """
    Create a new channel.

    Args:
        bot_token: Slack bot token
        name: Channel name (will be lowercased and hyphenated)
        is_private: Whether the channel should be private

    Returns:
        API response with channel info or error
    """
    url = f"{SLACK_API_BASE}/conversations.create"
    headers = _get_headers(bot_token)

    payload = {
        "name": name,
        "is_private": is_private,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def invite_to_channel(
    bot_token: str,
    channel: str,
    users: List[str],
) -> Dict[str, Any]:
    """
    Invite users to a channel.

    Args:
        bot_token: Slack bot token
        channel: Channel ID
        users: List of user IDs to invite

    Returns:
        API response or error
    """
    url = f"{SLACK_API_BASE}/conversations.invite"
    headers = _get_headers(bot_token)

    payload = {
        "channel": channel,
        "users": ",".join(users),
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def upload_file(
    bot_token: str,
    channels: List[str],
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    filename: Optional[str] = None,
    title: Optional[str] = None,
    initial_comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upload a file to Slack.

    Args:
        bot_token: Slack bot token
        channels: List of channel IDs to share the file to
        content: File content as string (for text files)
        file_path: Path to local file to upload
        filename: Filename to use
        title: Title for the file
        initial_comment: Message to include with the file

    Returns:
        API response with file info or error
    """
    url = f"{SLACK_API_BASE}/files.upload"
    headers = {"Authorization": f"Bearer {bot_token}"}

    data: Dict[str, Any] = {
        "channels": ",".join(channels),
    }

    if filename:
        data["filename"] = filename
    if title:
        data["title"] = title
    if initial_comment:
        data["initial_comment"] = initial_comment

    files = None
    if file_path:
        files = {"file": open(file_path, "rb")}
    elif content:
        data["content"] = content

    response = requests.post(url, headers=headers, data=data, files=files)

    if files:
        files["file"].close()

    result = response.json()

    if not result.get("ok"):
        return {"error": result.get("error", "Unknown error"), "details": result}

    return result


def get_channel_info(
    bot_token: str,
    channel: str,
) -> Dict[str, Any]:
    """
    Get information about a channel.

    Args:
        bot_token: Slack bot token
        channel: Channel ID

    Returns:
        API response with channel info or error
    """
    url = f"{SLACK_API_BASE}/conversations.info"
    headers = _get_headers(bot_token)

    params = {"channel": channel}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def search_messages(
    bot_token: str,
    query: str,
    count: int = 20,
    sort: str = "timestamp",
    sort_dir: str = "desc",
) -> Dict[str, Any]:
    """
    Search for messages in the workspace.

    Args:
        bot_token: Slack bot token (requires user token for search)
        query: Search query
        count: Number of results to return
        sort: Sort by "score" or "timestamp"
        sort_dir: Sort direction "asc" or "desc"

    Returns:
        API response with search results or error
    """
    url = f"{SLACK_API_BASE}/search.messages"
    headers = _get_headers(bot_token)

    params = {
        "query": query,
        "count": count,
        "sort": sort,
        "sort_dir": sort_dir,
    }

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data


def open_dm(
    bot_token: str,
    users: List[str],
) -> Dict[str, Any]:
    """
    Open a DM or group DM with users.

    Args:
        bot_token: Slack bot token
        users: List of user IDs (1 for DM, 2+ for group DM)

    Returns:
        API response with channel info or error
    """
    url = f"{SLACK_API_BASE}/conversations.open"
    headers = _get_headers(bot_token)

    payload = {"users": ",".join(users)}

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("error", "Unknown error"), "details": data}

    return data
