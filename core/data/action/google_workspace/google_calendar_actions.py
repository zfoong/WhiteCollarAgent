from core.action.action_framework.registry import action


@action(
    name="create_google_meet",
    description="Create a Google Calendar event with a Google Meet link.",
    action_sets=["google_workspace"],
    input_schema={
        "event_data": {"type": "object", "description": "Calendar event data with summary, start, end, conferenceData.", "example": {}},
        "calendar_id": {"type": "string", "description": "Calendar ID (default: primary).", "example": "primary"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def create_google_meet(input_data: dict) -> dict:
    from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
    creds = GoogleWorkspaceAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Google credential. Use /google login first."}
    cred = creds[0]
    from core.external_libraries.google_workspace.helpers.google_helpers import create_google_meet_event
    result = create_google_meet_event(cred.token,
                                      calendar_id=input_data.get("calendar_id", "primary"),
                                      event_data=input_data.get("event_data"))
    return {"status": "success", "result": result}


@action(
    name="check_calendar_availability",
    description="Check Google Calendar free/busy availability.",
    action_sets=["google_workspace"],
    input_schema={
        "time_min": {"type": "string", "description": "Start time in ISO 8601 format.", "example": "2024-01-15T09:00:00Z"},
        "time_max": {"type": "string", "description": "End time in ISO 8601 format.", "example": "2024-01-15T17:00:00Z"},
        "calendar_id": {"type": "string", "description": "Calendar ID (default: primary).", "example": "primary"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def check_calendar_availability(input_data: dict) -> dict:
    from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
    creds = GoogleWorkspaceAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Google credential. Use /google login first."}
    cred = creds[0]
    from core.external_libraries.google_workspace.helpers.google_helpers import check_google_calendar_availability
    result = check_google_calendar_availability(cred.token,
                                                calendar_id=input_data.get("calendar_id", "primary"),
                                                time_min=input_data.get("time_min"),
                                                time_max=input_data.get("time_max"))
    return {"status": "success", "result": result}


@action(
    name="check_availability_and_schedule",
    description="Schedule meeting if free.",
    action_sets=["google_workspace"],
    input_schema={
        "start_time": {"type": "string", "description": "Start time.", "example": "2024-01-01T10:00:00"},
        "end_time": {"type": "string", "description": "End time.", "example": "2024-01-01T11:00:00"},
        "summary": {"type": "string", "description": "Summary.", "example": "Meeting"},
        "description": {"type": "string", "description": "Description.", "example": "Details"},
        "attendees": {"type": "array", "description": "Attendees.", "example": ["a@b.com"]},
        "from_email": {"type": "string", "description": "Sender.", "example": "me@example.com"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def check_availability_and_schedule(input_data: dict) -> dict:
    from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
    from datetime import datetime
    result = GoogleWorkspaceAppLibrary.schedule_if_free(
        user_id=input_data.get("user_id", "local"),
        start_time=datetime.fromisoformat(input_data["start_time"]),
        end_time=datetime.fromisoformat(input_data["end_time"]),
        summary=input_data["summary"],
        description=input_data.get("description", ""),
        attendees=input_data.get("attendees"),
        from_email=input_data.get("from_email")
    )
    return result
