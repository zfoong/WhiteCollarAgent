import asyncio
from typing import Optional, Dict, Any

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from core.external_libraries.external_app_library import ExternalAppLibrary


def _run_async(coro):
    """Run an async coroutine from sync code, reusing the existing event loop when possible.

    With nest_asyncio applied, run_until_complete works even inside a running loop.
    We avoid asyncio.run() because it creates a NEW event loop, which breaks Playwright
    objects that are bound to the TUI's existing loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists at all (e.g., running from a plain thread)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.whatsapp.credentials import WhatsAppCredential
from core.external_libraries.whatsapp.helpers.whatsapp_web_helpers import (
    send_whatsapp_web_message,
    send_whatsapp_web_media,
    reconnect_whatsapp_web_session,
    list_persisted_whatsapp_web_sessions,
    get_whatsapp_web_chat_messages,
    get_whatsapp_web_unread_chats,
    get_whatsapp_web_contact_phone,
    get_session_status,
)

from core.logger import logger

class WhatsAppAppLibrary(ExternalAppLibrary):
    _name = "WhatsApp"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the WhatsApp library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=WhatsAppCredential,
            persistence_file="whatsapp_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("WhatsAppAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, phone_number_id: Optional[str] = None) -> bool:
        """
        Returns True if a WhatsApp credential exists for the given
        user_id and optional phone_number_id, False otherwise.
        """
        cred_store = cls.get_credential_store()
        if phone_number_id:
            credentials = cred_store.get(user_id=user_id, phone_number_id=phone_number_id)
        else:
            credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        phone_number_id: Optional[str] = None
    ) -> Optional[WhatsAppCredential]:
        """
        Retrieve the WhatsApp credential for the given user_id and optional phone_number_id.
        Returns the credential if found, None otherwise.
        """
        logger.debug(f"Retrieving WhatsApp credentials for user_id={user_id}, phone_number_id={phone_number_id}")
        cred_store = cls.get_credential_store()
        if phone_number_id:
            credentials = cred_store.get(user_id=user_id, phone_number_id=phone_number_id)
        else:
            credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    # --------------------------------------------------
    # Send Text Message
    # --------------------------------------------------
    @classmethod
    def send_text_message(
        cls,
        user_id: str,
        to: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp Web.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            message: The text message to send
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            logger.debug(f"Using WhatsApp credentials: {credential.to_dict()}")
            logger.debug(f"Sending text message to {to}: {message}")

            session_id = credential.session_id or credential.phone_number_id

            async def send_with_auto_reconnect():
                """Try to send, auto-reconnect if session lost, then retry."""
                import re
                recipient = to

                # Resolve contact name if 'to' contains letters
                if re.search(r'[a-zA-Z]', to):
                    logger.info(f"[WhatsApp Web] Resolving contact name '{to}'...")
                    resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)

                    if not resolve_res.get("success") and "not connected" in resolve_res.get("error", "").lower():
                         logger.info(f"[WhatsApp Web] Session not connected during resolution, attempting auto-reconnect...")
                         reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                         if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                             resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)

                    if resolve_res.get("success") and resolve_res.get("phone"):
                        recipient = resolve_res.get("phone")
                        logger.info(f"[WhatsApp Web] Resolved '{to}' to {recipient}")
                    else:
                        return {"success": False, "error": f"Could not resolve contact '{to}': {resolve_res.get('error')}"}

                result = await send_whatsapp_web_message(session_id=session_id, to=recipient, message=message)

                if not result.get("success") and "not connected" in result.get("error", "").lower():
                    logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                    reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)

                    if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                        logger.info(f"[WhatsApp Web] Auto-reconnect successful, retrying send...")
                        result = await send_whatsapp_web_message(session_id=session_id, to=recipient, message=message)
                    else:
                        reconnect_status = reconnect_result.get("status", "unknown")
                        reconnect_error = reconnect_result.get("error", "")
                        if reconnect_status == "qr_required":
                            return {
                                "success": False,
                                "error": "WhatsApp Web session expired. The device was unlinked from your phone. Please start a new session and scan the QR code."
                            }
                        else:
                            return {
                                "success": False,
                                "error": f"Auto-reconnect failed ({reconnect_status}): {reconnect_error}. Please start a new WhatsApp Web session."
                            }

                return result

            result = _run_async(send_with_auto_reconnect())

            if result.get("success"):
                return {
                    "status": "success",
                    "message_id": result.get("timestamp", "sent"),
                    "to": to,
                    "via": "whatsapp_web",
                }
            else:
                error_msg = result.get("error", "Failed to send via WhatsApp Web")
                return {"status": "error", "reason": error_msg}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Media Message
    # --------------------------------------------------
    @classmethod
    def send_media_message(
        cls,
        user_id: str,
        to: str,
        media_type: str,
        media_url: Optional[str] = None,
        media_id: Optional[str] = None,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a media message via WhatsApp Web.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            media_type: Type of media: "image", "video", "audio", "document"
            media_url: File path of the media
            media_id: Unused (kept for API compatibility)
            caption: Optional caption for the media
            filename: Optional filename for documents
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            if not media_url:
                return {"status": "error", "reason": "WhatsApp Web requires media_url (file path) to send media"}

            session_id = credential.session_id or credential.phone_number_id
            media_path = media_url

            async def send_media_with_auto_reconnect():
                """Try to send media, auto-reconnect if session lost, then retry."""
                import re
                recipient = to

                # Resolve contact name if 'to' contains letters
                if re.search(r'[a-zA-Z]', to):
                    logger.info(f"[WhatsApp Web] Resolving contact name '{to}'...")
                    resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)

                    if not resolve_res.get("success") and "not connected" in resolve_res.get("error", "").lower():
                         logger.info(f"[WhatsApp Web] Session not connected during resolution, attempting auto-reconnect...")
                         reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                         if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                             resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)

                    if resolve_res.get("success") and resolve_res.get("phone"):
                        recipient = resolve_res.get("phone")
                        logger.info(f"[WhatsApp Web] Resolved '{to}' to {recipient}")
                    else:
                        return {"success": False, "error": f"Could not resolve contact '{to}': {resolve_res.get('error')}"}

                result = await send_whatsapp_web_media(session_id=session_id, to=recipient, media_path=media_path, caption=caption)

                if not result.get("success") and "not connected" in result.get("error", "").lower():
                    logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                    reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)

                    if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                        logger.info(f"[WhatsApp Web] Auto-reconnect successful, retrying send...")
                        result = await send_whatsapp_web_media(session_id=session_id, to=recipient, media_path=media_path, caption=caption)
                    else:
                        reconnect_status = reconnect_result.get("status", "unknown")
                        reconnect_error = reconnect_result.get("error", "")
                        if reconnect_status == "qr_required":
                            return {
                                "success": False,
                                "error": "WhatsApp Web session expired. The device was unlinked from your phone. Please start a new session and scan the QR code."
                            }
                        else:
                            return {
                                "success": False,
                                "error": f"Auto-reconnect failed ({reconnect_status}): {reconnect_error}. Please start a new WhatsApp Web session."
                            }

                return result

            result = _run_async(send_media_with_auto_reconnect())

            if result.get("success"):
                return {
                    "status": "success",
                    "message_id": result.get("timestamp", "sent"),
                    "to": to,
                    "media_type": media_type,
                    "via": "whatsapp_web",
                }
            else:
                return {"status": "error", "reason": result.get("error", "Failed to send media via WhatsApp Web")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Chat History
    # --------------------------------------------------
    @classmethod
    def get_chat_history(
        cls,
        user_id: str,
        phone_number: str,
        limit: int = 50,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get chat history from WhatsApp Web.

        Args:
            user_id: The user ID
            phone_number: The phone number to get history from
            limit: Maximum number of messages
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and messages
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            session_id = credential.session_id or credential.phone_number_id

            async def get_messages_task():
                result = await get_whatsapp_web_chat_messages(session_id=session_id, phone_number=phone_number, limit=limit)
                if not result.get("success") and "not connected" in result.get("error", "").lower():
                    logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                    reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                    if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                        return await get_whatsapp_web_chat_messages(session_id=session_id, phone_number=phone_number, limit=limit)
                return result

            result = _run_async(get_messages_task())

            if result.get("success"):
                return {
                    "status": "success",
                    "messages": result.get("messages", []),
                    "count": result.get("count", 0),
                    "via": "whatsapp_web",
                }
            else:
                return {"status": "error", "reason": result.get("error", "Failed to get messages via WhatsApp Web")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Unread Chats
    # --------------------------------------------------
    @classmethod
    def get_unread_chats(
        cls,
        user_id: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get list of unread chats from WhatsApp Web.

        Args:
            user_id: The user ID
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and unread chats
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            session_id = credential.session_id or credential.phone_number_id

            async def get_unread_task():
                result = await get_whatsapp_web_unread_chats(session_id=session_id)
                if not result.get("success") and "not connected" in result.get("error", "").lower():
                    logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                    reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                    if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                        return await get_whatsapp_web_unread_chats(session_id=session_id)
                return result

            result = _run_async(get_unread_task())

            if result.get("success"):
                return {
                    "status": "success",
                    "unread_chats": result.get("unread_chats", []),
                    "count": result.get("count", 0),
                    "via": "whatsapp_web",
                }
            else:
                return {"status": "error", "reason": result.get("error", "Failed to get unread chats via WhatsApp Web")}

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
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for a contact by name and return details (name, phone).

        Args:
            user_id: The user ID
            name: Contact name to search for
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and contact info
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            session_id = credential.session_id or credential.phone_number_id

            async def search_task():
                result = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=name)
                if not result.get("success") and "not connected" in result.get("error", "").lower():
                    logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                    reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                    if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                        return await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=name)
                return result

            result = _run_async(search_task())

            if result.get("success"):
                return {
                    "status": "success",
                    "contact": {
                        "name": result.get("name"),
                        "phone": result.get("phone")
                    },
                    "via": "whatsapp_web",
                }
            else:
                error_response = {"status": "error", "reason": result.get("error", "Failed to search contact via WhatsApp Web")}
                if "debug" in result:
                    error_response["debug"] = result["debug"]
                return error_response

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # WhatsApp Web Session Management
    # --------------------------------------------------
    @classmethod
    def reconnect_whatsapp_web(
        cls,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reconnect to an existing WhatsApp Web session after agent restart.

        This uses persisted browser data to restore the session without
        requiring a new QR code scan (if the device is still linked on the phone).

        Args:
            user_id: The user ID
            session_id: Optional specific session ID to reconnect. If not provided,
                        will try to find a session from stored credentials.

        Returns:
            Dict with status and session info
        """
        try:
            if not session_id:
                credentials = cls.get_credential_store().get(user_id=user_id)
                if not credentials:
                    return {
                        "status": "error",
                        "reason": "No WhatsApp Web credentials found for this user.",
                        "hint": "Start a new session with QR code pairing first."
                    }
                session_id = credentials[0].session_id or credentials[0].phone_number_id

            if not session_id:
                return {"status": "error", "reason": "No session_id available to reconnect."}

            result = _run_async(
                reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
            )

            return result

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def list_persisted_sessions(cls, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all WhatsApp Web sessions that have persisted data on disk.

        These sessions can potentially be reconnected without a new QR scan
        if the device is still linked on the phone.

        Args:
            user_id: Optional user ID to filter sessions (matches with stored credentials)

        Returns:
            Dict with list of persisted sessions
        """
        try:
            sessions = list_persisted_whatsapp_web_sessions()

            if user_id:
                credentials = cls.get_credential_store().get(user_id=user_id)
                user_session_ids = {
                    c.session_id or c.phone_number_id
                    for c in credentials
                }
                sessions = [s for s in sessions if s["session_id"] in user_session_ids]

            return {
                "status": "success",
                "sessions": sessions,
                "count": len(sessions),
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_web_session_status(
        cls,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the status of a WhatsApp Web session.
        """
        if not session_id:
             credentials = cls.get_credential_store().get(user_id=user_id)
             if credentials:
                 session_id = credentials[0].session_id or credentials[0].phone_number_id

        if not session_id:
             return cls.list_persisted_sessions(user_id=user_id)

        result = _run_async(get_session_status(session_id))

        if result:
            return result
        return {"status": "error", "message": "Session not found"}
