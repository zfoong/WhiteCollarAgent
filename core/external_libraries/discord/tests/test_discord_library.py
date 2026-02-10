"""
Comprehensive integration test script for Discord external library.

This script tests ALL Discord API methods using stored credentials.
Run this to verify Discord integration without going through the agent cycle.

Usage:
    python test_discord_library.py [--user-id YOUR_USER_ID] [--list]
    python test_discord_library.py --only bot_info
    python test_discord_library.py --skip-send

If no arguments provided, it will use the first stored credential it finds.
"""
import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.discord.external_app_library import DiscordAppLibrary
from core.external_libraries.discord.helpers import discord_bot_helpers as bot_api


# ═══════════════════════════════════════════════════════════════════════════════
# ANSI Colors
# ═══════════════════════════════════════════════════════════════════════════════

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")


def print_section(text: str):
    """Print a section header."""
    print(f"\n{Colors.CYAN}{'-' * 50}{Colors.END}")
    print(f"{Colors.CYAN}{text}{Colors.END}")
    print(f"{Colors.CYAN}{'-' * 50}{Colors.END}")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}+ {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}x {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}! {text}{Colors.END}")


def print_info(text: str):
    """Print info message."""
    print(f"  {text}")


def print_result(result: Dict[str, Any], indent: int = 2):
    """Pretty print a result dict."""
    formatted = json.dumps(result, indent=indent, default=str)
    for line in formatted.split('\n')[:30]:
        print(f"  {line}")
    if len(formatted.split('\n')) > 30:
        print(f"  ... (output truncated)")


# ═══════════════════════════════════════════════════════════════════════════════
# Test Runner
# ═══════════════════════════════════════════════════════════════════════════════

