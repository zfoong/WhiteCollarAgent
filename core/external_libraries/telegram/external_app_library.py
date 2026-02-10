import asyncio
from typing import Optional, Dict, Any, List, Union
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.telegram.credentials import TelegramCredential
from core.external_libraries.telegram.helpers.telegram_helpers import (
    get_me,
    send_message,
    send_photo,
    send_document,
    get_updates,
    get_chat,
    get_chat_member,
    get_chat_members_count,
    set_webhook,
    delete_webhook,
    get_webhook_info,
    forward_message,
    search_contact,
)

# Import MTProto helpers (optional - requires telethon)
try:
    from core.external_libraries.telegram.helpers import telegram_mtproto_helpers as mtproto
    MTPROTO_AVAILABLE = True
except ImportError:
    MTPROTO_AVAILABLE = False


class TelegramAppLibrary(ExternalAppLibrary):
    _name = "Telegram"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the Telegram library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=TelegramCredential,
            persistence_file="telegram_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("TelegramAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, bot_id: Optional[str] = None) -> bool:
        """
        Returns True if a Telegram credential exists for the given
        user_id and optional bot_id, False otherwise.
        """
        cred_store = cls.get_credential_store()
        if bot_id:
            credentials = cred_store.get(user_id=user_id, bot_id=bot_id)
        else:
            credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        bot_id: Optional[str] = None
    ) -> Optional[TelegramCredential]:
        """
        Retrieve the Telegram credential for the given user_id and optional bot_id.
        Returns the credential if found, None otherwise.
        """
        cred_store = cls.get_credential_store()
        if bot_id:
            credentials = cred_store.get(user_id=user_id, bot_id=bot_id)
        else:
            credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    # --------------------------------------------------
    # Resolve Chat Identifier (chat_id or name)
    # --------------------------------------------------
    @classmethod
    def _resolve_chat_identifier(
        cls,
        user_id: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a chat identifier from either chat_id or name.

        If chat_id is provided, it's used directly.
        If name is provided, searches for the contact first.

        Args:
            user_id: The user ID
            chat_id: Optional chat ID (numeric or @username)
            name: Optional name to search for
            bot_id: Optional bot ID

        Returns:
            Dict with resolved_chat_id and optional resolved_contact, or error
        """
        if chat_id is not None:
            # chat_id provided directly - use it
            return {"status": "success", "resolved_chat_id": chat_id}

        if name:
            # Search for contact by name
            search_result = cls.search_contact(
                user_id=user_id,
                name=name,
                bot_id=bot_id,
            )

            if search_result.get("status") == "error":
                return {
                    "status": "error",
                    "reason": f"Could not find contact '{name}': {search_result.get('reason', search_result.get('details', {}).get('error', 'Unknown error'))}"
                }

            contacts = search_result.get("contacts", [])
            if not contacts:
                return {
                    "status": "error",
                    "reason": f"No contacts found matching '{name}'. Make sure the contact has messaged the bot first."
                }

            # Use the first matching contact
            contact = contacts[0]
            return {
                "status": "success",
                "resolved_chat_id": contact.get("chat_id"),
                "resolved_contact": contact,
            }

        return {"status": "error", "reason": "Either chat_id or name must be provided"}

    # --------------------------------------------------
    # Get Bot Info
    # --------------------------------------------------
    @classmethod
    def get_bot_info(
        cls,
        user_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get basic information about the bot.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            result = get_me(bot_token=credential.bot_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "bot": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Message
    # --------------------------------------------------
    @classmethod
    def send_message(
        cls,
        user_id: str,
        text: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message to a chat.

        Args:
            user_id: The user ID
            text: Message text
            chat_id: Chat ID or username (@channel). Either chat_id or name required.
            name: Contact name to search for. Either chat_id or name required.
            parse_mode: "HTML", "Markdown", or "MarkdownV2"
            reply_to_message_id: Message ID to reply to
            bot_id: Optional bot ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve chat_id from either chat_id or name
            resolved = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=name, bot_id=bot_id
            )
            if resolved.get("status") == "error":
                return resolved

            actual_chat_id = resolved.get("resolved_chat_id")

            result = send_message(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "message": result.get("result")}
            if resolved.get("resolved_contact"):
                response["resolved_contact"] = resolved.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Photo
    # --------------------------------------------------
    @classmethod
    def send_photo(
        cls,
        user_id: str,
        photo: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a photo to a chat.

        Args:
            user_id: The user ID
            photo: Photo to send (file_id, URL, or file path)
            chat_id: Chat ID or username. Either chat_id or name required.
            name: Contact name to search for. Either chat_id or name required.
            caption: Optional photo caption
            parse_mode: Caption parse mode
            bot_id: Optional bot ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve chat_id from either chat_id or name
            resolved = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=name, bot_id=bot_id
            )
            if resolved.get("status") == "error":
                return resolved

            actual_chat_id = resolved.get("resolved_chat_id")

            result = send_photo(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "message": result.get("result")}
            if resolved.get("resolved_contact"):
                response["resolved_contact"] = resolved.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Document
    # --------------------------------------------------
    @classmethod
    def send_document(
        cls,
        user_id: str,
        document: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a document to a chat.

        Args:
            user_id: The user ID
            document: Document to send (file_id, URL, or file path)
            chat_id: Chat ID or username. Either chat_id or name required.
            name: Contact name to search for. Either chat_id or name required.
            caption: Optional document caption
            parse_mode: Caption parse mode
            bot_id: Optional bot ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve chat_id from either chat_id or name
            resolved = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=name, bot_id=bot_id
            )
            if resolved.get("status") == "error":
                return resolved

            actual_chat_id = resolved.get("resolved_chat_id")

            result = send_document(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
                document=document,
                caption=caption,
                parse_mode=parse_mode,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "message": result.get("result")}
            if resolved.get("resolved_contact"):
                response["resolved_contact"] = resolved.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Updates
    # --------------------------------------------------
    @classmethod
    def get_updates(
        cls,
        user_id: str,
        offset: Optional[int] = None,
        limit: int = 100,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get incoming updates using long polling.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            result = get_updates(
                bot_token=credential.bot_token,
                offset=offset,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "updates": result.get("result", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Chat
    # --------------------------------------------------
    @classmethod
    def get_chat(
        cls,
        user_id: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get up-to-date information about a chat.

        Args:
            user_id: The user ID
            chat_id: Chat ID or username. Either chat_id or name required.
            name: Contact name to search for. Either chat_id or name required.
            bot_id: Optional bot ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve chat_id from either chat_id or name
            resolved = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=name, bot_id=bot_id
            )
            if resolved.get("status") == "error":
                return resolved

            actual_chat_id = resolved.get("resolved_chat_id")

            result = get_chat(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "chat": result.get("result")}
            if resolved.get("resolved_contact"):
                response["resolved_contact"] = resolved.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Chat Member
    # --------------------------------------------------
    @classmethod
    def get_chat_member(
        cls,
        user_id: str,
        target_user_id: int,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get information about a member of a chat.

        Args:
            user_id: The user ID
            target_user_id: The Telegram user ID to get info about
            chat_id: Chat ID or username. Either chat_id or name required.
            name: Chat/group name to search for. Either chat_id or name required.
            bot_id: Optional bot ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve chat_id from either chat_id or name
            resolved = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=name, bot_id=bot_id
            )
            if resolved.get("status") == "error":
                return resolved

            actual_chat_id = resolved.get("resolved_chat_id")

            result = get_chat_member(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
                user_id=target_user_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "member": result.get("result")}
            if resolved.get("resolved_contact"):
                response["resolved_contact"] = resolved.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Chat Members Count
    # --------------------------------------------------
    @classmethod
    def get_chat_members_count(
        cls,
        user_id: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the number of members in a chat.

        Args:
            user_id: The user ID
            chat_id: Chat ID or username. Either chat_id or name required.
            name: Chat/group name to search for. Either chat_id or name required.
            bot_id: Optional bot ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve chat_id from either chat_id or name
            resolved = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=name, bot_id=bot_id
            )
            if resolved.get("status") == "error":
                return resolved

            actual_chat_id = resolved.get("resolved_chat_id")

            result = get_chat_members_count(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "count": result.get("result")}
            if resolved.get("resolved_contact"):
                response["resolved_contact"] = resolved.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Forward Message
    # --------------------------------------------------
    @classmethod
    def forward_message(
        cls,
        user_id: str,
        message_id: int,
        chat_id: Optional[Union[int, str]] = None,
        to_name: Optional[str] = None,
        from_chat_id: Optional[Union[int, str]] = None,
        from_name: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Forward a message from one chat to another.

        Args:
            user_id: The user ID
            message_id: Message ID to forward
            chat_id: Destination chat ID. Either chat_id or to_name required.
            to_name: Destination name to search for. Either chat_id or to_name required.
            from_chat_id: Source chat ID. Either from_chat_id or from_name required.
            from_name: Source name to search for. Either from_chat_id or from_name required.
            bot_id: Optional bot ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            # Resolve destination chat_id
            resolved_to = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=chat_id, name=to_name, bot_id=bot_id
            )
            if resolved_to.get("status") == "error":
                return {"status": "error", "reason": f"Destination: {resolved_to.get('reason')}"}

            actual_chat_id = resolved_to.get("resolved_chat_id")

            # Resolve source chat_id
            resolved_from = cls._resolve_chat_identifier(
                user_id=user_id, chat_id=from_chat_id, name=from_name, bot_id=bot_id
            )
            if resolved_from.get("status") == "error":
                return {"status": "error", "reason": f"Source: {resolved_from.get('reason')}"}

            actual_from_chat_id = resolved_from.get("resolved_chat_id")

            result = forward_message(
                bot_token=credential.bot_token,
                chat_id=actual_chat_id,
                from_chat_id=actual_from_chat_id,
                message_id=message_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            response = {"status": "success", "message": result.get("result")}
            if resolved_to.get("resolved_contact"):
                response["resolved_to_contact"] = resolved_to.get("resolved_contact")
            if resolved_from.get("resolved_contact"):
                response["resolved_from_contact"] = resolved_from.get("resolved_contact")
            return response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Webhook Management
    # --------------------------------------------------
    @classmethod
    def set_webhook(
        cls,
        user_id: str,
        webhook_url: str,
        secret_token: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Set a webhook for receiving updates.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            result = set_webhook(
                bot_token=credential.bot_token,
                url=webhook_url,
                secret_token=secret_token,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "result": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def delete_webhook(
        cls,
        user_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove webhook integration.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            result = delete_webhook(bot_token=credential.bot_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "result": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_webhook_info(
        cls,
        user_id: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get current webhook status.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            result = get_webhook_info(bot_token=credential.bot_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "webhook": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Search Contact
    # --------------------------------------------------
    @classmethod
    def search_contact(
        cls,
        user_id: str,
        name: str,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for a contact by name from the bot's chat history.

        Args:
            user_id: The user ID
            name: Name to search for (case-insensitive, partial match)
            bot_id: Optional bot ID to use specific credentials

        Returns:
            Dict with matching contacts or error
        """
        try:
            credential = cls.get_credentials(user_id=user_id, bot_id=bot_id)
            if not credential:
                return {"status": "error", "reason": "No valid Telegram credential found."}

            result = search_contact(
                bot_token=credential.bot_token,
                name=name,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "contacts": result.get("result", {}).get("contacts", []),
                "count": result.get("result", {}).get("count", 0),
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Message with Name Resolution
    # --------------------------------------------------
    @classmethod
    def send_message_to_name(
        cls,
        user_id: str,
        name: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a contact by searching for their name first.

        This is useful when you have a name instead of a chat_id.
        It searches for the contact and sends the message to the first match.

        Args:
            user_id: The user ID
            name: Name of the recipient to search for
            text: Message text
            parse_mode: "HTML", "Markdown", or "MarkdownV2"
            reply_to_message_id: Message ID to reply to
            bot_id: Optional bot ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            # First search for the contact
            search_result = cls.search_contact(
                user_id=user_id,
                name=name,
                bot_id=bot_id,
            )

            if search_result.get("status") == "error":
                return {
                    "status": "error",
                    "reason": f"Could not find contact '{name}': {search_result.get('reason', search_result.get('details', {}).get('error', 'Unknown error'))}"
                }

            contacts = search_result.get("contacts", [])
            if not contacts:
                return {
                    "status": "error",
                    "reason": f"No contacts found matching '{name}'. Make sure the contact has messaged the bot first."
                }

            # Use the first matching contact
            contact = contacts[0]
            chat_id = contact.get("chat_id")

            # Now send the message
            result = cls.send_message(
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id,
                bot_id=bot_id,
            )

            if result.get("status") == "success":
                result["resolved_contact"] = contact

            return result

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ==========================================================
    # MTProto (User Account) Methods
    # ==========================================================

    @classmethod
    def get_mtproto_credentials(
        cls,
        user_id: str,
        phone_number: Optional[str] = None,
    ) -> Optional[TelegramCredential]:
        """
        Retrieve MTProto (user account) credentials.

        Args:
            user_id: The user ID
            phone_number: Optional phone number to filter

        Returns:
            TelegramCredential if found, None otherwise
        """
        cred_store = cls.get_credential_store()
        filters = {"connection_type": "mtproto"}
        if phone_number:
            filters["phone_number"] = phone_number

        credentials = cred_store.get(user_id=user_id, **filters)
        return credentials[0] if credentials else None

    @classmethod
    def validate_mtproto_connection(
        cls,
        user_id: str,
        phone_number: Optional[str] = None,
    ) -> bool:
        """
        Check if a valid MTProto session exists.
        """
        cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
        return cred is not None and bool(cred.session_string)

    @classmethod
    def start_mtproto_auth(
        cls,
        user_id: str,
        phone_number: str,
        api_id: int,
        api_hash: str,
    ) -> Dict[str, Any]:
        """
        Start MTProto authentication - sends OTP to phone.

        Args:
            user_id: The user ID
            phone_number: Phone number with country code (+1234567890)
            api_id: Telegram API ID from my.telegram.org
            api_hash: Telegram API hash from my.telegram.org

        Returns:
            Dict with phone_code_hash on success, or error
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            # Run async function
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, create task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.start_auth(api_id, api_hash, phone_number)
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.start_auth(api_id, api_hash, phone_number)
                )

            if "error" in result:
                return {"status": "error", "details": result}

            # Get the pending session string - needed to complete auth
            # Telegram requires the same session for send_code_request and sign_in
            pending_session_string = result["result"].get("session_string", "")

            # Store partial credential with the pending session
            cred_store = cls.get_credential_store()
            cred_store.add(TelegramCredential(
                user_id=user_id,
                connection_type="mtproto",
                phone_number=phone_number,
                api_id=api_id,
                api_hash=api_hash,
                session_string=pending_session_string,  # Store pending session
            ))

            return {
                "status": "success",
                "phone_code_hash": result["result"]["phone_code_hash"],
                "phone_number": phone_number,
                "session_string": pending_session_string,  # Return for complete_auth
                "message": "OTP code sent to phone. Use complete_mtproto_auth to finish.",
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def complete_mtproto_auth(
        cls,
        user_id: str,
        phone_number: str,
        code: str,
        phone_code_hash: str,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete MTProto authentication with OTP code.

        Args:
            user_id: The user ID
            phone_number: Phone number used in start_mtproto_auth
            code: OTP code received via SMS/Telegram
            phone_code_hash: Hash from start_mtproto_auth response
            password: Optional 2FA password if enabled

        Returns:
            Dict with user info on success, or error
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            # Get stored credential
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred:
                return {
                    "status": "error",
                    "reason": "No pending auth found. Call start_mtproto_auth first."
                }

            # Get the pending session string from stored credential
            # Telegram requires the same session for send_code_request and sign_in
            pending_session_string = cred.session_string

            # Run async function
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.complete_auth(
                            cred.api_id, cred.api_hash, phone_number,
                            code, phone_code_hash, password,
                            pending_session_string=pending_session_string
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.complete_auth(
                        cred.api_id, cred.api_hash, phone_number,
                        code, phone_code_hash, password,
                        pending_session_string=pending_session_string
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            # Update credential with session
            auth_result = result["result"]
            cred_store = cls.get_credential_store()
            cred_store.add(TelegramCredential(
                user_id=user_id,
                connection_type="mtproto",
                phone_number=phone_number,
                api_id=cred.api_id,
                api_hash=cred.api_hash,
                session_string=auth_result["session_string"],
                account_name=f"{auth_result.get('first_name', '')} {auth_result.get('last_name', '')}".strip(),
                telegram_user_id=auth_result.get("user_id", 0),
            ))

            account_name = f"{auth_result.get('first_name', '')} {auth_result.get('last_name', '')}".strip()
            return {
                "status": "success",
                "user_id": auth_result.get("user_id"),
                "username": auth_result.get("username", ""),
                "name": account_name,
                "phone": auth_result.get("phone", phone_number),
                # Include full credential data for backend storage
                "api_id": cred.api_id,
                "api_hash": cred.api_hash,
                "session_string": auth_result["session_string"],
                "account_name": account_name,
                "telegram_user_id": auth_result.get("user_id", 0),
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_telegram_chats(
        cls,
        user_id: str,
        limit: int = 50,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get list of all conversations (dialogs) using MTProto.

        Args:
            user_id: The user ID
            limit: Maximum number of chats to return
            phone_number: Optional phone number for specific account

        Returns:
            Dict with list of dialogs/chats
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "error",
                    "reason": "No valid MTProto session found. Please authenticate first."
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.get_dialogs(
                            cred.session_string, cred.api_id, cred.api_hash, limit
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.get_dialogs(
                        cred.session_string, cred.api_id, cred.api_hash, limit
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "chats": result["result"]["dialogs"],
                "count": result["result"]["count"],
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def read_telegram_messages(
        cls,
        user_id: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        limit: int = 50,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Read message history from any chat using MTProto.

        Args:
            user_id: The user ID
            chat_id: Chat ID, username, or phone number. Either chat_id or name required.
            name: Contact/chat name to search for. Either chat_id or name required.
            limit: Maximum number of messages to return
            phone_number: Optional phone number for specific account

        Returns:
            Dict with list of messages
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "error",
                    "reason": "No valid MTProto session found. Please authenticate first."
                }

            # Resolve chat_id from name if needed
            actual_chat_id = chat_id
            if not chat_id and name:
                # Search for contact first
                search_result = cls.search_mtproto_contacts(
                    user_id=user_id, query=name, phone_number=phone_number
                )
                if search_result.get("status") == "error":
                    return search_result

                contacts = search_result.get("contacts", [])
                if not contacts:
                    return {
                        "status": "error",
                        "reason": f"No contacts found matching '{name}'."
                    }
                actual_chat_id = contacts[0].get("id")

            if not actual_chat_id:
                return {
                    "status": "error",
                    "reason": "Either chat_id or name must be provided."
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.get_messages(
                            cred.session_string, cred.api_id, cred.api_hash,
                            actual_chat_id, limit
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.get_messages(
                        cred.session_string, cred.api_id, cred.api_hash,
                        actual_chat_id, limit
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "chat": result["result"]["chat"],
                "messages": result["result"]["messages"],
                "count": result["result"]["count"],
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def send_mtproto_message(
        cls,
        user_id: str,
        text: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        reply_to: Optional[int] = None,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message using MTProto (user account).

        Args:
            user_id: The user ID
            text: Message text
            chat_id: Chat ID, username, or phone. Either chat_id or name required.
            name: Contact name to search for. Either chat_id or name required.
            reply_to: Optional message ID to reply to
            phone_number: Optional phone number for specific account

        Returns:
            Dict with sent message info
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "error",
                    "reason": "No valid MTProto session found. Please authenticate first."
                }

            # Resolve chat_id from name if needed
            actual_chat_id = chat_id
            if not chat_id and name:
                search_result = cls.search_mtproto_contacts(
                    user_id=user_id, query=name, phone_number=phone_number
                )
                if search_result.get("status") == "error":
                    return search_result

                contacts = search_result.get("contacts", [])
                if not contacts:
                    return {
                        "status": "error",
                        "reason": f"No contacts found matching '{name}'."
                    }
                actual_chat_id = contacts[0].get("id")

            if not actual_chat_id:
                return {
                    "status": "error",
                    "reason": "Either chat_id or name must be provided."
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.send_message(
                            cred.session_string, cred.api_id, cred.api_hash,
                            actual_chat_id, text, reply_to
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.send_message(
                        cred.session_string, cred.api_id, cred.api_hash,
                        actual_chat_id, text, reply_to
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "message_id": result["result"]["message_id"],
                "chat_id": result["result"]["chat_id"],
                "date": result["result"]["date"],
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def send_mtproto_file(
        cls,
        user_id: str,
        file_path: str,
        chat_id: Optional[Union[int, str]] = None,
        name: Optional[str] = None,
        caption: Optional[str] = None,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a file using MTProto (user account).

        Args:
            user_id: The user ID
            file_path: Path to file or URL
            chat_id: Chat ID, username, or phone. Either chat_id or name required.
            name: Contact name to search for. Either chat_id or name required.
            caption: Optional caption for the file
            phone_number: Optional phone number for specific account

        Returns:
            Dict with sent message info
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "error",
                    "reason": "No valid MTProto session found. Please authenticate first."
                }

            # Resolve chat_id from name if needed
            actual_chat_id = chat_id
            if not chat_id and name:
                search_result = cls.search_mtproto_contacts(
                    user_id=user_id, query=name, phone_number=phone_number
                )
                if search_result.get("status") == "error":
                    return search_result

                contacts = search_result.get("contacts", [])
                if not contacts:
                    return {
                        "status": "error",
                        "reason": f"No contacts found matching '{name}'."
                    }
                actual_chat_id = contacts[0].get("id")

            if not actual_chat_id:
                return {
                    "status": "error",
                    "reason": "Either chat_id or name must be provided."
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.send_file(
                            cred.session_string, cred.api_id, cred.api_hash,
                            actual_chat_id, file_path, caption
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.send_file(
                        cred.session_string, cred.api_id, cred.api_hash,
                        actual_chat_id, file_path, caption
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "message_id": result["result"]["message_id"],
                "chat_id": result["result"]["chat_id"],
                "date": result["result"]["date"],
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def search_mtproto_contacts(
        cls,
        user_id: str,
        query: str,
        limit: int = 20,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for contacts using MTProto.

        Args:
            user_id: The user ID
            query: Search query (name or username)
            limit: Maximum results to return
            phone_number: Optional phone number for specific account

        Returns:
            Dict with matching contacts
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "error",
                    "reason": "No valid MTProto session found. Please authenticate first."
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.search_contacts(
                            cred.session_string, cred.api_id, cred.api_hash,
                            query, limit
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.search_contacts(
                        cred.session_string, cred.api_id, cred.api_hash,
                        query, limit
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "contacts": result["result"]["contacts"],
                "count": result["result"]["count"],
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_mtproto_account_info(
        cls,
        user_id: str,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get information about the authenticated MTProto user.

        Args:
            user_id: The user ID
            phone_number: Optional phone number for specific account

        Returns:
            Dict with user info
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "error",
                    "reason": "No valid MTProto session found. Please authenticate first."
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.get_me(
                            cred.session_string, cred.api_id, cred.api_hash
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.get_me(
                        cred.session_string, cred.api_id, cred.api_hash
                    )
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "user": result["result"],
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def validate_mtproto_session(
        cls,
        user_id: str,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate if a MTProto session is still active.

        Args:
            user_id: The user ID
            phone_number: Optional phone number for specific account

        Returns:
            Dict with validation status
        """
        if not MTPROTO_AVAILABLE:
            return {
                "status": "error",
                "reason": "MTProto support not available. Install telethon: pip install telethon"
            }

        try:
            cred = cls.get_mtproto_credentials(user_id=user_id, phone_number=phone_number)
            if not cred or not cred.session_string:
                return {
                    "status": "success",
                    "valid": False,
                    "reason": "No session found.",
                }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        mtproto.validate_session(
                            cred.session_string, cred.api_id, cred.api_hash
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    mtproto.validate_session(
                        cred.session_string, cred.api_id, cred.api_hash
                    )
                )

            return {
                "status": "success",
                "valid": result["result"]["valid"],
                "user_id": result["result"].get("user_id"),
                "username": result["result"].get("username", ""),
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
