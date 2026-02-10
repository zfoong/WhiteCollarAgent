from core.action.action_framework.registry import action


@action(
    name="send_whatsapp_message",
    description="Send a text message via WhatsApp Business API.",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number with country code.", "example": "1234567890"},
        "message": {"type": "string", "description": "Message text.", "example": "Hello!"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_message(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    creds = [c for c in WhatsAppAppLibrary.get_credential_store().get(
        input_data.get("user_id", "local")) if c.connection_type == "business_api"]
    if not creds:
        return {"status": "error", "message": "No WhatsApp Business credential. Use /whatsapp login first."}
    cred = creds[0]
    from core.external_libraries.whatsapp.helpers.whatsapp_helpers import send_text_message
    result = send_text_message(cred.access_token, cred.phone_number_id,
                               input_data["to"], input_data["message"])
    return {"status": "success", "result": result}


@action(
    name="send_whatsapp_media",
    description="Send a media message (image, video, audio, document) via WhatsApp.",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number with country code.", "example": "1234567890"},
        "media_type": {"type": "string", "description": "Type: image, video, audio, document.", "example": "image"},
        "media_url": {"type": "string", "description": "Public URL of the media.", "example": "https://example.com/photo.jpg"},
        "caption": {"type": "string", "description": "Optional caption.", "example": "Check this out"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_media(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    creds = [c for c in WhatsAppAppLibrary.get_credential_store().get(
        input_data.get("user_id", "local")) if c.connection_type == "business_api"]
    if not creds:
        return {"status": "error", "message": "No WhatsApp Business credential. Use /whatsapp login first."}
    cred = creds[0]
    from core.external_libraries.whatsapp.helpers.whatsapp_helpers import send_media_message
    result = send_media_message(cred.access_token, cred.phone_number_id,
                                input_data["to"], input_data["media_type"],
                                media_url=input_data.get("media_url"),
                                caption=input_data.get("caption"))
    return {"status": "success", "result": result}


@action(
    name="send_whatsapp_template",
    description="Send a template message via WhatsApp Business API.",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number.", "example": "1234567890"},
        "template_name": {"type": "string", "description": "Approved template name.", "example": "hello_world"},
        "language_code": {"type": "string", "description": "Language code.", "example": "en_US"},
        "components": {"type": "array", "description": "Optional template components.", "example": []},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_template(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    creds = [c for c in WhatsAppAppLibrary.get_credential_store().get(
        input_data.get("user_id", "local")) if c.connection_type == "business_api"]
    if not creds:
        return {"status": "error", "message": "No WhatsApp Business credential. Use /whatsapp login first."}
    cred = creds[0]
    from core.external_libraries.whatsapp.helpers.whatsapp_helpers import send_template_message
    result = send_template_message(cred.access_token, cred.phone_number_id,
                                   input_data["to"], input_data["template_name"],
                                   language_code=input_data.get("language_code", "en_US"),
                                   components=input_data.get("components"))
    return {"status": "success", "result": result}


@action(
    name="get_whatsapp_profile",
    description="Get the WhatsApp Business profile.",
    action_sets=["whatsapp"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_profile(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    creds = [c for c in WhatsAppAppLibrary.get_credential_store().get(
        input_data.get("user_id", "local")) if c.connection_type == "business_api"]
    if not creds:
        return {"status": "error", "message": "No WhatsApp Business credential. Use /whatsapp login first."}
    cred = creds[0]
    from core.external_libraries.whatsapp.helpers.whatsapp_helpers import get_business_profile
    result = get_business_profile(cred.access_token, cred.phone_number_id)
    return {"status": "success", "result": result}


@action(
    name="send_whatsapp_location",
    description="Send a location message via WhatsApp.",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number.", "example": "1234567890"},
        "latitude": {"type": "number", "description": "Latitude.", "example": 37.7749},
        "longitude": {"type": "number", "description": "Longitude.", "example": -122.4194},
        "name": {"type": "string", "description": "Location name.", "example": "HQ"},
        "address": {"type": "string", "description": "Location address.", "example": "123 Main St"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_location(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.send_location_message(
        user_id=input_data.get("user_id", "local"),
        to=input_data["to"],
        latitude=input_data["latitude"],
        longitude=input_data["longitude"],
        name=input_data.get("name"),
        address=input_data.get("address")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="send_whatsapp_interactive",
    description="Send an interactive message (buttons/list).",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number.", "example": "1234567890"},
        "interactive_type": {"type": "string", "description": "button, list, etc.", "example": "button"},
        "body_text": {"type": "string", "description": "Body text.", "example": "Choose one"},
        "action": {"type": "object", "description": "Action object.", "example": {}},
        "header": {"type": "object", "description": "Optional header.", "example": {}},
        "footer_text": {"type": "string", "description": "Optional footer.", "example": "Footer"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_interactive(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.send_interactive_message(
        user_id=input_data.get("user_id", "local"),
        to=input_data["to"],
        interactive_type=input_data["interactive_type"],
        body_text=input_data["body_text"],
        action=input_data["action"],
        header=input_data.get("header"),
        footer_text=input_data.get("footer_text")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="mark_whatsapp_read",
    description="Mark a WhatsApp message as read.",
    action_sets=["whatsapp"],
    input_schema={
        "message_id": {"type": "string", "description": "Message ID.", "example": "msg123"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def mark_whatsapp_read(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.mark_as_read(
        user_id=input_data.get("user_id", "local"),
        message_id=input_data["message_id"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="upload_whatsapp_media",
    description="Upload media to WhatsApp.",
    action_sets=["whatsapp"],
    input_schema={
        "file_path": {"type": "string", "description": "Local file path.", "example": "/path/to/img.jpg"},
        "media_type": {"type": "string", "description": "MIME type.", "example": "image/jpeg"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def upload_whatsapp_media(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.upload_media(
        user_id=input_data.get("user_id", "local"),
        file_path=input_data["file_path"],
        media_type=input_data["media_type"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_whatsapp_media_url",
    description="Get URL of uploaded media.",
    action_sets=["whatsapp"],
    input_schema={
        "media_id": {"type": "string", "description": "Media ID.", "example": "media123"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_media_url(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.get_media_url(
        user_id=input_data.get("user_id", "local"),
        media_id=input_data["media_id"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_whatsapp_phone_info",
    description="Get WhatsApp phone number info.",
    action_sets=["whatsapp"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_phone_info(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.get_phone_number_info(
        user_id=input_data.get("user_id", "local")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_whatsapp_templates",
    description="Get WhatsApp message templates.",
    action_sets=["whatsapp"],
    input_schema={
        "limit": {"type": "integer", "description": "Limit.", "example": 100},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_templates(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.get_message_templates(
        user_id=input_data.get("user_id", "local"),
        limit=input_data.get("limit", 100)
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_whatsapp_chat_history",
    description="Get chat history (WhatsApp Web).",
    action_sets=["whatsapp"],
    input_schema={
        "phone_number": {"type": "string", "description": "Phone number.", "example": "1234567890"},
        "limit": {"type": "integer", "description": "Limit.", "example": 50},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_chat_history(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.get_chat_history(
        user_id=input_data.get("user_id", "local"),
        phone_number=input_data["phone_number"],
        limit=input_data.get("limit", 50)
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_whatsapp_unread_chats",
    description="Get unread chats (WhatsApp Web).",
    action_sets=["whatsapp"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_unread_chats(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.get_unread_chats(
        user_id=input_data.get("user_id", "local")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="search_whatsapp_contact",
    description="Search contact by name (WhatsApp Web).",
    action_sets=["whatsapp"],
    input_schema={
        "name": {"type": "string", "description": "Contact name.", "example": "John Doe"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def search_whatsapp_contact(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.search_contact(
        user_id=input_data.get("user_id", "local"),
        name=input_data["name"]
    )
    return {"status": result.get("status", "success"), "result": result}
