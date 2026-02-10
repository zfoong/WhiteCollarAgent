"""
Discord User Account helper functions.

WARNING: Automating user accounts (self-bots) may violate Discord's Terms of Service.
Use at your own risk. This is provided for personal automation and self-bot use cases.

These functions use the same Discord API but with a user token instead of bot token.
"""
import requests
from typing import Optional, Dict, Any, List

DISCORD_API_BASE = "https://discord.com/api/v10"


def _get_headers(user_token: str) -> Dict[str, str]:
    """Get standard headers for Discord User API requests."""
    return {
        "Authorization": user_token,  # No "Bot" prefix for user tokens
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════════════════
# USER INFO
# ═══════════════════════════════════════════════════════════════════════════

def get_current_user(user_token: str) -> Dict[str, Any]:
    """
    Get the current user's information.

    Args:
        user_token: Discord user token

    Returns:
        User object with id, username, etc.
    """
    url = f"{DISCORD_API_BASE}/users/@me"
    headers = _get_headers(user_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "id": data.get("id"),
                    "username": data.get("username"),
                    "discriminator": data.get("discriminator"),
                    "email": data.get("email"),
                    "avatar": data.get("avatar"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_user_guilds(user_token: str, limit: int = 100) -> Dict[str, Any]:
    """
    Get list of guilds the user is in.

    Args:
        user_token: Discord user token
        limit: Max number of guilds

    Returns:
        List of guild objects
    """
    url = f"{DISCORD_API_BASE}/users/@me/guilds"
    headers = _get_headers(user_token)
    params = {"limit": limit}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": {"guilds": response.json()}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# DM CHANNELS
# ═══════════════════════════════════════════════════════════════════════════

def get_dm_channels(user_token: str) -> Dict[str, Any]:
    """
    Get the user's DM channels.

    Args:
        user_token: Discord user token

    Returns:
        List of DM channel objects
    """
    url = f"{DISCORD_API_BASE}/users/@me/channels"
    headers = _get_headers(user_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            channels = response.json()
            return {
                "ok": True,
                "result": {
                    "dm_channels": [
                        {
                            "id": c.get("id"),
                            "type": c.get("type"),
                            "recipients": [
                                {
                                    "id": r.get("id"),
                                    "username": r.get("username"),
                                }
                                for r in c.get("recipients", [])
                            ],
                            "last_message_id": c.get("last_message_id"),
                        }
                        for c in channels
                    ],
                    "count": len(channels),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def create_dm_channel(user_token: str, recipient_id: str) -> Dict[str, Any]:
    """
    Create/get a DM channel with a user.

    Args:
        user_token: Discord user token
        recipient_id: The user ID to DM

    Returns:
        DM channel object
    """
    url = f"{DISCORD_API_BASE}/users/@me/channels"
    headers = _get_headers(user_token)
    payload = {"recipient_id": recipient_id}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "channel_id": data.get("id"),
                    "type": data.get("type"),
                    "recipients": data.get("recipients", []),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGES (User Account)
# ═══════════════════════════════════════════════════════════════════════════

def send_message(
    user_token: str,
    channel_id: str,
    content: str,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a message as the user.

    Args:
        user_token: Discord user token
        channel_id: The channel ID
        content: Message content
        reply_to: Optional message ID to reply to

    Returns:
        Message object
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = _get_headers(user_token)

    payload = {"content": content}

    if reply_to:
        payload["message_reference"] = {"message_id": reply_to}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "message_id": data.get("id"),
                    "channel_id": data.get("channel_id"),
                    "content": data.get("content"),
                    "timestamp": data.get("timestamp"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_messages(
    user_token: str,
    channel_id: str,
    limit: int = 50,
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get messages from a channel.

    Args:
        user_token: Discord user token
        channel_id: The channel ID
        limit: Max number of messages (1-100)
        before: Get messages before this message ID
        after: Get messages after this message ID

    Returns:
        List of message objects
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = _get_headers(user_token)
    params = {"limit": min(limit, 100)}

    if before:
        params["before"] = before
    if after:
        params["after"] = after

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            messages = response.json()
            return {
                "ok": True,
                "result": {
                    "messages": [
                        {
                            "id": m.get("id"),
                            "content": m.get("content"),
                            "author": {
                                "id": m.get("author", {}).get("id"),
                                "username": m.get("author", {}).get("username"),
                            },
                            "timestamp": m.get("timestamp"),
                            "attachments": m.get("attachments", []),
                        }
                        for m in messages
                    ],
                    "count": len(messages),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def send_dm(
    user_token: str,
    recipient_id: str,
    content: str,
) -> Dict[str, Any]:
    """
    Send a direct message to a user.

    Args:
        user_token: Discord user token
        recipient_id: The user ID to DM
        content: Message content

    Returns:
        Message object
    """
    # First create/get the DM channel
    dm_result = create_dm_channel(user_token, recipient_id)
    if "error" in dm_result:
        return dm_result

    channel_id = dm_result["result"]["channel_id"]

    # Then send the message
    return send_message(user_token, channel_id, content)


# ═══════════════════════════════════════════════════════════════════════════
# RELATIONSHIPS (Friends)
# ═══════════════════════════════════════════════════════════════════════════

def get_relationships(user_token: str) -> Dict[str, Any]:
    """
    Get the user's relationships (friends, blocked, etc.).

    Args:
        user_token: Discord user token

    Returns:
        List of relationship objects
    """
    url = f"{DISCORD_API_BASE}/users/@me/relationships"
    headers = _get_headers(user_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            relationships = response.json()
            friends = [r for r in relationships if r.get("type") == 1]
            blocked = [r for r in relationships if r.get("type") == 2]
            incoming = [r for r in relationships if r.get("type") == 3]
            outgoing = [r for r in relationships if r.get("type") == 4]

            return {
                "ok": True,
                "result": {
                    "friends": [
                        {
                            "id": r.get("id"),
                            "username": r.get("user", {}).get("username"),
                        }
                        for r in friends
                    ],
                    "blocked": blocked,
                    "incoming_requests": incoming,
                    "outgoing_requests": outgoing,
                    "total_friends": len(friends),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════════════

def search_guild_messages(
    user_token: str,
    guild_id: str,
    query: str,
    limit: int = 25,
) -> Dict[str, Any]:
    """
    Search messages in a guild.

    Args:
        user_token: Discord user token
        guild_id: The guild ID
        query: Search query
        limit: Max results

    Returns:
        Search results
    """
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/messages/search"
    headers = _get_headers(user_token)
    params = {"content": query, "limit": limit}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "total_results": data.get("total_results"),
                    "messages": data.get("messages", []),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}