class DiscordTester:
    """Test runner for Discord API methods."""

    def __init__(
        self,
        user_id: str,
        bot_id: Optional[str] = None,
        discord_user_id: Optional[str] = None,
        skip_send: bool = False,
    ):
        self.user_id = user_id
        self.bot_id = bot_id
        self.discord_user_id = discord_user_id
        self.skip_send = skip_send
        self.test_results: Dict[str, str] = {}

        # Discovered IDs during testing
        self.discovered_guild_id: Optional[str] = None
        self.discovered_channel_id: Optional[str] = None
        self.discovered_message_id: Optional[str] = None

        # Track created resources for cleanup
        self.created_bot_messages: List[Dict[str, str]] = []   # [{"channel_id": ..., "message_id": ...}]

        # Track whether we have bot / user credentials
        self.has_bot = False
        self.has_user = False

    # -----------------------------------------------------------------------
    # Generic test executor
    # -----------------------------------------------------------------------

    def run_test(self, test_name: str, func, *args, **kwargs) -> Dict[str, Any]:
        """Run a single test and record result."""
        print(f"\n  Testing: {test_name}...")
        try:
            result = func(*args, **kwargs)
            status = result.get('status', 'unknown')

            if status == 'success':
                print_success(f"{test_name} - SUCCESS")
                self.test_results[test_name] = 'PASS'
            else:
                reason = result.get('message', result.get('reason', result.get('details', 'Unknown error')))
                print_error(f"{test_name} - FAILED: {reason}")
                self.test_results[test_name] = 'FAIL'

            return result
        except Exception as e:
            print_error(f"{test_name} - EXCEPTION: {str(e)}")
            self.test_results[test_name] = 'ERROR'
            return {"status": "error", "message": str(e)}

    # ═══════════════════════════════════════════════════════════════════════
    # BOT OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def test_bot_info(self):
        """Test get_bot_info."""
        print_section("BOT INFO")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping bot info tests.")
            return

        result = self.run_test(
            "get_bot_info",
            DiscordAppLibrary.get_bot_info,
            user_id=self.user_id,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            bot = result.get('bot', {})
            print_info(f"Bot ID: {bot.get('id', 'N/A')}")
            print_info(f"Bot Username: {bot.get('username', 'N/A')}")

    def test_bot_guilds(self):
        """Test get_bot_guilds and discover a guild_id for subsequent tests."""
        print_section("BOT GUILDS")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping bot guild tests.")
            return

        result = self.run_test(
            "get_bot_guilds",
            DiscordAppLibrary.get_bot_guilds,
            user_id=self.user_id,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            guilds = result.get('guilds', [])
            print_info(f"Found {len(guilds)} guild(s)")
            if guilds:
                self.discovered_guild_id = guilds[0].get('id')
                print_info(f"Using guild: {guilds[0].get('name', 'N/A')} ({self.discovered_guild_id})")
            else:
                print_warning("Bot is not in any guilds. Channel/member tests will be skipped.")

    def test_guild_channels(self):
        """Test get_guild_channels and discover a text channel_id."""
        print_section("GUILD CHANNELS")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping guild channel tests.")
            return

        if not self.discovered_guild_id:
            print_warning("No guild discovered. Skipping guild channel tests.")
            return

        result = self.run_test(
            "get_guild_channels",
            DiscordAppLibrary.get_guild_channels,
            user_id=self.user_id,
            guild_id=self.discovered_guild_id,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            text_channels = result.get('text_channels', [])
            voice_channels = result.get('voice_channels', [])
            categories = result.get('categories', [])
            print_info(f"Text channels: {len(text_channels)}")
            print_info(f"Voice channels: {len(voice_channels)}")
            print_info(f"Categories: {len(categories)}")
            if text_channels:
                self.discovered_channel_id = text_channels[0].get('id')
                print_info(f"Using channel: {text_channels[0].get('name', 'N/A')} ({self.discovered_channel_id})")

    def test_guild_members(self):
        """Test get_guild_members."""
        print_section("GUILD MEMBERS")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping guild member tests.")
            return

        if not self.discovered_guild_id:
            print_warning("No guild discovered. Skipping guild member tests.")
            return

        result = self.run_test(
            "get_guild_members",
            DiscordAppLibrary.get_guild_members,
            user_id=self.user_id,
            guild_id=self.discovered_guild_id,
            limit=10,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            members = result.get('members', [])
            print_info(f"Retrieved {len(members)} member(s)")
            for m in members[:3]:
                user = m.get('user', {})
                print_info(f"  - {user.get('username', 'N/A')} ({user.get('id', 'N/A')})")
            if len(members) > 3:
                print_info(f"  ... and {len(members) - 3} more")

    def test_get_messages_bot(self):
        """Test get_messages (bot) and discover a message_id for reaction tests."""
        print_section("GET MESSAGES (BOT)")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping bot get_messages tests.")
            return

        if not self.discovered_channel_id:
            print_warning("No channel discovered. Skipping bot get_messages tests.")
            return

        result = self.run_test(
            "get_messages (bot)",
            DiscordAppLibrary.get_messages,
            user_id=self.user_id,
            channel_id=self.discovered_channel_id,
            limit=5,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            messages = result.get('messages', [])
            print_info(f"Retrieved {len(messages)} message(s)")
            if messages:
                self.discovered_message_id = messages[0].get('id')
                author = messages[0].get('author', {})
                content_preview = (messages[0].get('content', '') or '')[:60]
                print_info(f"Latest message by {author.get('username', 'N/A')}: {content_preview}")

    def test_send_message_bot(self):
        """Test send_message (bot). Skippable with --skip-send."""
        print_section("SEND MESSAGE (BOT)")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping bot send_message tests.")
            return

        if self.skip_send:
            print_warning("--skip-send flag set. Skipping bot send_message test.")
            return

        if not self.discovered_channel_id:
            print_warning("No channel discovered. Skipping bot send_message test.")
            return

        test_content = f"[CraftOS Integration Test] Bot message at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        result = self.run_test(
            "send_message (bot)",
            DiscordAppLibrary.send_message,
            user_id=self.user_id,
            channel_id=self.discovered_channel_id,
            content=test_content,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            msg_id = result.get('message_id')
            print_info(f"Sent message ID: {msg_id}")
            if msg_id:
                self.created_bot_messages.append({
                    "channel_id": self.discovered_channel_id,
                    "message_id": msg_id,
                })

    def test_send_message_bot_with_embed(self):
        """Test send_message (bot) with an embed. Skippable with --skip-send."""
        print_section("SEND MESSAGE WITH EMBED (BOT)")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping bot embed test.")
            return

        if self.skip_send:
            print_warning("--skip-send flag set. Skipping bot embed test.")
            return

        if not self.discovered_channel_id:
            print_warning("No channel discovered. Skipping bot embed test.")
            return

        embed = {
            "title": "CraftOS Integration Test",
            "description": "This embed was sent by an automated integration test.",
            "color": 3066993,
            "footer": {"text": f"Tested at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
        }
        result = self.run_test(
            "send_message (bot, embed)",
            DiscordAppLibrary.send_message,
            user_id=self.user_id,
            channel_id=self.discovered_channel_id,
            content="",
            embed=embed,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            msg_id = result.get('message_id')
            print_info(f"Sent embed message ID: {msg_id}")
            if msg_id:
                self.created_bot_messages.append({
                    "channel_id": self.discovered_channel_id,
                    "message_id": msg_id,
                })

    def test_add_reaction(self):
        """Test add_reaction."""
        print_section("ADD REACTION (BOT)")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping reaction tests.")
            return

        if self.skip_send:
            print_warning("--skip-send flag set. Skipping reaction test.")
            return

        # Prefer reacting to our own test message, fall back to discovered
        target_channel = None
        target_message = None

        if self.created_bot_messages:
            target_channel = self.created_bot_messages[0]["channel_id"]
            target_message = self.created_bot_messages[0]["message_id"]
        elif self.discovered_message_id and self.discovered_channel_id:
            target_channel = self.discovered_channel_id
            target_message = self.discovered_message_id

        if not target_channel or not target_message:
            print_warning("No message available for reaction test. Skipping.")
            return

        result = self.run_test(
            "add_reaction",
            DiscordAppLibrary.add_reaction,
            user_id=self.user_id,
            channel_id=target_channel,
            message_id=target_message,
            emoji="%E2%9C%85",  # URL-encoded checkmark emoji
            bot_id=self.bot_id,
        )

    def test_send_dm_bot(self):
        """Test send_dm_bot. Skippable with --skip-send."""
        print_section("SEND DM (BOT)")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping bot DM test.")
            return

        if self.skip_send:
            print_warning("--skip-send flag set. Skipping bot DM test.")
            return

        # We need a recipient. Use the bot's own user ID to DM itself (will fail),
        # or use a discovered guild member. For safety, just report as skipped.
        print_warning("send_dm_bot requires a specific recipient_id. Skipping to avoid spam.")
        print_info("To test manually: DiscordAppLibrary.send_dm_bot(user_id=..., recipient_id=..., content=...)")

    def test_voice_status(self):
        """Test get_voice_status (read-only, no actual voice join)."""
        print_section("VOICE STATUS (BOT)")

        if not self.has_bot:
            print_warning("No bot credentials available. Skipping voice status test.")
            return

        if not self.discovered_guild_id:
            print_warning("No guild discovered. Skipping voice status test.")
            return

        result = self.run_test(
            "get_voice_status",
            DiscordAppLibrary.get_voice_status,
            user_id=self.user_id,
            guild_id=self.discovered_guild_id,
            bot_id=self.bot_id,
        )

        if result.get('status') == 'success':
            connected = result.get('connected', False)
            print_info(f"Voice connected: {connected}")

    # ═══════════════════════════════════════════════════════════════════════
    # USER ACCOUNT OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def test_user_info(self):
        """Test get_user_info."""
        print_section("USER INFO")

        if not self.has_user:
            print_warning("No user credentials available. Skipping user info tests.")
            return

        result = self.run_test(
            "get_user_info",
            DiscordAppLibrary.get_user_info,
            user_id=self.user_id,
            discord_user_id=self.discord_user_id,
        )

        if result.get('status') == 'success':
            user = result.get('user', {})
            print_info(f"Discord User: {user.get('username', 'N/A')}")
            print_info(f"Discord User ID: {user.get('id', 'N/A')}")

    def test_user_guilds(self):
        """Test get_user_guilds."""
        print_section("USER GUILDS")

        if not self.has_user:
            print_warning("No user credentials available. Skipping user guild tests.")
            return

        result = self.run_test(
            "get_user_guilds",
            DiscordAppLibrary.get_user_guilds,
            user_id=self.user_id,
            discord_user_id=self.discord_user_id,
        )

        if result.get('status') == 'success':
            guilds = result.get('guilds', [])
            print_info(f"Found {len(guilds)} guild(s)")
            for g in guilds[:5]:
                print_info(f"  - {g.get('name', 'N/A')} ({g.get('id', 'N/A')})")
            if len(guilds) > 5:
                print_info(f"  ... and {len(guilds) - 5} more")

    def test_dm_channels(self):
        """Test get_dm_channels."""
        print_section("DM CHANNELS (USER)")

        if not self.has_user:
            print_warning("No user credentials available. Skipping DM channel tests.")
            return

        result = self.run_test(
            "get_dm_channels",
            DiscordAppLibrary.get_dm_channels,
            user_id=self.user_id,
            discord_user_id=self.discord_user_id,
        )

        if result.get('status') == 'success':
            channels = result.get('dm_channels', [])
            count = result.get('count', len(channels))
            print_info(f"Found {count} DM channel(s)")
            for ch in channels[:3]:
                recipients = ch.get('recipients', [])
                names = ", ".join(r.get('username', '?') for r in recipients)
                print_info(f"  - {names} (channel {ch.get('id', 'N/A')})")
            if count > 3:
                print_info(f"  ... and {count - 3} more")

    def test_get_messages_user(self):
        """Test get_messages_user."""
        print_section("GET MESSAGES (USER)")

        if not self.has_user:
            print_warning("No user credentials available. Skipping user get_messages tests.")
            return

        # We need a channel_id. Try to get one from DM channels.
        dm_result = DiscordAppLibrary.get_dm_channels(
            user_id=self.user_id,
            discord_user_id=self.discord_user_id,
        )
        dm_channel_id = None
        if dm_result.get('status') == 'success':
            channels = dm_result.get('dm_channels', [])
            if channels:
                dm_channel_id = channels[0].get('id')

        if not dm_channel_id:
            print_warning("No DM channel found to read messages from. Skipping.")
            return

        print_info(f"Reading messages from DM channel: {dm_channel_id}")

        result = self.run_test(
            "get_messages_user",
            DiscordAppLibrary.get_messages_user,
            user_id=self.user_id,
            channel_id=dm_channel_id,
            limit=5,
            discord_user_id=self.discord_user_id,
        )

        if result.get('status') == 'success':
            messages = result.get('messages', [])
            print_info(f"Retrieved {len(messages)} message(s)")

    def test_send_message_user(self):
        """Test send_message_user. Skippable with --skip-send."""
        print_section("SEND MESSAGE (USER)")

        if not self.has_user:
            print_warning("No user credentials available. Skipping user send_message test.")
            return

        if self.skip_send:
            print_warning("--skip-send flag set. Skipping user send_message test.")
            return

        print_warning("send_message_user requires a specific channel_id. Skipping to avoid spam.")
        print_info("To test manually: DiscordAppLibrary.send_message_user(user_id=..., channel_id=..., content=...)")

    def test_send_dm_user(self):
        """Test send_dm_user. Skippable with --skip-send."""
        print_section("SEND DM (USER)")

        if not self.has_user:
            print_warning("No user credentials available. Skipping user DM test.")
            return

        if self.skip_send:
            print_warning("--skip-send flag set. Skipping user DM test.")
            return

        print_warning("send_dm_user requires a specific recipient_id. Skipping to avoid spam.")
        print_info("To test manually: DiscordAppLibrary.send_dm_user(user_id=..., recipient_id=..., content=...)")

    def test_friends(self):
        """Test get_friends."""
        print_section("FRIENDS LIST (USER)")

        if not self.has_user:
            print_warning("No user credentials available. Skipping friends test.")
            return

        result = self.run_test(
            "get_friends",
            DiscordAppLibrary.get_friends,
            user_id=self.user_id,
            discord_user_id=self.discord_user_id,
        )

        if result.get('status') == 'success':
            friends = result.get('friends', [])
            total = result.get('total_friends', len(friends))
            print_info(f"Total friends: {total}")
            for f in friends[:5]:
                print_info(f"  - {f.get('username', 'N/A')} ({f.get('id', 'N/A')})")
            if total > 5:
                print_info(f"  ... and {total - 5} more")

    # ═══════════════════════════════════════════════════════════════════════
    # CREDENTIAL MANAGEMENT (verify store operations)
    # ═══════════════════════════════════════════════════════════════════════

    def test_credential_store_operations(self):
        """Verify credential store lookup works."""
        print_section("CREDENTIAL STORE OPERATIONS")

        # Bot credentials lookup
        print(f"\n  Testing: get_bot_credentials...")
        try:
            creds = DiscordAppLibrary.get_bot_credentials(self.user_id, self.bot_id)
            if creds:
                print_success(f"get_bot_credentials - SUCCESS (found {len(creds)} credential(s))")
                self.test_results["get_bot_credentials"] = "PASS"
                print_info(f"Bot ID: {creds[0].bot_id}")
                print_info(f"Bot Username: {creds[0].bot_username}")
            else:
                print_warning("get_bot_credentials - No bot credentials found (not an error)")
                self.test_results["get_bot_credentials"] = "PASS"
        except Exception as e:
            print_error(f"get_bot_credentials - EXCEPTION: {e}")
            self.test_results["get_bot_credentials"] = "ERROR"

        # User credentials lookup
        print(f"\n  Testing: get_user_credentials...")
        try:
            creds = DiscordAppLibrary.get_user_credentials(self.user_id, self.discord_user_id)
            if creds:
                print_success(f"get_user_credentials - SUCCESS (found {len(creds)} credential(s))")
                self.test_results["get_user_credentials"] = "PASS"
                print_info(f"Discord User ID: {creds[0].discord_user_id}")
                print_info(f"Username: {creds[0].username}")
            else:
                print_warning("get_user_credentials - No user credentials found (not an error)")
                self.test_results["get_user_credentials"] = "PASS"
        except Exception as e:
            print_error(f"get_user_credentials - EXCEPTION: {e}")
            self.test_results["get_user_credentials"] = "ERROR"

        # Shared bot guild lookup
        print(f"\n  Testing: get_shared_bot_guilds...")
        try:
            guilds = DiscordAppLibrary.get_shared_bot_guilds(self.user_id)
            print_success(f"get_shared_bot_guilds - SUCCESS (found {len(guilds)} association(s))")
            self.test_results["get_shared_bot_guilds"] = "PASS"
            for g in guilds[:3]:
                print_info(f"  Guild: {g.guild_name} ({g.guild_id})")
        except Exception as e:
            print_error(f"get_shared_bot_guilds - EXCEPTION: {e}")
            self.test_results["get_shared_bot_guilds"] = "ERROR"

        # get_bot_token_for_guild
        if self.discovered_guild_id:
            print(f"\n  Testing: get_bot_token_for_guild...")
            try:
                token_info = DiscordAppLibrary.get_bot_token_for_guild(
                    self.user_id, self.discovered_guild_id, self.bot_id
                )
                if token_info:
                    print_success("get_bot_token_for_guild - SUCCESS (token resolved)")
                    self.test_results["get_bot_token_for_guild"] = "PASS"
                    print_info(f"Resolved bot_id: {token_info[1]}")
                else:
                    print_warning("get_bot_token_for_guild - No token resolved (may be expected)")
                    self.test_results["get_bot_token_for_guild"] = "PASS"
            except Exception as e:
                print_error(f"get_bot_token_for_guild - EXCEPTION: {e}")
                self.test_results["get_bot_token_for_guild"] = "ERROR"

    # ═══════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════

    def cleanup(self):
        """Clean up any messages created during testing."""
        print_section("CLEANUP")

        if not self.created_bot_messages:
            print_info("No test messages to clean up.")
            return

        # Get bot token for direct API cleanup
        bot_creds = DiscordAppLibrary.get_bot_credentials(self.user_id, self.bot_id)
        if not bot_creds:
            print_warning("Cannot clean up: no bot credentials for deletion.")
            return

        bot_token = bot_creds[0].bot_token

        for msg_info in self.created_bot_messages:
            channel_id = msg_info["channel_id"]
            message_id = msg_info["message_id"]
            print_info(f"Deleting test message {message_id} from channel {channel_id}...")
            try:
                result = bot_api.delete_message(bot_token, channel_id, message_id)
                if "ok" in result:
                    print_success(f"Deleted message {message_id}")
                else:
                    print_error(f"Failed to delete message {message_id}: {result.get('error', 'Unknown')}")
            except Exception as e:
                print_error(f"Failed to delete message {message_id}: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════

    def print_summary(self):
        """Print test summary."""
        print_header("TEST SUMMARY")

        passed = sum(1 for v in self.test_results.values() if v == 'PASS')
        failed = sum(1 for v in self.test_results.values() if v == 'FAIL')
        errors = sum(1 for v in self.test_results.values() if v == 'ERROR')
        total = len(self.test_results)

        print(f"\n  Total tests: {total}")
        print(f"  {Colors.GREEN}Passed: {passed}{Colors.END}")
        print(f"  {Colors.RED}Failed: {failed}{Colors.END}")
        print(f"  {Colors.YELLOW}Errors: {errors}{Colors.END}")

        print(f"\n  {Colors.BOLD}Detailed Results:{Colors.END}")
        for name, result in self.test_results.items():
            if result == 'PASS':
                print(f"    {Colors.GREEN}+{Colors.END} {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}x{Colors.END} {name}")
            else:
                print(f"    {Colors.YELLOW}!{Colors.END} {name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Credential Listing
# ═══════════════════════════════════════════════════════════════════════════════

def list_credentials():
    """List all stored Discord credentials (bot + user)."""
    print_header("STORED DISCORD CREDENTIALS")

    DiscordAppLibrary.initialize()
    bot_store = DiscordAppLibrary._bot_credentials_store
    user_store = DiscordAppLibrary._user_credentials_store
    guild_store = DiscordAppLibrary._shared_bot_guild_store

    # Gather bot credentials
    all_bot_creds = []
    for user_id, creds in bot_store.credentials.items():
        all_bot_creds.extend(creds)

    # Gather user credentials
    all_user_creds = []
    for user_id, creds in user_store.credentials.items():
        all_user_creds.extend(creds)

    # Gather shared guild associations
    all_guild_creds = []
    for user_id, creds in guild_store.credentials.items():
        all_guild_creds.extend(creds)

    if not all_bot_creds and not all_user_creds:
        print_warning("No Discord credentials found.")
        print_info("Please add bot or user credentials via the CraftOS control panel first.")
        return None, None, None

    # Print bot credentials
    if all_bot_creds:
        print(f"\n  {Colors.BOLD}Bot Credentials ({len(all_bot_creds)}):{Colors.END}\n")
        for i, cred in enumerate(all_bot_creds, 1):
            print(f"  [{i}] User ID:      {cred.user_id}")
            print(f"      Bot ID:       {cred.bot_id}")
            print(f"      Bot Username: {cred.bot_username}")
            print(f"      Has Token:    {bool(cred.bot_token)}")
            print()

    # Print user credentials
    if all_user_creds:
        print(f"\n  {Colors.BOLD}User Credentials ({len(all_user_creds)}):{Colors.END}\n")
        for i, cred in enumerate(all_user_creds, 1):
            print(f"  [{i}] User ID:         {cred.user_id}")
            print(f"      Discord User ID: {cred.discord_user_id}")
            print(f"      Username:        {cred.username}")
            print(f"      Discriminator:   {cred.discriminator}")
            print(f"      Has Token:       {bool(cred.user_token)}")
            print()

    # Print shared guild associations
    if all_guild_creds:
        print(f"\n  {Colors.BOLD}Shared Bot Guilds ({len(all_guild_creds)}):{Colors.END}\n")
        for i, cred in enumerate(all_guild_creds, 1):
            print(f"  [{i}] User ID:      {cred.user_id}")
            print(f"      Guild ID:     {cred.guild_id}")
            print(f"      Guild Name:   {cred.guild_name}")
            print(f"      Connected At: {cred.connected_at}")
            print()

    # Return first available identifiers
    first_user_id = all_bot_creds[0].user_id if all_bot_creds else (all_user_creds[0].user_id if all_user_creds else None)
    first_bot_id = all_bot_creds[0].bot_id if all_bot_creds else None
    first_discord_user_id = all_user_creds[0].discord_user_id if all_user_creds else None

    return first_user_id, first_bot_id, first_discord_user_id


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Test Discord API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--bot-id', type=str, help='Specific Discord bot ID to use')
    parser.add_argument('--discord-user-id', type=str, help='Specific Discord user ID to use')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--skip-send', action='store_true', help='Skip tests that send messages / reactions')
    parser.add_argument(
        '--only', type=str,
        help=(
            'Only run a specific test group. Options: '
            'creds, bot_info, bot_guilds, channels, members, get_messages_bot, '
            'send_bot, embed_bot, reaction, dm_bot, voice, '
            'user_info, user_guilds, dm_channels, get_messages_user, '
            'send_user, dm_user, friends'
        ),
    )
    args = parser.parse_args()

    print_header("DISCORD EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    DiscordAppLibrary.initialize()
    print_success("DiscordAppLibrary initialized")

    # List credentials if requested
    if args.list:
        list_credentials()
        return

    # Resolve credentials
    user_id = args.user_id
    bot_id = args.bot_id
    discord_user_id = args.discord_user_id

    if not user_id:
        print_section("CREDENTIAL LOOKUP")
        user_id, bot_id_found, discord_user_id_found = list_credentials()

        if not user_id:
            print_error("No credentials available. Exiting.")
            return

        if not bot_id:
            bot_id = bot_id_found
        if not discord_user_id:
            discord_user_id = discord_user_id_found

    print_info(f"Using: user_id={user_id}")
    if bot_id:
        print_info(f"       bot_id={bot_id}")
    if discord_user_id:
        print_info(f"       discord_user_id={discord_user_id}")

    # Determine what credential types we have
    has_bot = bool(DiscordAppLibrary.get_bot_credentials(user_id, bot_id))
    has_user = bool(DiscordAppLibrary.get_user_credentials(user_id, discord_user_id))

    if has_bot:
        print_success("Bot credentials found")
    else:
        print_warning("No bot credentials found - bot tests will be skipped")

    if has_user:
        print_success("User credentials found")
    else:
        print_warning("No user credentials found - user account tests will be skipped")

    if not has_bot and not has_user:
        print_error("No credentials of any type found. Nothing to test. Exiting.")
        return

    # Create tester
    tester = DiscordTester(
        user_id=user_id,
        bot_id=bot_id,
        discord_user_id=discord_user_id,
        skip_send=args.skip_send,
    )
    tester.has_bot = has_bot
    tester.has_user = has_user

    # -----------------------------------------------------------------------
    # Test group registry
    # -----------------------------------------------------------------------

    # Bot test groups (order matters: guilds/channels discover IDs for later)
    BOT_DISCOVERY = [
        ('bot_info',         tester.test_bot_info),
        ('bot_guilds',       tester.test_bot_guilds),
        ('channels',         tester.test_guild_channels),
    ]
    BOT_READ = [
        ('members',          tester.test_guild_members),
        ('get_messages_bot', tester.test_get_messages_bot),
        ('voice',            tester.test_voice_status),
        ('creds',            tester.test_credential_store_operations),
    ]
    BOT_WRITE = [
        ('send_bot',         tester.test_send_message_bot),
        ('embed_bot',        tester.test_send_message_bot_with_embed),
        ('reaction',         tester.test_add_reaction),
        ('dm_bot',           tester.test_send_dm_bot),
    ]

    # User test groups
    USER_TESTS = [
        ('user_info',         tester.test_user_info),
        ('user_guilds',       tester.test_user_guilds),
        ('dm_channels',       tester.test_dm_channels),
        ('get_messages_user', tester.test_get_messages_user),
        ('send_user',         tester.test_send_message_user),
        ('dm_user',           tester.test_send_dm_user),
        ('friends',           tester.test_friends),
    ]

    ALL_GROUPS = BOT_DISCOVERY + BOT_READ + BOT_WRITE + USER_TESTS

    try:
        if args.only:
            # Find the requested group
            group_map = {name: func for name, func in ALL_GROUPS}
            if args.only not in group_map:
                print_error(f"Unknown test group: {args.only}")
                print_info(f"Available: {', '.join(name for name, _ in ALL_GROUPS)}")
                return

            # For groups that depend on discovery, run discovery first
            discovery_dependent = {name for name, _ in BOT_READ + BOT_WRITE}
            if args.only in discovery_dependent:
                print_info("Running bot discovery first (needed for this test group)...")
                for name, func in BOT_DISCOVERY:
                    func()

            group_map[args.only]()
        else:
            # Run all tests in order
            for name, func in ALL_GROUPS:
                func()

    finally:
        # Cleanup created messages
        if not args.skip_send:
            tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
