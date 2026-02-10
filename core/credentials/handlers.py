"""All integration credential handlers + registry."""
from __future__ import annotations

import secrets
import time
import webbrowser
from abc import ABC, abstractmethod
from typing import Tuple
from urllib.parse import urlencode

LOCAL_USER_ID = "local"
REDIRECT_URI = "http://localhost:8765"


class IntegrationHandler(ABC):
    @abstractmethod
    async def login(self, args: list[str]) -> Tuple[bool, str]: ...
    @abstractmethod
    async def logout(self, args: list[str]) -> Tuple[bool, str]: ...
    @abstractmethod
    async def status(self) -> Tuple[bool, str]: ...

    async def invite(self, args: list[str]) -> Tuple[bool, str]:
        return False, "Invite not available for this integration. Use 'login' instead."

    @property
    def subcommands(self) -> list[str]:
        return ["login", "logout", "status"]

    async def handle(self, sub: str, args: list[str]) -> Tuple[bool, str]:
        """Route subcommand. Override in subclasses for extra subcommands."""
        if sub == "invite":    return await self.invite(args)
        if sub == "login":     return await self.login(args)
        if sub == "logout":    return await self.logout(args)
        if sub == "status":    return await self.status()
        return False, f"Unknown subcommand: {sub}. Use: {', '.join(self.subcommands)}"


# ═══════════════════════════════════════════════════════════════════
# Google
# ═══════════════════════════════════════════════════════════════════

class GoogleHandler(IntegrationHandler):
    SCOPES = "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/contacts.readonly https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"

    async def login(self, args):
        from core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            return False, "Not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars."

        params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": self.SCOPES, "access_type": "offline", "prompt": "consent", "state": secrets.token_urlsafe(32)}
        from core.credentials.oauth_server import run_oauth_flow
        code, error = run_oauth_flow(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")
        if error: return False, f"Google OAuth failed: {error}"

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"}) as r:
                if r.status != 200: return False, f"Token exchange failed: {await r.text()}"
                tokens = await r.json()
            async with s.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"}) as r:
                if r.status != 200: return False, "Failed to fetch user info."
                info = await r.json()

        from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
        from core.external_libraries.google_workspace.credentials import GoogleWorkspaceCredential
        GoogleWorkspaceAppLibrary.initialize()
        GoogleWorkspaceAppLibrary.get_credential_store().add(GoogleWorkspaceCredential(
            user_id=LOCAL_USER_ID, email=info.get("email", ""), token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""), token_expiry=time.time() + tokens.get("expires_in", 3600)))
        return True, f"Google connected as {info.get('email')}"

    async def logout(self, args):
        from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
        GoogleWorkspaceAppLibrary.initialize()
        store = GoogleWorkspaceAppLibrary.get_credential_store()
        creds = store.get(LOCAL_USER_ID)
        if not creds: return False, "No Google credentials found."
        email = args[0] if args else creds[0].email
        store.remove(LOCAL_USER_ID, email=email)
        return True, f"Removed Google credential for {email}."

    async def status(self):
        from core.external_libraries.google_workspace.external_app_library import GoogleWorkspaceAppLibrary
        GoogleWorkspaceAppLibrary.initialize()
        creds = GoogleWorkspaceAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not creds: return True, "Google: Not connected"
        return True, "Google: Connected\n" + "\n".join(f"  - {c.email}" for c in creds)


# ═══════════════════════════════════════════════════════════════════
# Slack
# ═══════════════════════════════════════════════════════════════════

