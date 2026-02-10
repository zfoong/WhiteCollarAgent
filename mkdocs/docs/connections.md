# Connections

White Collar Agent integrates with 9 external services. Each integration has two connection methods:

- **Invite** (easy) — Add the CraftOS-hosted bot/app to your workspace. No API keys needed.
- **Login** (advanced) — Bring your own bot token, API key, or OAuth credentials.

Use `/cred status` to see all active connections at a glance.

---

## Discord

Send messages, read channels, list servers, and DM users via Discord.

**Available actions:** `send_discord_message`, `get_discord_messages`, `list_discord_guilds`, `get_discord_channels`, `send_discord_dm`

### Connect

| Command | Description |
|---------|-------------|
| `/discord invite` | Add the CraftOS bot to your server (opens browser) |
| `/discord invite <guild_id> [name]` | Register a guild after adding the bot |
| `/discord login <bot_token>` | Connect your own Discord bot |
| `/discord login-user <user_token>` | Connect a Discord user account |
| `/discord status` | Show all Discord connections |
| `/discord logout [id]` | Remove a connection |

### Prerequisites

- **Invite:** Requires `DISCORD_SHARED_BOT_ID` env var (set by CraftOS admin)
- **Login:** Create a bot at [discord.com/developers](https://discord.com/developers/applications), copy the bot token

---

## Slack

Send messages, list channels/users, search messages, read history, and upload files.

**Available actions:** `send_slack_message`, `list_slack_channels`, `get_slack_channel_history`, `list_slack_users`, `search_slack_messages`, `upload_slack_file`

### Connect

| Command | Description |
|---------|-------------|
| `/slack invite` | Install the CraftOS Slack app to your workspace (OAuth flow) |
| `/slack login <bot_token> [workspace_name]` | Connect your own Slack bot token |
| `/slack status` | Show connected workspaces |
| `/slack logout [workspace_id]` | Remove a workspace connection |

### Prerequisites

- **Invite:** Requires `SLACK_SHARED_CLIENT_ID` and `SLACK_SHARED_CLIENT_SECRET` env vars
- **Login:** Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps), install to workspace, copy the Bot User OAuth Token (`xoxb-...`)

---

## Telegram

Send messages/photos, get updates, look up chats, and search contacts.

**Available actions:** `send_telegram_message`, `send_telegram_photo`, `get_telegram_updates`, `get_telegram_chat`, `search_telegram_contact`

### Connect

| Command | Description |
|---------|-------------|
| `/telegram invite` | Connect the CraftOS Telegram bot (opens t.me link) |
| `/telegram login <bot_token>` | Connect your own bot from @BotFather |
| `/telegram login-user <api_id> <api_hash> <session_string> [phone]` | Connect a Telegram user account (MTProto) |
| `/telegram status` | Show all Telegram connections |
| `/telegram logout [id]` | Remove a connection |

### Prerequisites

- **Invite:** Requires `TELEGRAM_SHARED_BOT_TOKEN` and `TELEGRAM_SHARED_BOT_USERNAME` env vars
- **Login:** Message [@BotFather](https://t.me/BotFather) on Telegram to create a bot and get the token
- **Login-user:** Get API credentials from [my.telegram.org](https://my.telegram.org), generate a session string with Telethon

---

## Notion

Search pages/databases, create and update pages, query databases.

**Available actions:** `search_notion`, `get_notion_page`, `create_notion_page`, `query_notion_database`, `update_notion_page`

### Connect

| Command | Description |
|---------|-------------|
| `/notion invite` | Authorize the CraftOS Notion integration (OAuth flow) |
| `/notion login <integration_token>` | Connect your own Notion integration |
| `/notion status` | Show connected workspaces |
| `/notion logout [workspace_id]` | Remove a workspace connection |

### Prerequisites

- **Invite:** Requires `NOTION_SHARED_CLIENT_ID` and `NOTION_SHARED_CLIENT_SECRET` env vars
- **Login:** Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations), copy the Internal Integration Secret

---

## Google Workspace

Send/read emails (Gmail), create calendar events with Google Meet, manage Google Drive files.

**Available actions:** `send_gmail`, `list_gmail`, `get_gmail`, `read_top_emails`, `create_google_meet`, `check_calendar_availability`, `list_drive_files`, `create_drive_folder`, `move_drive_file`

### Connect

| Command | Description |
|---------|-------------|
| `/google login` | Authenticate via Google OAuth (opens browser) |
| `/google status` | Show connected Google accounts |
| `/google logout [email]` | Remove a Google account |

### Prerequisites

Requires `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` env vars. Create OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/apis/credentials).

