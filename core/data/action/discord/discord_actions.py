from core.action.action_framework.registry import action


@action(
    name="send_discord_message",
    description="Send a message to a Discord channel.",
    action_sets=["discord"],
    input_schema={
        "channel_id": {"type": "string", "description": "Discord channel ID.", "example": "123456789012345678"},
        "content": {"type": "string", "description": "Message content.", "example": "Hello!"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_discord_message(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    creds = DiscordAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Discord credential. Use /discord login first."}
    cred = creds[0]
    from core.external_libraries.discord.helpers.discord_bot_helpers import send_message
    result = send_message(cred.bot_token, input_data["channel_id"], input_data["content"])
    return {"status": "success", "result": result}


@action(
    name="get_discord_messages",
    description="Get messages from a Discord channel.",
    action_sets=["discord"],
    input_schema={
        "channel_id": {"type": "string", "description": "Discord channel ID.", "example": "123456789012345678"},
        "limit": {"type": "integer", "description": "Max messages to return (1-100).", "example": 50},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_discord_messages(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    creds = DiscordAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Discord credential. Use /discord login first."}
    cred = creds[0]
    from core.external_libraries.discord.helpers.discord_bot_helpers import get_messages
    result = get_messages(cred.bot_token, input_data["channel_id"],
                          limit=input_data.get("limit", 50))
    return {"status": "success", "result": result}


@action(
    name="list_discord_guilds",
    description="List Discord guilds (servers) the bot is in.",
    action_sets=["discord"],
    input_schema={
        "limit": {"type": "integer", "description": "Max guilds to return.", "example": 100},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def list_discord_guilds(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    creds = DiscordAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Discord credential. Use /discord login first."}
    cred = creds[0]
    from core.external_libraries.discord.helpers.discord_bot_helpers import get_bot_guilds
    result = get_bot_guilds(cred.bot_token, limit=input_data.get("limit", 100))
    return {"status": "success", "result": result}


@action(
    name="get_discord_channels",
    description="Get all channels in a Discord guild.",
    action_sets=["discord"],
    input_schema={
        "guild_id": {"type": "string", "description": "Discord guild (server) ID.", "example": "123456789012345678"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_discord_channels(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    creds = DiscordAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Discord credential. Use /discord login first."}
    cred = creds[0]
    from core.external_libraries.discord.helpers.discord_bot_helpers import get_guild_channels
    result = get_guild_channels(cred.bot_token, input_data["guild_id"])
    return {"status": "success", "result": result}


@action(
    name="send_discord_dm",
    description="Send a direct message to a Discord user.",
    action_sets=["discord"],
    input_schema={
        "recipient_id": {"type": "string", "description": "Discord user ID to DM.", "example": "123456789012345678"},
        "content": {"type": "string", "description": "Message content.", "example": "Hey there!"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_discord_dm(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    creds = DiscordAppLibrary.get_credential_store().get(input_data.get("user_id", "local"))
    if not creds:
        return {"status": "error", "message": "No Discord credential. Use /discord login first."}
    cred = creds[0]
    from core.external_libraries.discord.helpers.discord_bot_helpers import send_dm
    result = send_dm(cred.bot_token, input_data["recipient_id"], input_data["content"])
    return {"status": "success", "result": result}


@action(
    name="list_discord_guild_members",
    description="List guild members.",
    action_sets=["discord"],
    input_schema={
        "guild_id": {"type": "string", "description": "Guild ID.", "example": "123456789012345678"},
        "limit": {"type": "integer", "description": "Limit.", "example": 100},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def list_discord_guild_members(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.get_guild_members(
        user_id=input_data.get("user_id", "local"),
        guild_id=input_data["guild_id"],
        limit=input_data.get("limit", 100)
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="add_discord_reaction",
    description="Add reaction.",
    action_sets=["discord"],
    input_schema={
        "channel_id": {"type": "string", "description": "Channel ID.", "example": "123"},
        "message_id": {"type": "string", "description": "Message ID.", "example": "456"},
        "emoji": {"type": "string", "description": "Emoji.", "example": "👍"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def add_discord_reaction(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.add_reaction(
        user_id=input_data.get("user_id", "local"),
        channel_id=input_data["channel_id"],
        message_id=input_data["message_id"],
        emoji=input_data["emoji"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="send_discord_user_message",
    description="Send user message (self-bot).",
    action_sets=["discord"],
    input_schema={
        "channel_id": {"type": "string", "description": "Channel ID.", "example": "123"},
        "content": {"type": "string", "description": "Content.", "example": "Hi"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_discord_user_message(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.send_message_user(
        user_id=input_data.get("user_id", "local"),
        channel_id=input_data["channel_id"],
        content=input_data["content"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_discord_user_guilds",
    description="Get user guilds.",
    action_sets=["discord"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_discord_user_guilds(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.get_user_guilds(
        user_id=input_data.get("user_id", "local")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_discord_user_dm_channels",
    description="Get user DMs.",
    action_sets=["discord"],
    input_schema={},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_discord_user_dm_channels(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.get_dm_channels(
        user_id=input_data.get("user_id", "local")
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="send_discord_user_dm",
    description="Send user DM.",
    action_sets=["discord"],
    input_schema={
        "recipient_id": {"type": "string", "description": "Recipient ID.", "example": "123"},
        "content": {"type": "string", "description": "Content.", "example": "Hi"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def send_discord_user_dm(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.send_dm_user(
        user_id=input_data.get("user_id", "local"),
        recipient_id=input_data["recipient_id"],
        content=input_data["content"]
    )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="join_discord_voice_channel",
    description="Join voice channel.",
    action_sets=["discord"],
    input_schema={
        "guild_id": {"type": "string", "description": "Guild ID.", "example": "123"},
        "channel_id": {"type": "string", "description": "Channel ID.", "example": "456"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def join_discord_voice_channel(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                DiscordAppLibrary.join_voice_channel(
                    user_id=input_data.get("user_id", "local"),
                    guild_id=input_data["guild_id"],
                    channel_id=input_data["channel_id"]
                )
            )
            result = future.result()
    else:
        result = loop.run_until_complete(
            DiscordAppLibrary.join_voice_channel(
                user_id=input_data.get("user_id", "local"),
                guild_id=input_data["guild_id"],
                channel_id=input_data["channel_id"]
            )
        )
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="leave_discord_voice_channel",
    description="Leave voice channel.",
    action_sets=["discord"],
    input_schema={"guild_id": {"type": "string", "description": "Guild ID.", "example": "123"}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def leave_discord_voice_channel(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    import asyncio
    try:
        result = asyncio.run(DiscordAppLibrary.leave_voice_channel(
            user_id=input_data.get("user_id", "local"),
            guild_id=input_data["guild_id"]
        ))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                DiscordAppLibrary.leave_voice_channel(
                    user_id=input_data.get("user_id", "local"),
                    guild_id=input_data["guild_id"]
                )
            )
            result = future.result()
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="speak_discord_voice_tts",
    description="Speak TTS in voice.",
    action_sets=["discord"],
    input_schema={
        "guild_id": {"type": "string", "description": "Guild ID.", "example": "123"},
        "text": {"type": "string", "description": "Text.", "example": "Hello"},
    },
    output_schema={"status": {"type": "string", "example": "success"}},
)
def speak_discord_voice_tts(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    import asyncio
    try:
        result = asyncio.run(DiscordAppLibrary.speak_in_voice(
            user_id=input_data.get("user_id", "local"),
            guild_id=input_data["guild_id"],
            text=input_data["text"]
        ))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                DiscordAppLibrary.speak_in_voice(
                    user_id=input_data.get("user_id", "local"),
                    guild_id=input_data["guild_id"],
                    text=input_data["text"]
                )
            )
            result = future.result()
    return {"status": result.get("status", "success"), "result": result}


@action(
    name="get_discord_voice_status",
    description="Get voice status.",
    action_sets=["discord"],
    input_schema={"guild_id": {"type": "string", "description": "Guild ID.", "example": "123"}},
    output_schema={"status": {"type": "string", "example": "success"}},
)
def get_discord_voice_status(input_data: dict) -> dict:
    from core.external_libraries.discord.external_app_library import DiscordAppLibrary
    result = DiscordAppLibrary.get_voice_status(
        user_id=input_data.get("user_id", "local"),
        guild_id=input_data["guild_id"]
    )
    return {"status": result.get("status", "success"), "result": result}
