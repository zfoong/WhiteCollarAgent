import asyncio
from typing import Optional, Dict, Any, List
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.whatsapp.credentials import WhatsAppCredential
from core.external_libraries.whatsapp.helpers.whatsapp_helpers import (
    send_text_message as send_text_message_api,
    send_template_message,
    send_media_message as send_media_message_api,
    send_location_message,
    send_contact_message,
    send_interactive_message,
    mark_message_as_read,
    upload_media,
    get_media_url,
    get_business_profile,
    get_phone_number_info,
    get_message_templates,
)
from core.external_libraries.whatsapp.helpers.whatsapp_web_helpers import (
    send_whatsapp_web_message,
    send_whatsapp_web_media,
    reconnect_whatsapp_web_session,
    list_persisted_whatsapp_web_sessions,
    get_whatsapp_web_chat_messages,
    get_whatsapp_web_unread_chats,
    get_whatsapp_web_contact_phone,
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
        preview_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            message: The text message to send
            phone_number_id: Optional phone number ID to use specific credentials
            preview_url: Whether to show URL previews

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            logger.debug(f"Using WhatsApp credentials: {credential.to_dict()}")
            logger.debug(f"Sending text message to {to}: {message}")

            # Route based on connection type
            if credential.connection_type == "whatsapp_web":
                # Use WhatsApp Web
                session_id = credential.session_id or credential.phone_number_id

                async def send_with_auto_reconnect():
                    """Try to send, auto-reconnect if session lost, then retry."""
                    import re
                    recipient = to
                    
                    # Resolve contact name if 'to' contains letters
                    if re.search(r'[a-zA-Z]', to):
                        logger.info(f"[WhatsApp Web] Resolving contact name '{to}'...")
                        # Try resolution
                        resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)
                        
                        # If failed because not connected, we might need to reconnect FIRST before resolving
                        if not resolve_res.get("success") and "not connected" in resolve_res.get("error", "").lower():
                             logger.info(f"[WhatsApp Web] Session not connected during resolution, attempting auto-reconnect...")
                             reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                             if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                                 # Retry resolution
                                 resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)
                        
                        if resolve_res.get("success") and resolve_res.get("phone"):
                            recipient = resolve_res.get("phone")
                            logger.info(f"[WhatsApp Web] Resolved '{to}' to {recipient}")
                        else:
                            return {"status": "error", "reason": f"Could not resolve contact '{to}': {resolve_res.get('error')}"}

                    result = await send_whatsapp_web_message(session_id=session_id, to=recipient, message=message)

                    # If session not connected (and we didn't already reconnect above), try to reconnect
                    if not result.get("success") and "not connected" in result.get("error", "").lower():
                        logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                        reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)

                        if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                            logger.info(f"[WhatsApp Web] Auto-reconnect successful, retrying send...")
                            # Retry the send after successful reconnect
                            result = await send_whatsapp_web_message(session_id=session_id, to=recipient, message=message)
                        else:
                            # Reconnect failed - include helpful info
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

                try:
                    result = asyncio.get_event_loop().run_until_complete(send_with_auto_reconnect())
                except RuntimeError:
                    # If no event loop, create one
                    result = asyncio.run(send_with_auto_reconnect())

                if result.get("success"):
                    return {
                        "status": "success",
                        "message_id": result.get("timestamp", "sent"),  # WhatsApp Web doesn't return message IDs
                        "to": to,
                        "via": "whatsapp_web",
                    }
                else:
                    error_msg = result.get("error", "Failed to send via WhatsApp Web")
                    return {"status": "error", "reason": error_msg}
            else:
                # Use Business API
                result = send_text_message_api(
                    access_token=credential.access_token,
                    phone_number_id=credential.phone_number_id,
                    to=to,
                    message=message,
                    preview_url=preview_url,
                )

                if "error" in result:
                    return {"status": "error", "details": result}

                return {
                    "status": "success",
                    "message_id": result.get("messages", [{}])[0].get("id"),
                    "to": to,
                    "via": "business_api",
                }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Template Message
    # --------------------------------------------------
    @classmethod
    def send_template_message(
        cls,
        user_id: str,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a template message via WhatsApp.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            template_name: Name of the approved template
            language_code: Language code for the template
            components: Optional template components
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Template messages are only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Template messages are only supported via WhatsApp Business API, not WhatsApp Web."}

            result = send_template_message(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
                to=to,
                template_name=template_name,
                language_code=language_code,
                components=components,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "message_id": result.get("messages", [{}])[0].get("id"),
                "to": to,
                "template": template_name,
            }

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
        Send a media message via WhatsApp.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            media_type: Type of media: "image", "video", "audio", "document"
            media_url: Public URL of the media
            media_id: Media ID from previously uploaded media
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

            # Route based on connection type
            if credential.connection_type == "whatsapp_web":
                # WhatsApp Web requires a local file path, not URL
                if not media_url and not media_id:
                    return {"status": "error", "reason": "WhatsApp Web requires media_url (file path) to send media"}

                session_id = credential.session_id or credential.phone_number_id
                media_path = media_url  # For WhatsApp Web, media_url should be a local file path

                async def send_media_with_auto_reconnect():
                    """Try to send media, auto-reconnect if session lost, then retry."""
                    import re
                    recipient = to

                    # Resolve contact name if 'to' contains letters
                    if re.search(r'[a-zA-Z]', to):
                        logger.info(f"[WhatsApp Web] Resolving contact name '{to}'...")
                        # Try resolution
                        resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)
                        
                        # If failed because not connected, we might need to reconnect FIRST before resolving
                        if not resolve_res.get("success") and "not connected" in resolve_res.get("error", "").lower():
                             logger.info(f"[WhatsApp Web] Session not connected during resolution, attempting auto-reconnect...")
                             reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                             if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                                 # Retry resolution
                                 resolve_res = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=to)
                        
                        if resolve_res.get("success") and resolve_res.get("phone"):
                            recipient = resolve_res.get("phone")
                            logger.info(f"[WhatsApp Web] Resolved '{to}' to {recipient}")
                        else:
                            return {"status": "error", "reason": f"Could not resolve contact '{to}': {resolve_res.get('error')}"}

                    result = await send_whatsapp_web_media(session_id=session_id, to=recipient, media_path=media_path, caption=caption)

                    # If session not connected, try to reconnect automatically
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

                try:
                    result = asyncio.get_event_loop().run_until_complete(send_media_with_auto_reconnect())
                except RuntimeError:
                    result = asyncio.run(send_media_with_auto_reconnect())

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
            else:
                # Business API
                result = send_media_message_api(
                    access_token=credential.access_token,
                    phone_number_id=credential.phone_number_id,
                    to=to,
                    media_type=media_type,
                    media_url=media_url,
                    media_id=media_id,
                    caption=caption,
                    filename=filename,
                )

                if "error" in result:
                    return {"status": "error", "details": result}

                return {
                    "status": "success",
                    "message_id": result.get("messages", [{}])[0].get("id"),
                    "to": to,
                    "media_type": media_type,
                    "via": "business_api",
                }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Location Message
    # --------------------------------------------------
    @classmethod
    def send_location_message(
        cls,
        user_id: str,
        to: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a location message via WhatsApp.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            latitude: Location latitude
            longitude: Location longitude
            name: Optional name of the location
            address: Optional address of the location
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Location messages are only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Location messages are only supported via WhatsApp Business API, not WhatsApp Web."}

            result = send_location_message(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
                to=to,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "message_id": result.get("messages", [{}])[0].get("id"),
                "to": to,
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Send Interactive Message
    # --------------------------------------------------
    @classmethod
    def send_interactive_message(
        cls,
        user_id: str,
        to: str,
        interactive_type: str,
        body_text: str,
        action: Dict[str, Any],
        header: Optional[Dict[str, Any]] = None,
        footer_text: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an interactive message (buttons, list) via WhatsApp.

        Args:
            user_id: The user ID
            to: Recipient phone number (with country code)
            interactive_type: Type: "button", "list", "product", "product_list"
            body_text: The main body text
            action: The action object (buttons, sections, etc.)
            header: Optional header object
            footer_text: Optional footer text
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Interactive messages are only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Interactive messages are only supported via WhatsApp Business API, not WhatsApp Web."}

            interactive_obj: Dict[str, Any] = {
                "body": {"text": body_text},
                "action": action,
            }
            if header:
                interactive_obj["header"] = header
            if footer_text:
                interactive_obj["footer"] = {"text": footer_text}

            result = send_interactive_message(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
                to=to,
                interactive_type=interactive_type,
                interactive_obj=interactive_obj,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "message_id": result.get("messages", [{}])[0].get("id"),
                "to": to,
                "type": interactive_type,
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Mark Message as Read
    # --------------------------------------------------
    @classmethod
    def mark_as_read(
        cls,
        user_id: str,
        message_id: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mark a message as read.

        Args:
            user_id: The user ID
            message_id: The ID of the message to mark as read
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Mark as read is only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Mark as read is only supported via WhatsApp Business API, not WhatsApp Web."}

            result = mark_message_as_read(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
                message_id=message_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "message_id": message_id}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Upload Media
    # --------------------------------------------------
    @classmethod
    def upload_media(
        cls,
        user_id: str,
        file_path: str,
        media_type: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload media to WhatsApp servers.

        Args:
            user_id: The user ID
            file_path: Local path to the file to upload
            media_type: MIME type of the media
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and media ID
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Upload media is only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Upload media is only supported via WhatsApp Business API, not WhatsApp Web."}

            result = upload_media(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
                file_path=file_path,
                media_type=media_type,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "media_id": result.get("id")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Media URL
    # --------------------------------------------------
    @classmethod
    def get_media_url(
        cls,
        user_id: str,
        media_id: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the URL of an uploaded media file.

        Args:
            user_id: The user ID
            media_id: The media ID
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and media URL
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Get media URL is only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Get media URL is only supported via WhatsApp Business API, not WhatsApp Web."}

            result = get_media_url(
                access_token=credential.access_token,
                media_id=media_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {
                "status": "success",
                "url": result.get("url"),
                "mime_type": result.get("mime_type"),
                "sha256": result.get("sha256"),
                "file_size": result.get("file_size"),
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Business Profile
    # --------------------------------------------------
    @classmethod
    def get_business_profile(
        cls,
        user_id: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the WhatsApp Business profile.

        Args:
            user_id: The user ID
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and profile data
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Get business profile is only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Get business profile is only supported via WhatsApp Business API, not WhatsApp Web."}

            result = get_business_profile(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "profile": result.get("data", [{}])[0]}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Phone Number Info
    # --------------------------------------------------
    @classmethod
    def get_phone_number_info(
        cls,
        user_id: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get information about the WhatsApp phone number.

        Args:
            user_id: The user ID
            phone_number_id: Optional phone number ID to use specific credentials

        Returns:
            Dict with status and phone number info
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Get phone number info is only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Get phone number info is only supported via WhatsApp Business API, not WhatsApp Web."}

            result = get_phone_number_info(
                access_token=credential.access_token,
                phone_number_id=credential.phone_number_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "phone_info": result}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Message Templates
    # --------------------------------------------------
    @classmethod
    def get_message_templates(
        cls,
        user_id: str,
        phone_number_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Get message templates for the WhatsApp Business Account.

        Args:
            user_id: The user ID
            phone_number_id: Optional phone number ID to use specific credentials
            limit: Maximum number of templates to return

        Returns:
            Dict with status and templates list
        """
        try:
            credential = cls.get_credentials(user_id=user_id, phone_number_id=phone_number_id)
            if not credential:
                return {"status": "error", "reason": "No valid WhatsApp credential found."}

            # Get message templates is only supported via Business API
            if credential.connection_type == "whatsapp_web":
                return {"status": "error", "reason": "Get message templates is only supported via WhatsApp Business API, not WhatsApp Web."}

            result = get_message_templates(
                access_token=credential.access_token,
                business_account_id=credential.business_account_id,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "templates": result.get("data", [])}

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
        Get chat history from WhatsApp.

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

            # Only supported via WhatsApp Web for now
            if credential.connection_type == "whatsapp_web":
                session_id = credential.session_id or credential.phone_number_id
                
                async def get_messages_task():
                    result = await get_whatsapp_web_chat_messages(session_id=session_id, phone_number=phone_number, limit=limit)
                    # If not connected, try reconnect
                    if not result.get("success") and "not connected" in result.get("error", "").lower():
                        logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                        reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                        if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                            return await get_whatsapp_web_chat_messages(session_id=session_id, phone_number=phone_number, limit=limit)
                    return result

                try:
                    result = asyncio.get_event_loop().run_until_complete(get_messages_task())
                except RuntimeError:
                    result = asyncio.run(get_messages_task())

                if result.get("success"):
                    return {
                        "status": "success",
                        "messages": result.get("messages", []),
                        "count": result.get("count", 0),
                        "via": "whatsapp_web",
                    }
                else:
                    return {"status": "error", "reason": result.get("error", "Failed to get messages via WhatsApp Web")}
            else:
                return {"status": "error", "reason": "Get chat history is only supported via WhatsApp Web connection type currently."}

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
        Get list of unread chats from WhatsApp.

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

            # Only supported via WhatsApp Web for now
            if credential.connection_type == "whatsapp_web":
                session_id = credential.session_id or credential.phone_number_id
                
                async def get_unread_task():
                    result = await get_whatsapp_web_unread_chats(session_id=session_id)
                    # If not connected, try reconnect
                    if not result.get("success") and "not connected" in result.get("error", "").lower():
                        logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                        reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                        if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                            return await get_whatsapp_web_unread_chats(session_id=session_id)
                    return result

                try:
                    result = asyncio.get_event_loop().run_until_complete(get_unread_task())
                except RuntimeError:
                    result = asyncio.run(get_unread_task())

                if result.get("success"):
                    return {
                        "status": "success",
                        "unread_chats": result.get("unread_chats", []),
                        "count": result.get("count", 0),
                        "via": "whatsapp_web",
                    }
                else:
                    return {"status": "error", "reason": result.get("error", "Failed to get unread chats via WhatsApp Web")}
            else:
                return {"status": "error", "reason": "Get unread chats is only supported via WhatsApp Web connection type currently."}

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

            if credential.connection_type == "whatsapp_web":
                session_id = credential.session_id or credential.phone_number_id
                
                async def search_task():
                    result = await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=name)
                    # Auto-reconnect logic
                    if not result.get("success") and "not connected" in result.get("error", "").lower():
                        logger.info(f"[WhatsApp Web] Session not connected, attempting auto-reconnect...")
                        reconnect_result = await reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                        if reconnect_result.get("success") and reconnect_result.get("status") == "connected":
                            return await get_whatsapp_web_contact_phone(session_id=session_id, contact_name=name)
                    return result

                try:
                    result = asyncio.get_event_loop().run_until_complete(search_task())
                except RuntimeError:
                    result = asyncio.run(search_task())

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
                    # Include debug info if available
                    if "debug" in result:
                        error_response["debug"] = result["debug"]
                    return error_response
            else:
                return {"status": "error", "reason": "Search contact is only supported via WhatsApp Web connection type currently."}

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
            # If no session_id provided, try to get it from stored credentials
            if not session_id:
                credentials = cls.get_credential_store().get(user_id=user_id)
                whatsapp_web_creds = [c for c in credentials if c.connection_type == "whatsapp_web"]
                if not whatsapp_web_creds:
                    return {
                        "status": "error",
                        "reason": "No WhatsApp Web credentials found for this user.",
                        "hint": "Start a new session with QR code pairing first."
                    }
                # Use the session_id from credentials
                session_id = whatsapp_web_creds[0].session_id or whatsapp_web_creds[0].phone_number_id

            if not session_id:
                return {"status": "error", "reason": "No session_id available to reconnect."}

            # Try to reconnect
            try:
                result = asyncio.get_event_loop().run_until_complete(
                    reconnect_whatsapp_web_session(session_id=session_id, user_id=user_id)
                )
            except RuntimeError:
                result = asyncio.run(
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

            # If user_id provided, try to match with stored credentials
            if user_id:
                credentials = cls.get_credential_store().get(user_id=user_id)
                user_session_ids = {
                    c.session_id or c.phone_number_id
                    for c in credentials
                    if c.connection_type == "whatsapp_web"
                }
                sessions = [s for s in sessions if s["session_id"] in user_session_ids]

            return {
                "status": "success",
                "sessions": sessions,
                "count": len(sessions),
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
