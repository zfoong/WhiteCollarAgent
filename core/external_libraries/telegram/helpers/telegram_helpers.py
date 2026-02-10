"""
Telegram Bot API helper functions.

These functions make direct calls to the Telegram Bot API.
"""
import requests
from typing import Optional, Dict, Any, List, Union

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def _get_api_url(bot_token: str, method: str) -> str:
    """Get the full API URL for a method."""
    return f"{TELEGRAM_API_BASE}{bot_token}/{method}"


def get_me(bot_token: str) -> Dict[str, Any]:
    """
    Get basic information about the bot.

    Args:
        bot_token: Telegram bot token from @BotFather

    Returns:
        API response with bot info or error
    """
    url = _get_api_url(bot_token, "getMe")
    response = requests.get(url)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def send_message(
    bot_token: str,
    chat_id: Union[int, str],
    text: str,
    parse_mode: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    disable_notification: bool = False,
) -> Dict[str, Any]:
    """
    Send a text message to a chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID or username (@channel)
        text: Message text (up to 4096 characters)
        parse_mode: "HTML", "Markdown", or "MarkdownV2"
        reply_to_message_id: Message ID to reply to
        disable_notification: Send silently

    Returns:
        API response with sent message or error
    """
    url = _get_api_url(bot_token, "sendMessage")

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
    }

    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if disable_notification:
        payload["disable_notification"] = True

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def send_photo(
    bot_token: str,
    chat_id: Union[int, str],
    photo: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a photo to a chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID or username
        photo: File ID, URL, or file path
        caption: Photo caption
        parse_mode: Caption parse mode

    Returns:
        API response with sent message or error
    """
    url = _get_api_url(bot_token, "sendPhoto")

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "photo": photo,
    }

    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def send_document(
    bot_token: str,
    chat_id: Union[int, str],
    document: str,
    caption: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a document to a chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID or username
        document: File ID, URL, or file path
        caption: Document caption
        parse_mode: Caption parse mode

    Returns:
        API response with sent message or error
    """
    url = _get_api_url(bot_token, "sendDocument")

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "document": document,
    }

    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def get_updates(
    bot_token: str,
    offset: Optional[int] = None,
    limit: int = 100,
    timeout: int = 0,
    allowed_updates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get incoming updates using long polling.

    Args:
        bot_token: Telegram bot token
        offset: Identifier of the first update to return
        limit: Maximum number of updates (1-100)
        timeout: Timeout in seconds for long polling
        allowed_updates: List of update types to receive

    Returns:
        API response with updates or error
    """
    url = _get_api_url(bot_token, "getUpdates")

    payload: Dict[str, Any] = {
        "limit": limit,
        "timeout": timeout,
    }

    if offset:
        payload["offset"] = offset
    if allowed_updates:
        payload["allowed_updates"] = allowed_updates

    response = requests.post(url, json=payload, timeout=timeout + 10)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def get_chat(
    bot_token: str,
    chat_id: Union[int, str],
) -> Dict[str, Any]:
    """
    Get up-to-date information about a chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID or username

    Returns:
        API response with chat info or error
    """
    url = _get_api_url(bot_token, "getChat")

    payload = {"chat_id": chat_id}

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def get_chat_member(
    bot_token: str,
    chat_id: Union[int, str],
    user_id: int,
) -> Dict[str, Any]:
    """
    Get information about a member of a chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID or username
        user_id: User ID

    Returns:
        API response with chat member info or error
    """
    url = _get_api_url(bot_token, "getChatMember")

    payload = {
        "chat_id": chat_id,
        "user_id": user_id,
    }

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def get_chat_members_count(
    bot_token: str,
    chat_id: Union[int, str],
) -> Dict[str, Any]:
    """
    Get the number of members in a chat.

    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID or username

    Returns:
        API response with member count or error
    """
    url = _get_api_url(bot_token, "getChatMembersCount")

    payload = {"chat_id": chat_id}

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def set_webhook(
    bot_token: str,
    url: str,
    certificate: Optional[str] = None,
    max_connections: int = 40,
    allowed_updates: Optional[List[str]] = None,
    secret_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set a webhook for receiving updates.

    Args:
        bot_token: Telegram bot token
        url: HTTPS URL for webhook
        certificate: Public key certificate
        max_connections: Maximum simultaneous connections (1-100)
        allowed_updates: List of update types to receive
        secret_token: Secret token for webhook verification

    Returns:
        API response or error
    """
    api_url = _get_api_url(bot_token, "setWebhook")

    payload: Dict[str, Any] = {
        "url": url,
        "max_connections": max_connections,
    }

    if certificate:
        payload["certificate"] = certificate
    if allowed_updates:
        payload["allowed_updates"] = allowed_updates
    if secret_token:
        payload["secret_token"] = secret_token

    response = requests.post(api_url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def delete_webhook(
    bot_token: str,
    drop_pending_updates: bool = False,
) -> Dict[str, Any]:
    """
    Remove webhook integration.

    Args:
        bot_token: Telegram bot token
        drop_pending_updates: Drop pending updates

    Returns:
        API response or error
    """
    url = _get_api_url(bot_token, "deleteWebhook")

    payload = {"drop_pending_updates": drop_pending_updates}

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def get_webhook_info(bot_token: str) -> Dict[str, Any]:
    """
    Get current webhook status.

    Args:
        bot_token: Telegram bot token

    Returns:
        API response with webhook info or error
    """
    url = _get_api_url(bot_token, "getWebhookInfo")

    response = requests.get(url)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def forward_message(
    bot_token: str,
    chat_id: Union[int, str],
    from_chat_id: Union[int, str],
    message_id: int,
    disable_notification: bool = False,
) -> Dict[str, Any]:
    """
    Forward a message from one chat to another.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        from_chat_id: Source chat ID
        message_id: Message ID to forward
        disable_notification: Send silently

    Returns:
        API response with forwarded message or error
    """
    url = _get_api_url(bot_token, "forwardMessage")

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }

    if disable_notification:
        payload["disable_notification"] = True

    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Unknown error"), "details": data}

    return data


def search_contact(
    bot_token: str,
    name: str,
) -> Dict[str, Any]:
    """
    Search for a contact by name from the bot's recent chat history.

    Telegram bots can only interact with users who have started a conversation
    with the bot. This function searches through recent updates to find
    matching users/chats by name.

    Args:
        bot_token: Telegram bot token
        name: Name to search for (case-insensitive, partial match)

    Returns:
        Dict with matching contacts or error
    """
    # Get recent updates to find users who have interacted with the bot
    updates_result = get_updates(bot_token=bot_token, limit=100)

    if "error" in updates_result:
        return updates_result

    updates = updates_result.get("result", [])

    # Extract unique chats/users from updates
    seen_ids = set()
    contacts = []
    search_lower = name.lower()

    for update in updates:
        # Check message
        message = update.get("message") or update.get("edited_message")
        if message:
            chat = message.get("chat", {})
            chat_id = chat.get("id")

            if chat_id and chat_id not in seen_ids:
                seen_ids.add(chat_id)

                # Build searchable name based on chat type
                chat_type = chat.get("type", "")
                if chat_type == "private":
                    first_name = chat.get("first_name", "")
                    last_name = chat.get("last_name", "")
                    username = chat.get("username", "")
                    full_name = f"{first_name} {last_name}".strip()
                    searchable = f"{full_name} {username}".lower()
                else:
                    # Group or channel
                    title = chat.get("title", "")
                    username = chat.get("username", "")
                    full_name = title
                    searchable = f"{title} {username}".lower()

                if search_lower in searchable:
                    contacts.append({
                        "chat_id": chat_id,
                        "type": chat_type,
                        "name": full_name or username,
                        "username": username,
                        "first_name": chat.get("first_name", ""),
                        "last_name": chat.get("last_name", ""),
                    })

            # Also check the sender (from field)
            sender = message.get("from", {})
            sender_id = sender.get("id")

            if sender_id and sender_id not in seen_ids:
                seen_ids.add(sender_id)

                first_name = sender.get("first_name", "")
                last_name = sender.get("last_name", "")
                username = sender.get("username", "")
                full_name = f"{first_name} {last_name}".strip()
                searchable = f"{full_name} {username}".lower()

                if search_lower in searchable and not sender.get("is_bot"):
                    contacts.append({
                        "chat_id": sender_id,
                        "type": "private",
                        "name": full_name or username,
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                    })

    if contacts:
        return {
            "ok": True,
            "result": {
                "contacts": contacts,
                "count": len(contacts),
            }
        }
    else:
        return {
            "error": f"No contacts found matching '{name}'",
            "details": {"searched_updates": len(updates), "name": name}
        }
