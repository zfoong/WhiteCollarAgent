from core.action.action_framework.registry import action


@action(
    name="create_recall_bot",
    description="Create a Recall.ai bot to join a meeting and record/transcribe.",
    action_sets=["recall"],
    input_schema={
        "meeting_url": {"type": "string", "description": "Meeting URL (Zoom, Google Meet, Teams).", "example": "https://meet.google.com/abc-defg-hij"},
        "bot_name": {"type": "string", "description": "Display name for the bot.", "example": "Meeting Assistant"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def create_recall_bot(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    creds = RecallAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Recall credential. Use /recall login first."}
    cred = creds[0]
    from core.external_libraries.recall.helpers.recall_helpers import create_bot
    result = create_bot(cred.api_key, input_data["meeting_url"],
                        bot_name=input_data.get("bot_name", "Meeting Assistant"),
                        region=cred.region)
    return {"status": "success", "result": result}


@action(
    name="get_recall_bot",
    description="Get status and details of a Recall.ai bot.",
    action_sets=["recall"],
    input_schema={
        "bot_id": {"type": "string", "description": "Recall bot ID.", "example": "abc-123"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_recall_bot(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    creds = RecallAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Recall credential. Use /recall login first."}
    cred = creds[0]
    from core.external_libraries.recall.helpers.recall_helpers import get_bot
    result = get_bot(cred.api_key, input_data["bot_id"], region=cred.region)
    return {"status": "success", "result": result}


@action(
    name="get_recall_transcript",
    description="Get the meeting transcript from a Recall.ai bot.",
    action_sets=["recall"],
    input_schema={
        "bot_id": {"type": "string", "description": "Recall bot ID.", "example": "abc-123"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_recall_transcript(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    creds = RecallAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Recall credential. Use /recall login first."}
    cred = creds[0]
    from core.external_libraries.recall.helpers.recall_helpers import get_transcript
    result = get_transcript(cred.api_key, input_data["bot_id"], region=cred.region)
    return {"status": "success", "result": result}


@action(
    name="recall_leave_meeting",
    description="Make a Recall.ai bot leave the meeting.",
    action_sets=["recall"],
    input_schema={
        "bot_id": {"type": "string", "description": "Recall bot ID.", "example": "abc-123"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def recall_leave_meeting(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    creds = RecallAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Recall credential. Use /recall login first."}
    cred = creds[0]
    from core.external_libraries.recall.helpers.recall_helpers import leave_meeting
    result = leave_meeting(cred.api_key, input_data["bot_id"], region=cred.region)
    return {"status": "success", "result": result}


@action(
    name="list_meeting_bots",
    description="List bots.",
    action_sets=["recall"],
    input_schema={"page_size": {"type": "integer", "description": "Page size.", "example": 50}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def list_meeting_bots(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    result = RecallAppLibrary.list_bots(
        user_id=input_data.get("user_id", "local"),
        page_size=input_data.get("page_size", 50)
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="delete_meeting_bot",
    description="Delete bot.",
    action_sets=["recall"],
    input_schema={"bot_id": {"type": "string", "description": "Bot ID.", "example": "abc"}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def delete_meeting_bot(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    result = RecallAppLibrary.delete_bot(
        user_id=input_data.get("user_id", "local"),
        bot_id=input_data["bot_id"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_meeting_recording",
    description="Get recording.",
    action_sets=["recall"],
    input_schema={"bot_id": {"type": "string", "description": "Bot ID.", "example": "abc"}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_meeting_recording(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    result = RecallAppLibrary.get_recording(
        user_id=input_data.get("user_id", "local"),
        bot_id=input_data["bot_id"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="send_meeting_chat_message",
    description="Send chat.",
    action_sets=["recall"],
    input_schema={
        "bot_id": {"type": "string", "description": "Bot ID.", "example": "abc"},
        "message": {"type": "string", "description": "Message.", "example": "Hi"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_meeting_chat_message(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    result = RecallAppLibrary.send_chat_message(
        user_id=input_data.get("user_id", "local"),
        bot_id=input_data["bot_id"],
        message=input_data["message"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="speak_in_meeting",
    description="Speak in meeting (audio).",
    action_sets=["recall"],
    input_schema={
        "bot_id": {"type": "string", "description": "Bot ID.", "example": "abc"},
        "audio_data": {"type": "string", "description": "Base64 audio.", "example": "UklGR..."},
        "audio_format": {"type": "string", "description": "Format.", "example": "wav"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def speak_in_meeting(input_data: dict) -> dict:
    from core.external_libraries.recall.external_app_library import RecallAppLibrary
    result = RecallAppLibrary.speak_in_meeting(
        user_id=input_data.get("user_id", "local"),
        bot_id=input_data["bot_id"],
        audio_data=input_data["audio_data"],
        audio_format=input_data.get("audio_format", "wav")
    )
    return {"status": result.get("status", "success"), "result": result}
