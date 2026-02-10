from core.action.action_framework.registry import action


@action(
    name="send_whatsapp_web_text_message",
    description="Send a text message via WhatsApp Web.",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number.", "example": "1234567890"},
        "message": {"type": "string", "description": "Message text.", "example": "Hello!"},
        "session_id": {"type": "string", "description": "Optional session ID.", "example": "session_1"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_web_text_message(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.send_text_message(
        user_id=input_data.get("user_id", "local"),
        to=input_data["to"],
        message=input_data["message"],
        phone_number_id=input_data.get("session_id")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="send_whatsapp_web_media_message",
    description="Send a media message via WhatsApp Web.",
    action_sets=["whatsapp"],
    input_schema={
        "to": {"type": "string", "description": "Recipient phone number.", "example": "1234567890"},
        "media_path": {"type": "string", "description": "Local media path.", "example": "/path/to/img.jpg"},
        "caption": {"type": "string", "description": "Optional caption.", "example": "Caption"},
        "session_id": {"type": "string", "description": "Optional session ID.", "example": "session_1"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_whatsapp_web_media_message(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.send_media_message(
        user_id=input_data.get("user_id", "local"),
        to=input_data["to"],
        media_type="auto",
        media_url=input_data["media_path"],
        caption=input_data.get("caption"),
        phone_number_id=input_data.get("session_id")
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


@action(
    name="get_whatsapp_web_session_status",
    description="Get WhatsApp Web session status.",
    action_sets=["whatsapp"],
    input_schema={
        "session_id": {"type": "string", "description": "Optional session ID.", "example": "session_1"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_whatsapp_web_session_status(input_data: dict) -> dict:
    from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
    result = WhatsAppAppLibrary.get_web_session_status(
        user_id=input_data.get("user_id", "local"),
        session_id=input_data.get("session_id")
    )
    return {"status": result.get("status", "success"), "result": result}