class SlackHandler(IntegrationHandler):
    @property
    def subcommands(self) -> list[str]:
        return ["invite", "login", "logout", "status"]

    async def invite(self, args):
        from core.config import SLACK_SHARED_CLIENT_ID, SLACK_SHARED_CLIENT_SECRET
        if not SLACK_SHARED_CLIENT_ID or not SLACK_SHARED_CLIENT_SECRET:
            return False, "CraftOS Slack app not configured. Set SLACK_SHARED_CLIENT_ID and SLACK_SHARED_CLIENT_SECRET env vars.\nAlternatively, use /slack login <bot_token> with your own Slack app."

        scopes = "chat:write,channels:read,channels:history,groups:read,groups:history,users:read,search:read,files:write,im:read,im:write,im:history"
        params = {"client_id": SLACK_SHARED_CLIENT_ID, "scope": scopes, "redirect_uri": REDIRECT_URI, "state": secrets.token_urlsafe(32)}
        from core.credentials.oauth_server import run_oauth_flow
        code, error = run_oauth_flow(f"https://slack.com/oauth/v2/authorize?{urlencode(params)}")
        if error: return False, f"Slack OAuth failed: {error}"

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post("https://slack.com/api/oauth.v2.access", data={"code": code, "client_id": SLACK_SHARED_CLIENT_ID, "client_secret": SLACK_SHARED_CLIENT_SECRET, "redirect_uri": REDIRECT_URI}) as r:
                data = await r.json()
                if not data.get("ok"): return False, f"Slack OAuth token exchange failed: {data.get('error')}"

        bot_token = data.get("access_token", "")
        team_id = data.get("team", {}).get("id", "")
        team_name = data.get("team", {}).get("name", team_id)

        from core.external_libraries.slack.external_app_library import SlackAppLibrary
        from core.external_libraries.slack.credentials import SlackCredential
        SlackAppLibrary.initialize()
        SlackAppLibrary.get_credential_store().add(SlackCredential(user_id=LOCAL_USER_ID, workspace_id=team_id, workspace_name=team_name, bot_token=bot_token, team_id=team_id))
        return True, f"Slack connected via CraftOS app: {team_name} ({team_id})"

    async def login(self, args):
        if not args: return False, "Usage: /slack login <bot_token> [workspace_name]"
        bot_token = args[0]
        if not bot_token.startswith(("xoxb-", "xoxp-")): return False, "Invalid token. Expected xoxb-... or xoxp-..."

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post("https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {bot_token}"}) as r:
                data = await r.json()
                if not data.get("ok"): return False, f"Slack auth failed: {data.get('error')}"
                team_id = data.get("team_id", "")
                workspace_name = args[1] if len(args) > 1 else data.get("team", team_id)

        from core.external_libraries.slack.external_app_library import SlackAppLibrary
        from core.external_libraries.slack.credentials import SlackCredential
        SlackAppLibrary.initialize()
        SlackAppLibrary.get_credential_store().add(SlackCredential(user_id=LOCAL_USER_ID, workspace_id=team_id, workspace_name=workspace_name, bot_token=bot_token, team_id=team_id))
        return True, f"Slack connected: {workspace_name} ({team_id})"

    async def logout(self, args):
        from core.external_libraries.slack.external_app_library import SlackAppLibrary
        SlackAppLibrary.initialize()
        store = SlackAppLibrary.get_credential_store()
        creds = store.get(LOCAL_USER_ID)
        if not creds: return False, "No Slack credentials found."
        wid = args[0] if args else creds[0].workspace_id
        store.remove(LOCAL_USER_ID, workspace_id=wid)
        return True, f"Removed Slack credential for {wid}."

    async def status(self):
        from core.external_libraries.slack.external_app_library import SlackAppLibrary
        SlackAppLibrary.initialize()
        creds = SlackAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not creds: return True, "Slack: Not connected"
        return True, "Slack: Connected\n" + "\n".join(f"  - {c.workspace_name} ({c.workspace_id})" for c in creds)


# ═══════════════════════════════════════════════════════════════════
# Notion
# ═══════════════════════════════════════════════════════════════════

