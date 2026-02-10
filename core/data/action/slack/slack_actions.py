from core.action.action_framework.registry import action


@action(
    name="send_slack_message",
    description="Send a message to a Slack channel or DM.",
    action_sets=["slack"],
    input_schema={
        "channel": {"type": "string", "description": "Channel ID or name.", "example": "C01234567"},
        "text": {"type": "string", "description": "Message text.", "example": "Hello team!"},
        "thread_ts": {"type": "string", "description": "Optional thread timestamp for replies.", "example": ""},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_slack_message(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    creds = SlackAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Slack credential. Use /slack login first."}
    cred = creds[0]
    from core.external_libraries.slack.helpers.slack_helpers import send_message
    result = send_message(cred.bot_token, input_data["channel"], input_data["text"],
                          thread_ts=input_data.get("thread_ts"))
    return {"status": "success", "result": result}


@action(
    name="list_slack_channels",
    description="List channels in the Slack workspace.",
    action_sets=["slack"],
    input_schema={
        "limit": {"type": "integer", "description": "Max channels to return.", "example": 100},
    },
    output_schema={"status": {"type": "string", "example": "success"}, "channels": {"type": "array"}},
)
def list_slack_channels(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    creds = SlackAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Slack credential. Use /slack login first."}
    cred = creds[0]
    from core.external_libraries.slack.helpers.slack_helpers import list_channels
    result = list_channels(cred.bot_token, limit=input_data.get("limit", 100))
    return {"status": "success", "result": result}


@action(
    name="get_slack_channel_history",
    description="Get message history from a Slack channel.",
    action_sets=["slack"],
    input_schema={
        "channel": {"type": "string", "description": "Channel ID.", "example": "C01234567"},
        "limit": {"type": "integer", "description": "Max messages.", "example": 50},
    },
    output_schema={"status": {"type": "string", "example": "success"}, "messages": {"type": "array"}},
)
def get_slack_channel_history(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    creds = SlackAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Slack credential. Use /slack login first."}
    cred = creds[0]
    from core.external_libraries.slack.helpers.slack_helpers import get_channel_history
    result = get_channel_history(cred.bot_token, input_data["channel"], limit=input_data.get("limit", 50))
    return {"status": "success", "result": result}


@action(
    name="list_slack_users",
    description="List users in the Slack workspace.",
    action_sets=["slack"],
    input_schema={
        "limit": {"type": "integer", "description": "Max users to return.", "example": 100},
    },
    output_schema={"status": {"type": "string", "example": "success"}, "users": {"type": "array"}},
)
def list_slack_users(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    creds = SlackAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Slack credential. Use /slack login first."}
    cred = creds[0]
    from core.external_libraries.slack.helpers.slack_helpers import list_users
    result = list_users(cred.bot_token, limit=input_data.get("limit", 100))
    return {"status": "success", "result": result}


@action(
    name="search_slack_messages",
    description="Search for messages in the Slack workspace.",
    action_sets=["slack"],
    input_schema={
        "query": {"type": "string", "description": "Search query.", "example": "project update"},
        "count": {"type": "integer", "description": "Max results.", "example": 20},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def search_slack_messages(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    creds = SlackAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Slack credential. Use /slack login first."}
    cred = creds[0]
    from core.external_libraries.slack.helpers.slack_helpers import search_messages
    result = search_messages(cred.bot_token, input_data["query"], count=input_data.get("count", 20))
    return {"status": "success", "result": result}


@action(
    name="upload_slack_file",
    description="Upload a file to a Slack channel.",
    action_sets=["slack"],
    input_schema={
        "channels": {"type": "string", "description": "Channel ID to upload to.", "example": "C01234567"},
        "file_path": {"type": "string", "description": "Local file path to upload.", "example": "/path/to/file.txt"},
        "title": {"type": "string", "description": "File title.", "example": "Report"},
        "initial_comment": {"type": "string", "description": "Message with the file.", "example": "Here's the report"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def upload_slack_file(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    creds = SlackAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Slack credential. Use /slack login first."}
    cred = creds[0]
    from core.external_libraries.slack.helpers.slack_helpers import upload_file
    result = upload_file(cred.bot_token, input_data["channels"], file_path=input_data.get("file_path"),
                         title=input_data.get("title"), initial_comment=input_data.get("initial_comment"))
    return {"status": "success", "result": result}


@action(
    name="get_slack_user_info",
    description="Get info about a Slack user.",
    action_sets=["slack"],
    input_schema={
        "slack_user_id": {"type": "string", "description": "User ID.", "example": "U1234567"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_slack_user_info(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    result = SlackAppLibrary.get_user_info(
        user_id=input_data.get("user_id", "local"),
        slack_user_id=input_data["slack_user_id"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_slack_channel_info",
    description="Get info about a Slack channel.",
    action_sets=["slack"],
    input_schema={
        "channel": {"type": "string", "description": "Channel ID.", "example": "C1234567"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_slack_channel_info(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    result = SlackAppLibrary.get_channel_info(
        user_id=input_data.get("user_id", "local"),
        channel=input_data["channel"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="create_slack_channel",
    description="Create a new Slack channel.",
    action_sets=["slack"],
    input_schema={
        "name": {"type": "string", "description": "Channel name.", "example": "project-alpha"},
        "is_private": {"type": "boolean", "description": "Is private?", "example": False},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def create_slack_channel(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    result = SlackAppLibrary.create_channel(
        user_id=input_data.get("user_id", "local"),
        name=input_data["name"],
        is_private=input_data.get("is_private", False)
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="invite_to_slack_channel",
    description="Invite users to a Slack channel.",
    action_sets=["slack"],
    input_schema={
        "channel": {"type": "string", "description": "Channel ID.", "example": "C1234567"},
        "users": {"type": "array", "description": "List of user IDs.", "example": ["U123"]},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def invite_to_slack_channel(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    result = SlackAppLibrary.invite_to_channel(
        user_id=input_data.get("user_id", "local"),
        channel=input_data["channel"],
        users=input_data["users"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="open_slack_dm",
    description="Open a DM with Slack users.",
    action_sets=["slack"],
    input_schema={
        "users": {"type": "array", "description": "List of user IDs.", "example": ["U123"]},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def open_slack_dm(input_data: dict) -> dict:
    from core.external_libraries.slack.external_app_library import SlackAppLibrary
    result = SlackAppLibrary.open_dm(
        user_id=input_data.get("user_id", "local"),
        users=input_data["users"]
    )
    return {"status": result.get("status", "success"), "result": result}