Scopes requested: Gmail, Calendar, Drive, Contacts, UserInfo.

---

## LinkedIn

View profile, create posts, search jobs, get connections, send messages.

**Available actions:** `get_linkedin_profile`, `create_linkedin_post`, `search_linkedin_jobs`, `get_linkedin_connections`, `send_linkedin_message`

### Connect

| Command | Description |
|---------|-------------|
| `/linkedin login` | Authenticate via LinkedIn OAuth (opens browser) |
| `/linkedin status` | Show connected accounts |
| `/linkedin logout [linkedin_id]` | Remove an account |

### Prerequisites

Requires `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` env vars. Create an app at [linkedin.com/developers](https://www.linkedin.com/developers/).

---

## Zoom

Create, list, get details, and delete Zoom meetings.

**Available actions:** `create_zoom_meeting`, `list_zoom_meetings`, `get_zoom_meeting`, `delete_zoom_meeting`

### Connect

| Command | Description |
|---------|-------------|
| `/zoom login` | Authenticate via Zoom OAuth (opens browser) |
| `/zoom status` | Show connected Zoom accounts |
| `/zoom logout [zoom_user_id]` | Remove an account |

### Prerequisites

Requires `ZOOM_CLIENT_ID` and `ZOOM_CLIENT_SECRET` env vars. Create an OAuth app at [marketplace.zoom.us](https://marketplace.zoom.us/).

---

## WhatsApp

Send text, media, and template messages via WhatsApp Business API or WhatsApp Web.

**Available actions:** `send_whatsapp_message`, `send_whatsapp_media`, `send_whatsapp_template`, `get_whatsapp_profile`

### Connect

| Command | Description |
|---------|-------------|
| `/whatsapp login <phone_number_id> <access_token> [business_account_id]` | Connect WhatsApp Business API |
| `/whatsapp login-web [phone_number]` | Connect via WhatsApp Web (scan QR code) |
| `/whatsapp status` | Show all WhatsApp connections |
| `/whatsapp logout [id]` | Remove a connection |

### Prerequisites

- **Business API:** Set up a WhatsApp Business account in [Meta Business Suite](https://business.facebook.com/), get the Phone Number ID and Access Token
- **Web:** Requires Playwright (`pip install playwright && playwright install chromium`). A QR code will open in your browser — scan it with your phone's WhatsApp camera to connect.

---

## Recall.ai

Create meeting bots that join calls to record and transcribe (Zoom, Google Meet, Teams).

**Available actions:** `create_recall_bot`, `get_recall_bot`, `get_recall_transcript`, `recall_leave_meeting`

### Connect

| Command | Description |
|---------|-------------|
| `/recall login <api_key> [region]` | Connect with Recall.ai API key (region: `us` or `eu`) |
| `/recall status` | Show connection status |
| `/recall logout` | Remove the credential |

### Prerequisites

Get an API key from [recall.ai](https://www.recall.ai/). Default region is `us`.

---

## Environment Variables Reference

Set these in your environment or `.env` file:

| Variable | Integration | Required for |
|----------|-------------|-------------|
| `GOOGLE_CLIENT_ID` | Google | `/google login` |
| `GOOGLE_CLIENT_SECRET` | Google | `/google login` |
| `LINKEDIN_CLIENT_ID` | LinkedIn | `/linkedin login` |
| `LINKEDIN_CLIENT_SECRET` | LinkedIn | `/linkedin login` |
| `ZOOM_CLIENT_ID` | Zoom | `/zoom login` |
| `ZOOM_CLIENT_SECRET` | Zoom | `/zoom login` |
| `DISCORD_SHARED_BOT_TOKEN` | Discord | Shared bot operations |
| `DISCORD_SHARED_BOT_ID` | Discord | `/discord invite` |
| `SLACK_SHARED_CLIENT_ID` | Slack | `/slack invite` |
| `SLACK_SHARED_CLIENT_SECRET` | Slack | `/slack invite` |
| `TELEGRAM_SHARED_BOT_TOKEN` | Telegram | `/telegram invite` |
| `TELEGRAM_SHARED_BOT_USERNAME` | Telegram | `/telegram invite` |
| `NOTION_SHARED_CLIENT_ID` | Notion | `/notion invite` |
| `NOTION_SHARED_CLIENT_SECRET` | Notion | `/notion invite` |