class NotionHandler(IntegrationHandler):
    @property
    def subcommands(self) -> list[str]:
        return ["invite", "login", "logout", "status"]

    async def invite(self, args):
        from core.config import NOTION_SHARED_CLIENT_ID, NOTION_SHARED_CLIENT_SECRET
        if not NOTION_SHARED_CLIENT_ID or not NOTION_SHARED_CLIENT_SECRET:
            return False, "CraftOS Notion integration not configured. Set NOTION_SHARED_CLIENT_ID and NOTION_SHARED_CLIENT_SECRET env vars.\nAlternatively, use /notion login <token> with your own integration token."

        params = {"client_id": NOTION_SHARED_CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "owner": "user", "state": secrets.token_urlsafe(32)}
        from core.credentials.oauth_server import run_oauth_flow
        code, error = run_oauth_flow(f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}")
        if error: return False, f"Notion OAuth failed: {error}"

        import aiohttp, base64
        basic = base64.b64encode(f"{NOTION_SHARED_CLIENT_ID}:{NOTION_SHARED_CLIENT_SECRET}".encode()).decode()
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.notion.com/v1/oauth/token",
                              json={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
                              headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"}) as r:
                if r.status != 200: return False, f"Notion token exchange failed: {await r.text()}"
                data = await r.json()

        token = data.get("access_token", "")
        ws_name = data.get("workspace_name", "default")
        ws_id = data.get("workspace_id", ws_name)

        from core.external_libraries.notion.external_app_library import NotionAppLibrary
        from core.external_libraries.notion.credentials import NotionCredential
        NotionAppLibrary.initialize()
        NotionAppLibrary.get_credential_store().add(NotionCredential(user_id=LOCAL_USER_ID, workspace_id=ws_id, workspace_name=ws_name, token=token))
        return True, f"Notion connected via CraftOS integration: {ws_name}"

    async def login(self, args):
        if not args: return False, "Usage: /notion login <integration_token>"
        token = args[0]

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.notion.com/v1/users/me", headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"}) as r:
                if r.status != 200: return False, f"Notion auth failed: {r.status}"
                data = await r.json()

        ws_name = data.get("bot", {}).get("workspace_name", "default")
        from core.external_libraries.notion.external_app_library import NotionAppLibrary
        from core.external_libraries.notion.credentials import NotionCredential
        NotionAppLibrary.initialize()
        NotionAppLibrary.get_credential_store().add(NotionCredential(user_id=LOCAL_USER_ID, workspace_id=ws_name, workspace_name=ws_name, token=token))
        return True, f"Notion connected: {ws_name}"

    async def logout(self, args):
        from core.external_libraries.notion.external_app_library import NotionAppLibrary
        NotionAppLibrary.initialize()
        store = NotionAppLibrary.get_credential_store()
        creds = store.get(LOCAL_USER_ID)
        if not creds: return False, "No Notion credentials found."
        wid = args[0] if args else creds[0].workspace_id
        store.remove(LOCAL_USER_ID, workspace_id=wid)
        return True, f"Removed Notion credential for {wid}."

    async def status(self):
        from core.external_libraries.notion.external_app_library import NotionAppLibrary
        NotionAppLibrary.initialize()
        creds = NotionAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not creds: return True, "Notion: Not connected"
        return True, "Notion: Connected\n" + "\n".join(f"  - {c.workspace_name}" for c in creds)


# ═══════════════════════════════════════════════════════════════════
# LinkedIn
# ═══════════════════════════════════════════════════════════════════

class LinkedInHandler(IntegrationHandler):
    async def login(self, args):
        from core.config import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET
        if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
            return False, "Not configured. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET env vars."

        params = {"response_type": "code", "client_id": LINKEDIN_CLIENT_ID, "redirect_uri": REDIRECT_URI, "scope": "openid profile email w_member_social", "state": secrets.token_urlsafe(32)}
        from core.credentials.oauth_server import run_oauth_flow
        code, error = run_oauth_flow(f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}")
        if error: return False, f"LinkedIn OAuth failed: {error}"

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post("https://www.linkedin.com/oauth/v2/accessToken", data={"grant_type": "authorization_code", "code": code, "client_id": LINKEDIN_CLIENT_ID, "client_secret": LINKEDIN_CLIENT_SECRET, "redirect_uri": REDIRECT_URI}) as r:
                if r.status != 200: return False, f"Token exchange failed: {await r.text()}"
                tokens = await r.json()
            async with s.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"}) as r:
                if r.status != 200: return False, "Failed to fetch user info."
                info = await r.json()

        from core.external_libraries.linkedin.external_app_library import LinkedInAppLibrary
        from core.external_libraries.linkedin.credentials import LinkedInCredential
        LinkedInAppLibrary.initialize()
        LinkedInAppLibrary.get_credential_store().add(LinkedInCredential(
            user_id=LOCAL_USER_ID, access_token=tokens["access_token"], refresh_token=tokens.get("refresh_token", ""),
            token_expiry=time.time() + tokens.get("expires_in", 3600), linkedin_id=info.get("sub", ""),
            name=info.get("name", ""), email=info.get("email", ""), profile_picture_url=info.get("picture", "")))
        return True, f"LinkedIn connected as {info.get('name')} ({info.get('email')})"

    async def logout(self, args):
        from core.external_libraries.linkedin.external_app_library import LinkedInAppLibrary
        LinkedInAppLibrary.initialize()
        store = LinkedInAppLibrary.get_credential_store()
        creds = store.get(LOCAL_USER_ID)
        if not creds: return False, "No LinkedIn credentials found."
        lid = args[0] if args else creds[0].linkedin_id
        store.remove(LOCAL_USER_ID, linkedin_id=lid)
        return True, f"Removed LinkedIn credential for {lid}."

    async def status(self):
        from core.external_libraries.linkedin.external_app_library import LinkedInAppLibrary
        LinkedInAppLibrary.initialize()
        creds = LinkedInAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not creds: return True, "LinkedIn: Not connected"
        return True, "LinkedIn: Connected\n" + "\n".join(f"  - {c.name} ({c.email})" for c in creds)


