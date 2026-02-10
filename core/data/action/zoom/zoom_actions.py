from core.action.action_framework.registry import action


@action(
    name="create_zoom_meeting",
    description="Create a new Zoom meeting.",
    action_sets=["zoom"],
    input_schema={
        "topic": {"type": "string", "description": "Meeting topic.", "example": "Weekly Standup"},
        "start_time": {"type": "string", "description": "Start time in ISO 8601 format.", "example": "2024-01-15T10:00:00Z"},
        "duration": {"type": "integer", "description": "Duration in minutes.", "example": 60},
        "timezone": {"type": "string", "description": "Timezone.", "example": "UTC"},
        "agenda": {"type": "string", "description": "Meeting agenda.", "example": "Discuss project updates"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def create_zoom_meeting(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    creds = ZoomAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Zoom credential. Use /zoom login first."}
    cred = creds[0]
    from core.external_libraries.zoom.helpers.zoom_helpers import create_meeting
    result = create_meeting(cred.access_token, input_data["topic"],
                            start_time=input_data.get("start_time"),
                            duration=input_data.get("duration", 60),
                            timezone=input_data.get("timezone", "UTC"),
                            agenda=input_data.get("agenda", ""))
    return {"status": "success", "result": result}


@action(
    name="list_zoom_meetings",
    description="List scheduled Zoom meetings.",
    action_sets=["zoom"],
    input_schema={
        "meeting_type": {"type": "string", "description": "Type: scheduled, live, upcoming.", "example": "scheduled"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def list_zoom_meetings(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    creds = ZoomAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Zoom credential. Use /zoom login first."}
    cred = creds[0]
    from core.external_libraries.zoom.helpers.zoom_helpers import list_meetings
    result = list_meetings(cred.access_token,
                           meeting_type=input_data.get("meeting_type", "scheduled"))
    return {"status": "success", "result": result}


@action(
    name="get_zoom_meeting",
    description="Get details of a specific Zoom meeting.",
    action_sets=["zoom"],
    input_schema={
        "meeting_id": {"type": "string", "description": "Zoom meeting ID.", "example": "12345678901"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_zoom_meeting(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    creds = ZoomAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Zoom credential. Use /zoom login first."}
    cred = creds[0]
    from core.external_libraries.zoom.helpers.zoom_helpers import get_meeting
    result = get_meeting(cred.access_token, input_data["meeting_id"])
    return {"status": "success", "result": result}


@action(
    name="delete_zoom_meeting",
    description="Delete a Zoom meeting.",
    action_sets=["zoom"],
    input_schema={
        "meeting_id": {"type": "string", "description": "Zoom meeting ID to delete.", "example": "12345678901"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def delete_zoom_meeting(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    creds = ZoomAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Zoom credential. Use /zoom login first."}
    cred = creds[0]
    from core.external_libraries.zoom.helpers.zoom_helpers import delete_meeting
    result = delete_meeting(cred.access_token, input_data["meeting_id"])
    return {"status": "success", "result": result}


@action(
    name="get_zoom_profile",
    description="Get Zoom profile.",
    action_sets=["zoom"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_zoom_profile(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    result = ZoomAppLibrary.get_my_profile(
        user_id=input_data.get("user_id", "local")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_upcoming_zoom_meetings",
    description="Get upcoming meetings.",
    action_sets=["zoom"],
    input_schema={"page_size": {"type": "integer", "description": "Page size.", "example": 30}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_upcoming_zoom_meetings(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    result = ZoomAppLibrary.get_upcoming_meetings(
        user_id=input_data.get("user_id", "local"),
        page_size=input_data.get("page_size", 30)
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_live_zoom_meetings",
    description="Get live meetings.",
    action_sets=["zoom"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_live_zoom_meetings(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    result = ZoomAppLibrary.get_live_meetings(
        user_id=input_data.get("user_id", "local")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="update_zoom_meeting",
    description="Update a meeting.",
    action_sets=["zoom"],
    input_schema={
        "meeting_id": {"type": "string", "description": "Meeting ID.", "example": "123"},
        "topic": {"type": "string", "description": "Topic.", "example": "New Topic"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def update_zoom_meeting(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    result = ZoomAppLibrary.update_meeting(
        user_id=input_data.get("user_id", "local"),
        meeting_id=input_data["meeting_id"],
        topic=input_data.get("topic"),
        start_time=input_data.get("start_time"),
        duration=input_data.get("duration"),
        timezone=input_data.get("timezone"),
        agenda=input_data.get("agenda"),
        password=input_data.get("password"),
        settings=input_data.get("settings")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_zoom_meeting_invitation",
    description="Get invitation.",
    action_sets=["zoom"],
    input_schema={"meeting_id": {"type": "string", "description": "Meeting ID.", "example": "123"}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_zoom_meeting_invitation(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    result = ZoomAppLibrary.get_meeting_invitation(
        user_id=input_data.get("user_id", "local"),
        meeting_id=input_data["meeting_id"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="list_zoom_users",
    description="List users.",
    action_sets=["zoom"],
    input_schema={"page_size": {"type": "integer", "description": "Page size.", "example": 30}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def list_zoom_users(input_data: dict) -> dict:
    from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
    result = ZoomAppLibrary.list_users(
        user_id=input_data.get("user_id", "local"),
        page_size=input_data.get("page_size", 30)
    )
    return {"status": result.get("status", "success"), "result": result}
