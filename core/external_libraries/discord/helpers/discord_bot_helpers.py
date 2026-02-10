"""
Discord Bot API helper functions.

Uses Discord's REST API for bot operations.
For real-time events and voice, use discord.py library.

API Documentation: https://discord.com/developers/docs/intro
"""
import requests
from typing import Optional, Dict, Any, List

DISCORD_API_BASE = "https://discord.com/api/v10"


def _get_headers(bot_token: str) -> Dict[str, str]:
    """Get standard headers for Discord Bot API requests."""
    return {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════════════════
# BOT INFO
# ═══════════════════════════════════════════════════════════════════════════

def get_bot_user(bot_token: str) -> Dict[str, Any]:
    """
    Get the bot's user information.

    Args:
        bot_token: Discord bot token

    Returns:
        Bot user object with id, username, discriminator, etc.
    """
    url = f"{DISCORD_API_BASE}/users/@me"
    headers = _get_headers(bot_token)

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
                    "avatar": data.get("avatar"),
                    "bot": data.get("bot", True),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_bot_guilds(bot_token: str, limit: int = 100) -> Dict[str, Any]:
    """
    Get list of guilds (servers) the bot is in.

    Args:
        bot_token: Discord bot token
        limit: Max number of guilds to return

    Returns:
        List of guild objects
    """
    url = f"{DISCORD_API_BASE}/users/@me/guilds"
    headers = _get_headers(bot_token)
    params = {"limit": limit}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            guilds = response.json()
            return {"ok": True, "result": {"guilds": guilds}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# CHANNELS
# ═══════════════════════════════════════════════════════════════════════════

def get_guild_channels(bot_token: str, guild_id: str) -> Dict[str, Any]:
    """
    Get all channels in a guild.

    Args:
        bot_token: Discord bot token
        guild_id: The guild ID

    Returns:
        List of channel objects
    """
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/channels"
    headers = _get_headers(bot_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            channels = response.json()
            # Separate by type
            text_channels = [c for c in channels if c.get("type") == 0]
            voice_channels = [c for c in channels if c.get("type") == 2]
            categories = [c for c in channels if c.get("type") == 4]
            return {
                "ok": True,
                "result": {
                    "all_channels": channels,
                    "text_channels": text_channels,
                    "voice_channels": voice_channels,
                    "categories": categories,
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_channel(bot_token: str, channel_id: str) -> Dict[str, Any]:
    """
    Get a channel by ID.

    Args:
        bot_token: Discord bot token
        channel_id: The channel ID

    Returns:
        Channel object
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}"
    headers = _get_headers(bot_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGES
# ═══════════════════════════════════════════════════════════════════════════

def send_message(
    bot_token: str,
    channel_id: str,
    content: str,
    embed: Optional[Dict] = None,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a message to a channel.

    Args:
        bot_token: Discord bot token
        channel_id: The channel ID (can be DM channel or server channel)
        content: Message content
        embed: Optional embed object
        reply_to: Optional message ID to reply to

    Returns:
        Message object
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = _get_headers(bot_token)

    payload = {"content": content}

    if embed:
        payload["embeds"] = [embed]

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
    bot_token: str,
    channel_id: str,
    limit: int = 50,
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get messages from a channel.

    Args:
        bot_token: Discord bot token
        channel_id: The channel ID
        limit: Max number of messages (1-100)
        before: Get messages before this message ID
        after: Get messages after this message ID

    Returns:
        List of message objects
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = _get_headers(bot_token)
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
                                "bot": m.get("author", {}).get("bot", False),
                            },
                            "timestamp": m.get("timestamp"),
                            "attachments": m.get("attachments", []),
                            "embeds": m.get("embeds", []),
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


def edit_message(
    bot_token: str,
    channel_id: str,
    message_id: str,
    content: str,
) -> Dict[str, Any]:
    """
    Edit a message.

    Args:
        bot_token: Discord bot token
        channel_id: The channel ID
        message_id: The message ID to edit
        content: New message content

    Returns:
        Updated message object
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    headers = _get_headers(bot_token)
    payload = {"content": content}

    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def delete_message(
    bot_token: str,
    channel_id: str,
    message_id: str,
) -> Dict[str, Any]:
    """
    Delete a message.

    Args:
        bot_token: Discord bot token
        channel_id: The channel ID
        message_id: The message ID to delete

    Returns:
        Success status
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    headers = _get_headers(bot_token)

    try:
        response = requests.delete(url, headers=headers, timeout=15)

        if response.status_code == 204:
            return {"ok": True, "result": {"deleted": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# DIRECT MESSAGES
# ═══════════════════════════════════════════════════════════════════════════

def create_dm_channel(bot_token: str, recipient_id: str) -> Dict[str, Any]:
    """
    Create a DM channel with a user.

    Args:
        bot_token: Discord bot token
        recipient_id: The user ID to DM

    Returns:
        DM channel object
    """
    url = f"{DISCORD_API_BASE}/users/@me/channels"
    headers = _get_headers(bot_token)
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


def send_dm(
    bot_token: str,
    recipient_id: str,
    content: str,
    embed: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Send a direct message to a user.

    Args:
        bot_token: Discord bot token
        recipient_id: The user ID to DM
        content: Message content
        embed: Optional embed object

    Returns:
        Message object
    """
    # First create/get the DM channel
    dm_result = create_dm_channel(bot_token, recipient_id)
    if "error" in dm_result:
        return dm_result

    channel_id = dm_result["result"]["channel_id"]

    # Then send the message
    return send_message(bot_token, channel_id, content, embed)


# ═══════════════════════════════════════════════════════════════════════════
# USERS & MEMBERS
# ═══════════════════════════════════════════════════════════════════════════

def get_user(bot_token: str, user_id: str) -> Dict[str, Any]:
    """
    Get a user by ID.

    Args:
        bot_token: Discord bot token
        user_id: The user ID

    Returns:
        User object
    """
    url = f"{DISCORD_API_BASE}/users/{user_id}"
    headers = _get_headers(bot_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_guild_member(bot_token: str, guild_id: str, user_id: str) -> Dict[str, Any]:
    """
    Get a guild member.

    Args:
        bot_token: Discord bot token
        guild_id: The guild ID
        user_id: The user ID

    Returns:
        Guild member object
    """
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}"
    headers = _get_headers(bot_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def list_guild_members(
    bot_token: str,
    guild_id: str,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List guild members.

    Args:
        bot_token: Discord bot token
        guild_id: The guild ID
        limit: Max number of members

    Returns:
        List of guild member objects
    """
    url = f"{DISCORD_API_BASE}/guilds/{guild_id}/members"
    headers = _get_headers(bot_token)
    params = {"limit": min(limit, 1000)}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": {"members": response.json()}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# REACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def add_reaction(
    bot_token: str,
    channel_id: str,
    message_id: str,
    emoji: str,
) -> Dict[str, Any]:
    """
    Add a reaction to a message.

    Args:
        bot_token: Discord bot token
        channel_id: The channel ID
        message_id: The message ID
        emoji: Emoji to react with (URL encoded for custom emoji)

    Returns:
        Success status
    """
    # URL encode the emoji for custom emojis
    encoded_emoji = requests.utils.quote(emoji, safe='')
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    headers = _get_headers(bot_token)

    try:
        response = requests.put(url, headers=headers, timeout=15)

        if response.status_code == 204:
            return {"ok": True, "result": {"added": True, "emoji": emoji}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}