# ═══════════════════════════════════════════════════════════════════
# Zoom
# ═══════════════════════════════════════════════════════════════════

class ZoomHandler(IntegrationHandler):
    async def login(self, args):
        from core.config import ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
        if not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET:
            return False, "Not configured. Set ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET env vars."

        import base64
        params = {"response_type": "code", "client_id": ZOOM_CLIENT_ID, "redirect_uri": REDIRECT_URI, "state": secrets.token_urlsafe(32)}
        from core.credentials.oauth_server import run_oauth_flow
        code, error = run_oauth_flow(f"https://zoom.us/oauth/authorize?{urlencode(params)}")
        if error: return False, f"Zoom OAuth failed: {error}"

        basic = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post("https://zoom.us/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}, headers={"Authorization": f"Basic {basic}"}) as r:
                if r.status != 200: return False, f"Token exchange failed: {await r.text()}"
                tokens = await r.json()
            async with s.get("https://api.zoom.us/v2/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}) as r:
                if r.status != 200: return False, "Failed to fetch user info."
                info = await r.json()

        from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
        from core.external_libraries.zoom.credentials import ZoomCredential
        ZoomAppLibrary.initialize()
        ZoomAppLibrary.get_credential_store().add(ZoomCredential(
            user_id=LOCAL_USER_ID, access_token=tokens["access_token"], refresh_token=tokens.get("refresh_token", ""),
            token_expiry=time.time() + tokens.get("expires_in", 3600), zoom_user_id=info.get("id", ""),
            email=info.get("email", ""), display_name=info.get("display_name", ""), account_id=info.get("account_id", "")))
        return True, f"Zoom connected as {info.get('display_name')} ({info.get('email')})"

    async def logout(self, args):
        from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
        ZoomAppLibrary.initialize()
        store = ZoomAppLibrary.get_credential_store()
        creds = store.get(LOCAL_USER_ID)
        if not creds: return False, "No Zoom credentials found."
        zid = args[0] if args else creds[0].zoom_user_id
        store.remove(LOCAL_USER_ID, zoom_user_id=zid)
        return True, f"Removed Zoom credential for {zid}."

    async def status(self):
        from core.external_libraries.zoom.external_app_library import ZoomAppLibrary
        ZoomAppLibrary.initialize()
        creds = ZoomAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not creds: return True, "Zoom: Not connected"
        return True, "Zoom: Connected\n" + "\n".join(f"  - {c.display_name} ({c.email})" for c in creds)


# ═══════════════════════════════════════════════════════════════════
# Discord (unified: invite + bot + user)
# ═══════════════════════════════════════════════════════════════════

class DiscordHandler(IntegrationHandler):
    @property
    def subcommands(self) -> list[str]:
        return ["invite", "login", "login-user", "logout", "status"]

    async def handle(self, sub, args):
        if sub == "login-user": return await self._login_user(args)
        return await super().handle(sub, args)

    async def invite(self, args):
        from core.config import DISCORD_SHARED_BOT_ID
        if not DISCORD_SHARED_BOT_ID:
            return False, "CraftOS Discord bot not configured. Set DISCORD_SHARED_BOT_ID env var.\nAlternatively, use /discord login <bot_token> with your own bot."

        permissions = 274878024704  # Send Messages, Read Messages, Embed Links, Attach Files, Read History, Add Reactions
        invite_url = f"https://discord.com/oauth2/authorize?client_id={DISCORD_SHARED_BOT_ID}&permissions={permissions}&scope=bot%20applications.commands"
        webbrowser.open(invite_url)

        if args:
            guild_id = args[0]
            guild_name = args[1] if len(args) > 1 else guild_id
        else:
            return True, (
                f"Bot invite link opened in browser.\n"
                f"After adding the bot to your server, register the guild:\n"
                f"  /discord invite <guild_id> [guild_name]\n\n"
                f"Invite URL: {invite_url}"
            )

        from core.external_libraries.discord.external_app_library import DiscordAppLibrary
        from core.external_libraries.discord.credentials import DiscordSharedBotGuildCredential
        DiscordAppLibrary.initialize()
        DiscordAppLibrary.add_shared_bot_guild(DiscordSharedBotGuildCredential(
            user_id=LOCAL_USER_ID, guild_id=guild_id, guild_name=guild_name, connected_at=str(int(time.time()))))
        return True, f"Discord guild registered with CraftOS bot: {guild_name} ({guild_id})"

    async def login(self, args):
        if not args: return False, "Usage: /discord login <bot_token>"
        bot_token = args[0]

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bot {bot_token}"}) as r:
                if r.status != 200: return False, f"Invalid bot token: {r.status}"
                data = await r.json()

        from core.external_libraries.discord.external_app_library import DiscordAppLibrary
        from core.external_libraries.discord.credentials import DiscordBotCredential
        DiscordAppLibrary.initialize()
        DiscordAppLibrary.add_bot_credential(DiscordBotCredential(
            user_id=LOCAL_USER_ID, bot_token=bot_token, bot_id=data.get("id", ""), bot_username=data.get("username", "")))
        return True, f"Discord bot connected: {data.get('username')} ({data.get('id')})"

    async def _login_user(self, args):
        if not args: return False, "Usage: /discord login-user <user_token>"
        user_token = args[0]

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get("https://discord.com/api/v10/users/@me", headers={"Authorization": user_token}) as r:
                if r.status != 200: return False, f"Invalid user token: {r.status}"
                data = await r.json()

        from core.external_libraries.discord.external_app_library import DiscordAppLibrary
        from core.external_libraries.discord.credentials import DiscordUserCredential
        DiscordAppLibrary.initialize()
        DiscordAppLibrary.add_user_credential(DiscordUserCredential(
            user_id=LOCAL_USER_ID, user_token=user_token, discord_user_id=data.get("id", ""),
            username=data.get("username", ""), discriminator=data.get("discriminator", "")))
        return True, f"Discord user connected: {data.get('username')} ({data.get('id')})"

    async def logout(self, args):
        from core.external_libraries.discord.external_app_library import DiscordAppLibrary
        DiscordAppLibrary.initialize()

        # Try removing from each credential type
        if args:
            target = args[0]
            DiscordAppLibrary.remove_bot_credential(LOCAL_USER_ID, target)
            DiscordAppLibrary.remove_user_credential(LOCAL_USER_ID, target)
            DiscordAppLibrary.remove_shared_bot_guild(LOCAL_USER_ID, target)
            return True, f"Removed Discord credential: {target}"

        # No args — remove first found from any type
        bots = DiscordAppLibrary.get_bot_credentials(LOCAL_USER_ID)
        if bots:
            DiscordAppLibrary.remove_bot_credential(LOCAL_USER_ID, bots[0].bot_id)
            return True, f"Removed Discord bot {bots[0].bot_username} ({bots[0].bot_id})."
        users = DiscordAppLibrary.get_user_credentials(LOCAL_USER_ID)
        if users:
            DiscordAppLibrary.remove_user_credential(LOCAL_USER_ID, users[0].discord_user_id)
            return True, f"Removed Discord user {users[0].username} ({users[0].discord_user_id})."
        guilds = DiscordAppLibrary.get_shared_bot_guilds(LOCAL_USER_ID)
        if guilds:
            DiscordAppLibrary.remove_shared_bot_guild(LOCAL_USER_ID, guilds[0].guild_id)
            return True, f"Removed Discord guild {guilds[0].guild_name} ({guilds[0].guild_id})."
        return False, "No Discord credentials found."

    async def status(self):
        from core.external_libraries.discord.external_app_library import DiscordAppLibrary
        DiscordAppLibrary.initialize()
        lines = []
        bots = DiscordAppLibrary.get_bot_credentials(LOCAL_USER_ID)
        if bots:
            lines.append("  Bots:")
            lines.extend(f"    - {c.bot_username} ({c.bot_id})" for c in bots)
        users = DiscordAppLibrary.get_user_credentials(LOCAL_USER_ID)
        if users:
            lines.append("  Users:")
            lines.extend(f"    - {c.username} ({c.discord_user_id})" for c in users)
        guilds = DiscordAppLibrary.get_shared_bot_guilds(LOCAL_USER_ID)
        if guilds:
            lines.append("  Guilds (CraftOS bot):")
            lines.extend(f"    - {g.guild_name} ({g.guild_id})" for g in guilds)
        if not lines: return True, "Discord: Not connected"
        return True, "Discord: Connected\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Telegram (unified: invite + bot + user)
# ═══════════════════════════════════════════════════════════════════

class TelegramHandler(IntegrationHandler):
    @property
    def subcommands(self) -> list[str]:
        return ["invite", "login", "login-user", "logout", "status"]

    async def handle(self, sub, args):
        if sub == "login-user": return await self._login_user(args)
        return await super().handle(sub, args)

    async def invite(self, args):
        from core.config import TELEGRAM_SHARED_BOT_TOKEN, TELEGRAM_SHARED_BOT_USERNAME
        if not TELEGRAM_SHARED_BOT_TOKEN or not TELEGRAM_SHARED_BOT_USERNAME:
            return False, "CraftOS Telegram bot not configured. Set TELEGRAM_SHARED_BOT_TOKEN and TELEGRAM_SHARED_BOT_USERNAME env vars.\nAlternatively, use /telegram login <bot_token> with your own bot from @BotFather."

        # Validate shared bot token
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.telegram.org/bot{TELEGRAM_SHARED_BOT_TOKEN}/getMe") as r:
                data = await r.json()
                if not data.get("ok"): return False, f"CraftOS Telegram bot token is invalid: {data.get('description')}"
                info = data["result"]

        # Store the shared bot credential locally
        from core.external_libraries.telegram.external_app_library import TelegramAppLibrary
        from core.external_libraries.telegram.credentials import TelegramCredential
        TelegramAppLibrary.initialize()
        TelegramAppLibrary.get_credential_store().add(TelegramCredential(
            user_id=LOCAL_USER_ID, connection_type="bot_api",
            bot_id=str(info.get("id", "")), bot_username=info.get("username", ""),
            bot_token=TELEGRAM_SHARED_BOT_TOKEN))

        bot_link = f"https://t.me/{TELEGRAM_SHARED_BOT_USERNAME}"
        webbrowser.open(bot_link)
        return True, (
            f"CraftOS Telegram bot connected: @{info.get('username')}\n"
            f"Start chatting or add to groups: {bot_link}"
        )

    async def login(self, args):
        if not args: return False, "Usage: /telegram login <bot_token>\nGet from @BotFather on Telegram."
        bot_token = args[0]

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.telegram.org/bot{bot_token}/getMe") as r:
                data = await r.json()
                if not data.get("ok"): return False, f"Invalid bot token: {data.get('description')}"
                info = data["result"]

        from core.external_libraries.telegram.external_app_library import TelegramAppLibrary
        from core.external_libraries.telegram.credentials import TelegramCredential
        TelegramAppLibrary.initialize()
        TelegramAppLibrary.get_credential_store().add(TelegramCredential(
            user_id=LOCAL_USER_ID, connection_type="bot_api",
            bot_id=str(info.get("id", "")), bot_username=info.get("username", ""), bot_token=bot_token))
        return True, f"Telegram bot connected: @{info.get('username')} ({info.get('id')})"

    async def _login_user(self, args):
        if len(args) < 3: return False, "Usage: /telegram login-user <api_id> <api_hash> <session_string> [phone]"
        try: api_id_int = int(args[0])
        except ValueError: return False, "api_id must be a number."

        from core.external_libraries.telegram.external_app_library import TelegramAppLibrary
        from core.external_libraries.telegram.credentials import TelegramCredential
        TelegramAppLibrary.initialize()
        TelegramAppLibrary.get_credential_store().add(TelegramCredential(
            user_id=LOCAL_USER_ID, connection_type="mtproto",
            api_id=api_id_int, api_hash=args[1], session_string=args[2],
            phone_number=args[3] if len(args) > 3 else "unknown"))
        return True, "Telegram user account connected via MTProto."

    async def logout(self, args):
        from core.external_libraries.telegram.external_app_library import TelegramAppLibrary
        TelegramAppLibrary.initialize()
        store = TelegramAppLibrary.get_credential_store()
        all_creds = store.get(LOCAL_USER_ID)
        if not all_creds: return False, "No Telegram credentials found."

        if args:
            target = args[0]
            store.remove(LOCAL_USER_ID, bot_id=target)
            store.remove(LOCAL_USER_ID, phone_number=target)
            return True, f"Removed Telegram credential: {target}"

        # Remove first credential found
        cred = all_creds[0]
        if cred.connection_type == "bot_api":
            store.remove(LOCAL_USER_ID, bot_id=cred.bot_id)
            return True, f"Removed Telegram bot @{cred.bot_username} ({cred.bot_id})."
        else:
            store.remove(LOCAL_USER_ID, phone_number=cred.phone_number)
            return True, f"Removed Telegram user credential for {cred.phone_number}."

    async def status(self):
        from core.external_libraries.telegram.external_app_library import TelegramAppLibrary
        TelegramAppLibrary.initialize()
        all_creds = TelegramAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not all_creds: return True, "Telegram: Not connected"
        lines = []
        bots = [c for c in all_creds if c.connection_type == "bot_api"]
        users = [c for c in all_creds if c.connection_type == "mtproto"]
        if bots:
            lines.append("  Bots:")
            lines.extend(f"    - @{c.bot_username} ({c.bot_id})" for c in bots)
        if users:
            lines.append("  Users:")
            lines.extend(f"    - {c.account_name or c.phone_number}" for c in users)
        return True, "Telegram: Connected\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# WhatsApp (unified: business + web)
# ═══════════════════════════════════════════════════════════════════

class WhatsAppHandler(IntegrationHandler):
    @property
    def subcommands(self) -> list[str]:
        return ["login", "login-web", "logout", "status"]

    async def handle(self, sub, args):
        if sub == "login-web": return await self._login_web(args)
        return await super().handle(sub, args)

    async def login(self, args):
        if len(args) < 2: return False, "Usage: /whatsapp login <phone_number_id> <access_token> [business_account_id]"

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://graph.facebook.com/v18.0/{args[0]}", headers={"Authorization": f"Bearer {args[1]}"}) as r:
                if r.status != 200: return False, f"WhatsApp validation failed: {r.status}"
                data = await r.json()

        from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
        from core.external_libraries.whatsapp.credentials import WhatsAppCredential
        WhatsAppAppLibrary.initialize()
        WhatsAppAppLibrary.get_credential_store().add(WhatsAppCredential(
            user_id=LOCAL_USER_ID, phone_number_id=args[0], connection_type="business_api",
            business_account_id=args[2] if len(args) > 2 else "",
            access_token=args[1], display_phone_number=data.get("display_phone_number", args[0])))
        return True, f"WhatsApp Business connected: {data.get('display_phone_number', args[0])}"

    async def _login_web(self, args):
        import asyncio

        phone_number = args[0] if args else ""

        try:
            from core.external_libraries.whatsapp.helpers.whatsapp_web_helpers import start_whatsapp_web_session
        except ImportError:
            return False, "Playwright not installed. Run: pip install playwright && playwright install chromium"

        session = await start_whatsapp_web_session(user_id=LOCAL_USER_ID)

        if session.status == "error":
            return False, "Failed to start WhatsApp Web session. Is Playwright installed?\n  pip install playwright && playwright install chromium"

        # Wait for QR code (up to 30s)
        for _ in range(30):
            if session.status == "qr_ready" and session.qr_code:
                break
            if session.status == "connected":
                break
            if session.status == "error":
                return False, "WhatsApp Web session failed to initialize."
            await asyncio.sleep(1)
        else:
            return False, "Timed out waiting for QR code."

        if session.status != "connected":
            # Save QR as temp image and open it
            import tempfile, base64, os
            qr_data = session.qr_code
            if qr_data and qr_data.startswith("data:image"):
                qr_data = qr_data.split(",", 1)[1]
            if qr_data:
                qr_path = os.path.join(tempfile.gettempdir(), f"whatsapp_qr_{session.session_id}.png")
                with open(qr_path, "wb") as f:
                    f.write(base64.b64decode(qr_data))
                webbrowser.open(f"file://{qr_path}")

            # Wait for user to scan QR (up to 120s)
            for _ in range(120):
                if session.status == "connected":
                    break
                if session.status in ("error", "disconnected"):
                    return False, "WhatsApp Web session disconnected or failed."
                await asyncio.sleep(1)
            else:
                return False, "Timed out waiting for QR scan. Run /whatsapp login-web again."

        # Connected — store credential
        from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
        from core.external_libraries.whatsapp.credentials import WhatsAppCredential
        WhatsAppAppLibrary.initialize()

        display_phone = session.phone_number or phone_number or session.session_id
        WhatsAppAppLibrary.get_credential_store().add(WhatsAppCredential(
            user_id=LOCAL_USER_ID,
            phone_number_id=session.session_id,
            connection_type="whatsapp_web",
            session_id=session.session_id,
            jid=session.jid or "",
            display_phone_number=display_phone,
        ))
        return True, f"WhatsApp Web connected: {display_phone}\nSession ID: {session.session_id}"

    async def logout(self, args):
        from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
        WhatsAppAppLibrary.initialize()
        store = WhatsAppAppLibrary.get_credential_store()
        all_creds = store.get(LOCAL_USER_ID)
        if not all_creds: return False, "No WhatsApp credentials found."
        pid = args[0] if args else all_creds[0].phone_number_id
        store.remove(LOCAL_USER_ID, phone_number_id=pid)
        return True, f"Removed WhatsApp credential for {pid}."

    async def status(self):
        from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary
        WhatsAppAppLibrary.initialize()
        all_creds = WhatsAppAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not all_creds: return True, "WhatsApp: Not connected"
        lines = []
        biz = [c for c in all_creds if c.connection_type == "business_api"]
        web = [c for c in all_creds if c.connection_type == "whatsapp_web"]
        if biz:
            lines.append("  Business API:")
            lines.extend(f"    - {c.display_phone_number}" for c in biz)
        if web:
            lines.append("  Web Sessions:")
            lines.extend(f"    - Session: {c.session_id}" for c in web)
        return True, "WhatsApp: Connected\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Recall.ai
# ═══════════════════════════════════════════════════════════════════

class RecallHandler(IntegrationHandler):
    async def login(self, args):
        if not args: return False, "Usage: /recall login <api_key> [region]\nRegion: us (default) or eu"
        api_key, region = args[0], args[1] if len(args) > 1 else "us"

        import aiohttp
        base = "https://us-west-2.recall.ai" if region == "us" else "https://eu-central-1.recall.ai"
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/api/v1/bot/", headers={"Authorization": f"Token {api_key}"}) as r:
                if r.status == 401: return False, "Invalid Recall API key."

        from core.external_libraries.recall.external_app_library import RecallAppLibrary
        from core.external_libraries.recall.credentials import RecallCredential
        RecallAppLibrary.initialize()
        RecallAppLibrary.get_credential_store().add(RecallCredential(user_id=LOCAL_USER_ID, api_key=api_key, region=region))
        return True, f"Recall.ai connected (region: {region})"

    async def logout(self, args):
        from core.external_libraries.recall.external_app_library import RecallAppLibrary
        RecallAppLibrary.initialize()
        store = RecallAppLibrary.get_credential_store()
        creds = store.get(LOCAL_USER_ID)
        if not creds: return False, "No Recall credentials found."
        store.remove(LOCAL_USER_ID)
        return True, "Removed Recall.ai credential."

    async def status(self):
        from core.external_libraries.recall.external_app_library import RecallAppLibrary
        RecallAppLibrary.initialize()
        creds = RecallAppLibrary.get_credential_store().get(LOCAL_USER_ID)
        if not creds: return True, "Recall.ai: Not connected"
        return True, f"Recall.ai: Connected (region: {creds[0].region})"


# ═══════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════

INTEGRATION_HANDLERS: dict[str, IntegrationHandler] = {
    "google":    GoogleHandler(),
    "slack":     SlackHandler(),
    "notion":    NotionHandler(),
    "linkedin":  LinkedInHandler(),
    "zoom":      ZoomHandler(),
    "discord":   DiscordHandler(),
    "telegram":  TelegramHandler(),
    "whatsapp":  WhatsAppHandler(),
    "recall":    RecallHandler(),
}
