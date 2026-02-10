"""
Comprehensive integration test script for Telegram external library.

This script tests ALL Telegram API methods (Bot API and MTProto) using stored
credentials. Run this to verify Telegram integration without going through the
agent cycle.

Usage:
    python test_telegram_library.py [--user-id YOUR_USER_ID] [--chat-id CHAT_ID]
    python test_telegram_library.py --list
    python test_telegram_library.py --only bot
    python test_telegram_library.py --only mtproto --skip-send
    python test_telegram_library.py --only send --chat-id 123456789

If no arguments provided, it will use the first stored credential.
"""
import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.telegram.external_app_library import TelegramAppLibrary

# ANSI colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
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
    print(f"{Colors.GREEN}[PASS] {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}[FAIL] {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}[WARN] {text}{Colors.END}")


def print_info(text: str):
    """Print info message."""
    print(f"  {text}")


def print_skip(text: str):
    """Print skip message."""
    print(f"{Colors.MAGENTA}[SKIP] {text}{Colors.END}")


def print_result(result: Dict[str, Any], indent: int = 2):
    """Pretty print a result dict."""
    formatted = json.dumps(result, indent=indent, default=str)
    for line in formatted.split('\n')[:30]:  # Limit output
        print(f"  {line}")
    if len(formatted.split('\n')) > 30:
        print(f"  ... (output truncated)")


class TelegramTester:
    """Test runner for Telegram API methods (Bot API and MTProto)."""

    def __init__(
        self,
        user_id: str,
        chat_id: Optional[str] = None,
        skip_send: bool = False,
    ):
        self.user_id = user_id
        self.chat_id = chat_id
        self.skip_send = skip_send
        self.test_results: Dict[str, str] = {}
        self.sent_message_ids: list = []  # Track messages to clean up
        self.bot_user_id: Optional[int] = None  # Bot's own user ID for get_chat_member

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
                reason = result.get('reason', result.get('details', 'Unknown error'))
                print_error(f"{test_name} - FAILED: {reason}")
                self.test_results[test_name] = 'FAIL'

            return result
        except Exception as e:
            print_error(f"{test_name} - EXCEPTION: {str(e)}")
            self.test_results[test_name] = 'ERROR'
            return {"status": "error", "reason": str(e)}

    # ==================================================================
    # BOT API TESTS
    # ==================================================================

    def test_initialize(self):
        """Test library initialization."""
        print_section("INITIALIZATION")

        print(f"\n  Testing: initialize...")
        try:
            TelegramAppLibrary.initialize()
            print_success("initialize - SUCCESS")
            self.test_results["initialize"] = 'PASS'
        except Exception as e:
            print_error(f"initialize - EXCEPTION: {str(e)}")
            self.test_results["initialize"] = 'ERROR'

    def test_validate_connection(self):
        """Test credential validation."""
        print_section("VALIDATE CONNECTION")

        print(f"\n  Testing: validate_connection...")
        try:
            valid = TelegramAppLibrary.validate_connection(user_id=self.user_id)
            if valid:
                print_success("validate_connection - SUCCESS (credential found)")
                self.test_results["validate_connection"] = 'PASS'
            else:
                print_error("validate_connection - FAILED (no credential found)")
                self.test_results["validate_connection"] = 'FAIL'
        except Exception as e:
            print_error(f"validate_connection - EXCEPTION: {str(e)}")
            self.test_results["validate_connection"] = 'ERROR'

    def test_get_credentials(self):
        """Test credential retrieval."""
        print_section("GET CREDENTIALS")

        print(f"\n  Testing: get_credentials...")
        try:
            cred = TelegramAppLibrary.get_credentials(user_id=self.user_id)
            if cred:
                print_success("get_credentials - SUCCESS")
                print_info(f"Bot ID: {cred.bot_id}")
                print_info(f"Bot Username: {cred.bot_username}")
                print_info(f"Connection Type: {cred.connection_type}")
                print_info(f"Has Token: {bool(cred.bot_token)}")
                self.test_results["get_credentials"] = 'PASS'
            else:
                print_error("get_credentials - FAILED (no credential returned)")
                self.test_results["get_credentials"] = 'FAIL'
        except Exception as e:
            print_error(f"get_credentials - EXCEPTION: {str(e)}")
            self.test_results["get_credentials"] = 'ERROR'

    def test_get_bot_info(self):
        """Test getting bot information."""
        print_section("GET BOT INFO")

        result = self.run_test(
            "get_bot_info",
            TelegramAppLibrary.get_bot_info,
            user_id=self.user_id,
        )
        if result.get('status') == 'success':
            bot = result.get('bot', {})
            self.bot_user_id = bot.get('id')
            print_info(f"Bot Name: {bot.get('first_name', 'N/A')}")
            print_info(f"Bot Username: @{bot.get('username', 'N/A')}")
            print_info(f"Bot ID: {bot.get('id', 'N/A')}")
            print_info(f"Can Join Groups: {bot.get('can_join_groups', 'N/A')}")
            print_info(f"Supports Inline: {bot.get('supports_inline_queries', 'N/A')}")

    def test_get_updates(self):
        """Test getting bot updates."""
        print_section("GET UPDATES")

        result = self.run_test(
            "get_updates",
            TelegramAppLibrary.get_updates,
            user_id=self.user_id,
            limit=5,
        )
        if result.get('status') == 'success':
            updates = result.get('updates', [])
            print_info(f"Found {len(updates)} update(s)")
            if updates:
                latest = updates[-1]
                print_info(f"Latest update ID: {latest.get('update_id')}")
                msg = latest.get('message', {})
                if msg:
                    print_info(f"From: {msg.get('from', {}).get('first_name', 'N/A')}")
                    print_info(f"Text: {msg.get('text', '(no text)')[:80]}")

    def test_search_contact(self):
        """Test searching for contacts from bot update history."""
        print_section("SEARCH CONTACT")

        # Use a generic search term -- if there are any contacts, we'll find them
        result = self.run_test(
            "search_contact",
            TelegramAppLibrary.search_contact,
            user_id=self.user_id,
            name="a",  # Broad search to find any contact
        )
        if result.get('status') == 'success':
            contacts = result.get('contacts', [])
            print_info(f"Found {result.get('count', 0)} contact(s) matching 'a'")
            for c in contacts[:5]:
                print_info(f"  - {c.get('name', 'N/A')} (chat_id: {c.get('chat_id', 'N/A')})")

    def test_send_message(self):
        """Test sending a text message via Bot API."""
        print_section("SEND MESSAGE (Bot API)")

        if self.skip_send:
            print_skip("send_message - skipped (--skip-send)")
            self.test_results["send_message"] = 'SKIP'
            return

        if not self.chat_id:
            print_warning("send_message - skipped (no --chat-id provided)")
            self.test_results["send_message"] = 'SKIP'
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_text = f"[CraftOS Integration Test] Bot API send_message - {timestamp}"

        result = self.run_test(
            "send_message",
            TelegramAppLibrary.send_message,
            user_id=self.user_id,
            chat_id=self.chat_id,
            text=test_text,
        )
        if result.get('status') == 'success':
            msg = result.get('message', {})
            msg_id = msg.get('message_id')
            print_info(f"Message ID: {msg_id}")
            print_info(f"Chat ID: {msg.get('chat', {}).get('id')}")
            if msg_id:
                self.sent_message_ids.append(('bot', msg_id))

    def test_send_message_to_name(self):
        """Test sending a message by contact name resolution."""
        print_section("SEND MESSAGE TO NAME (Bot API)")

        if self.skip_send:
            print_skip("send_message_to_name - skipped (--skip-send)")
            self.test_results["send_message_to_name"] = 'SKIP'
            return

        if not self.chat_id:
            print_warning("send_message_to_name - skipped (no --chat-id; need contact history)")
            self.test_results["send_message_to_name"] = 'SKIP'
            return

        # First find a valid contact name from search_contact
        search_result = TelegramAppLibrary.search_contact(
            user_id=self.user_id,
            name="a",
        )
        contacts = search_result.get('contacts', [])
        if not contacts:
            print_warning("send_message_to_name - skipped (no contacts found to resolve name)")
            self.test_results["send_message_to_name"] = 'SKIP'
            return

        contact_name = contacts[0].get('name', '')
        if not contact_name:
            print_warning("send_message_to_name - skipped (first contact has no name)")
            self.test_results["send_message_to_name"] = 'SKIP'
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_text = f"[CraftOS Integration Test] send_message_to_name - {timestamp}"

        result = self.run_test(
            "send_message_to_name",
            TelegramAppLibrary.send_message_to_name,
            user_id=self.user_id,
            name=contact_name,
            text=test_text,
        )
        if result.get('status') == 'success':
            msg = result.get('message', {})
            resolved = result.get('resolved_contact', {})
            print_info(f"Resolved to: {resolved.get('name', 'N/A')} (chat_id: {resolved.get('chat_id', 'N/A')})")
            msg_id = msg.get('message_id')
            if msg_id:
                self.sent_message_ids.append(('bot', msg_id))

    def test_send_photo(self):
        """Test sending a photo via Bot API."""
        print_section("SEND PHOTO (Bot API)")

        if self.skip_send:
            print_skip("send_photo - skipped (--skip-send)")
            self.test_results["send_photo"] = 'SKIP'
            return

        if not self.chat_id:
            print_warning("send_photo - skipped (no --chat-id provided)")
            self.test_results["send_photo"] = 'SKIP'
            return

        # Use a small public image URL for testing
        photo_url = "https://via.placeholder.com/100x100.png?text=CraftOS+Test"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        result = self.run_test(
            "send_photo",
            TelegramAppLibrary.send_photo,
            user_id=self.user_id,
            chat_id=self.chat_id,
            photo=photo_url,
            caption=f"[CraftOS Integration Test] send_photo - {timestamp}",
        )
        if result.get('status') == 'success':
            msg = result.get('message', {})
            msg_id = msg.get('message_id')
            print_info(f"Message ID: {msg_id}")
            if msg_id:
                self.sent_message_ids.append(('bot', msg_id))

    def test_send_document(self):
        """Test sending a document via Bot API."""
        print_section("SEND DOCUMENT (Bot API)")

        if self.skip_send:
            print_skip("send_document - skipped (--skip-send)")
            self.test_results["send_document"] = 'SKIP'
            return

        if not self.chat_id:
            print_warning("send_document - skipped (no --chat-id provided)")
            self.test_results["send_document"] = 'SKIP'
            return

        # Use a small public file URL for testing
        doc_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        result = self.run_test(
            "send_document",
            TelegramAppLibrary.send_document,
            user_id=self.user_id,
            chat_id=self.chat_id,
            document=doc_url,
            caption=f"[CraftOS Integration Test] send_document - {timestamp}",
        )
        if result.get('status') == 'success':
            msg = result.get('message', {})
            msg_id = msg.get('message_id')
            print_info(f"Message ID: {msg_id}")
            if msg_id:
                self.sent_message_ids.append(('bot', msg_id))

    def test_get_chat(self):
        """Test getting chat information."""
        print_section("GET CHAT (Bot API)")

        if not self.chat_id:
            print_warning("get_chat - skipped (no --chat-id provided)")
            self.test_results["get_chat"] = 'SKIP'
            return

        result = self.run_test(
            "get_chat",
            TelegramAppLibrary.get_chat,
            user_id=self.user_id,
            chat_id=self.chat_id,
        )
        if result.get('status') == 'success':
            chat = result.get('chat', {})
            print_info(f"Chat Type: {chat.get('type', 'N/A')}")
            print_info(f"Chat Title/Name: {chat.get('title', chat.get('first_name', 'N/A'))}")
            print_info(f"Chat ID: {chat.get('id', 'N/A')}")

    def test_get_chat_member(self):
        """Test getting chat member information."""
        print_section("GET CHAT MEMBER (Bot API)")

        if not self.chat_id:
            print_warning("get_chat_member - skipped (no --chat-id provided)")
            self.test_results["get_chat_member"] = 'SKIP'
            return

        # Use the bot's own user ID if we have it, otherwise use the chat_id
        target_user = self.bot_user_id
        if not target_user:
            print_warning("get_chat_member - skipped (bot user ID not available; run get_bot_info first)")
            self.test_results["get_chat_member"] = 'SKIP'
            return

        result = self.run_test(
            "get_chat_member",
            TelegramAppLibrary.get_chat_member,
            user_id=self.user_id,
            chat_id=self.chat_id,
            target_user_id=target_user,
        )
        if result.get('status') == 'success':
            member = result.get('member', {})
            print_info(f"Status: {member.get('status', 'N/A')}")
            user = member.get('user', {})
            print_info(f"User: {user.get('first_name', 'N/A')} (@{user.get('username', 'N/A')})")

    def test_get_chat_members_count(self):
        """Test getting chat members count."""
        print_section("GET CHAT MEMBERS COUNT (Bot API)")

        if not self.chat_id:
            print_warning("get_chat_members_count - skipped (no --chat-id provided)")
            self.test_results["get_chat_members_count"] = 'SKIP'
            return

        result = self.run_test(
            "get_chat_members_count",
            TelegramAppLibrary.get_chat_members_count,
            user_id=self.user_id,
            chat_id=self.chat_id,
        )
        if result.get('status') == 'success':
            print_info(f"Member count: {result.get('count', 'N/A')}")

    def test_forward_message(self):
        """Test forwarding a message."""
        print_section("FORWARD MESSAGE (Bot API)")

        if self.skip_send:
            print_skip("forward_message - skipped (--skip-send)")
            self.test_results["forward_message"] = 'SKIP'
            return

        if not self.chat_id:
            print_warning("forward_message - skipped (no --chat-id provided)")
            self.test_results["forward_message"] = 'SKIP'
            return

        # We need a message ID to forward. Use one we sent earlier, or get from updates.
        source_message_id = None
        source_chat_id = self.chat_id

        # Try to use a message we sent earlier in this session
        bot_messages = [(t, mid) for t, mid in self.sent_message_ids if t == 'bot']
        if bot_messages:
            source_message_id = bot_messages[0][1]
        else:
            # Try to get a recent message from updates
            updates_result = TelegramAppLibrary.get_updates(
                user_id=self.user_id, limit=5
            )
            if updates_result.get('status') == 'success':
                updates = updates_result.get('updates', [])
                for u in reversed(updates):
                    msg = u.get('message', {})
                    if msg.get('message_id') and msg.get('chat', {}).get('id'):
                        source_message_id = msg['message_id']
                        source_chat_id = msg['chat']['id']
                        break

        if not source_message_id:
            print_warning("forward_message - skipped (no message available to forward)")
            self.test_results["forward_message"] = 'SKIP'
            return

        result = self.run_test(
            "forward_message",
            TelegramAppLibrary.forward_message,
            user_id=self.user_id,
            chat_id=self.chat_id,
            from_chat_id=source_chat_id,
            message_id=source_message_id,
        )
        if result.get('status') == 'success':
            msg = result.get('message', {})
            print_info(f"Forwarded Message ID: {msg.get('message_id', 'N/A')}")
            msg_id = msg.get('message_id')
            if msg_id:
                self.sent_message_ids.append(('bot', msg_id))

    # ==================================================================
    # MTPROTO (USER ACCOUNT) TESTS
    # ==================================================================

    def test_mtproto_validate_connection(self):
        """Test MTProto session validation."""
        print_section("MTPROTO VALIDATE CONNECTION")

        print(f"\n  Testing: validate_mtproto_connection...")
        try:
            valid = TelegramAppLibrary.validate_mtproto_connection(user_id=self.user_id)
            if valid:
                print_success("validate_mtproto_connection - SUCCESS (session found)")
                self.test_results["validate_mtproto_connection"] = 'PASS'
            else:
                print_warning("validate_mtproto_connection - No MTProto session found")
                self.test_results["validate_mtproto_connection"] = 'SKIP'
        except Exception as e:
            print_error(f"validate_mtproto_connection - EXCEPTION: {str(e)}")
            self.test_results["validate_mtproto_connection"] = 'ERROR'

    def _has_mtproto(self) -> bool:
        """Check if MTProto credentials are available."""
        try:
            return TelegramAppLibrary.validate_mtproto_connection(user_id=self.user_id)
        except Exception:
            return False

    def test_get_mtproto_account_info(self):
        """Test getting MTProto account info."""
        print_section("MTPROTO ACCOUNT INFO")

        if not self._has_mtproto():
            print_skip("get_mtproto_account_info - skipped (no MTProto session)")
            self.test_results["get_mtproto_account_info"] = 'SKIP'
            return

        result = self.run_test(
            "get_mtproto_account_info",
            TelegramAppLibrary.get_mtproto_account_info,
            user_id=self.user_id,
        )
        if result.get('status') == 'success':
            user = result.get('user', {})
            print_info(f"Name: {user.get('first_name', '')} {user.get('last_name', '')}")
            print_info(f"Username: @{user.get('username', 'N/A')}")
            print_info(f"Phone: {user.get('phone', 'N/A')}")
            print_info(f"User ID: {user.get('id', 'N/A')}")

    def test_get_telegram_chats(self):
        """Test getting MTProto dialogs/chats."""
        print_section("MTPROTO GET CHATS")

        if not self._has_mtproto():
            print_skip("get_telegram_chats - skipped (no MTProto session)")
            self.test_results["get_telegram_chats"] = 'SKIP'
            return

        result = self.run_test(
            "get_telegram_chats",
            TelegramAppLibrary.get_telegram_chats,
            user_id=self.user_id,
            limit=10,
        )
        if result.get('status') == 'success':
            chats = result.get('chats', [])
            print_info(f"Found {result.get('count', 0)} chat(s)")
            for c in chats[:5]:
                print_info(f"  - {c.get('name', c.get('title', 'N/A'))} (id: {c.get('id', 'N/A')}, type: {c.get('type', 'N/A')})")

    def test_read_telegram_messages(self):
        """Test reading messages via MTProto."""
        print_section("MTPROTO READ MESSAGES")

        if not self._has_mtproto():
            print_skip("read_telegram_messages - skipped (no MTProto session)")
            self.test_results["read_telegram_messages"] = 'SKIP'
            return

        # Use the provided chat_id, or try to find one from dialogs
        target_chat = self.chat_id
        if not target_chat:
            chats_result = TelegramAppLibrary.get_telegram_chats(
                user_id=self.user_id, limit=5
            )
            if chats_result.get('status') == 'success':
                chats = chats_result.get('chats', [])
                if chats:
                    target_chat = chats[0].get('id')
                    print_info(f"Using first dialog: {chats[0].get('name', 'N/A')} (id: {target_chat})")

        if not target_chat:
            print_warning("read_telegram_messages - skipped (no chat available)")
            self.test_results["read_telegram_messages"] = 'SKIP'
            return

        result = self.run_test(
            "read_telegram_messages",
            TelegramAppLibrary.read_telegram_messages,
            user_id=self.user_id,
            chat_id=target_chat,
            limit=5,
        )
        if result.get('status') == 'success':
            messages = result.get('messages', [])
            chat_info = result.get('chat', {})
            print_info(f"Chat: {chat_info.get('name', chat_info.get('title', 'N/A'))}")
            print_info(f"Messages retrieved: {result.get('count', 0)}")
            for m in messages[:3]:
                sender = m.get('sender', m.get('from', 'Unknown'))
                text = m.get('text', '(no text)')
                print_info(f"  - [{sender}] {str(text)[:80]}")

    def test_search_mtproto_contacts(self):
        """Test searching contacts via MTProto."""
        print_section("MTPROTO SEARCH CONTACTS")

        if not self._has_mtproto():
            print_skip("search_mtproto_contacts - skipped (no MTProto session)")
            self.test_results["search_mtproto_contacts"] = 'SKIP'
            return

        result = self.run_test(
            "search_mtproto_contacts",
            TelegramAppLibrary.search_mtproto_contacts,
            user_id=self.user_id,
            query="a",  # Broad search
            limit=10,
        )
        if result.get('status') == 'success':
            contacts = result.get('contacts', [])
            print_info(f"Found {result.get('count', 0)} contact(s) matching 'a'")
            for c in contacts[:5]:
                name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                print_info(f"  - {name or 'N/A'} (id: {c.get('id', 'N/A')}, username: @{c.get('username', 'N/A')})")

    def test_send_mtproto_message(self):
        """Test sending a message via MTProto."""
        print_section("MTPROTO SEND MESSAGE")

        if self.skip_send:
            print_skip("send_mtproto_message - skipped (--skip-send)")
            self.test_results["send_mtproto_message"] = 'SKIP'
            return

        if not self._has_mtproto():
            print_skip("send_mtproto_message - skipped (no MTProto session)")
            self.test_results["send_mtproto_message"] = 'SKIP'
            return

        if not self.chat_id:
            print_warning("send_mtproto_message - skipped (no --chat-id provided)")
            self.test_results["send_mtproto_message"] = 'SKIP'
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_text = f"[CraftOS Integration Test] MTProto send_message - {timestamp}"

        result = self.run_test(
            "send_mtproto_message",
            TelegramAppLibrary.send_mtproto_message,
            user_id=self.user_id,
            chat_id=self.chat_id,
            text=test_text,
        )
        if result.get('status') == 'success':
            print_info(f"Message ID: {result.get('message_id', 'N/A')}")
            print_info(f"Chat ID: {result.get('chat_id', 'N/A')}")
            print_info(f"Date: {result.get('date', 'N/A')}")
            msg_id = result.get('message_id')
            if msg_id:
                self.sent_message_ids.append(('mtproto', msg_id))

    # ==================================================================
    # TEST GROUP RUNNERS
    # ==================================================================

    def test_bot_readonly(self):
        """Run all read-only Bot API tests."""
        self.test_initialize()
        self.test_validate_connection()
        self.test_get_credentials()
        self.test_get_bot_info()
        self.test_get_updates()
        self.test_search_contact()
        self.test_get_chat()
        self.test_get_chat_member()
        self.test_get_chat_members_count()

    def test_bot_send(self):
        """Run all Bot API send/write tests."""
        self.test_send_message()
        self.test_send_photo()
        self.test_send_document()
        self.test_send_message_to_name()
        self.test_forward_message()

    def test_mtproto_readonly(self):
        """Run all read-only MTProto tests."""
        self.test_mtproto_validate_connection()
        self.test_get_mtproto_account_info()
        self.test_get_telegram_chats()
        self.test_read_telegram_messages()
        self.test_search_mtproto_contacts()

    def test_mtproto_send(self):
        """Run MTProto send tests."""
        self.test_send_mtproto_message()

    def test_all(self):
        """Run all tests."""
        # Bot API read-only
        self.test_bot_readonly()
        # Bot API send
        self.test_bot_send()
        # MTProto read-only
        self.test_mtproto_readonly()
        # MTProto send
        self.test_mtproto_send()

    # ==================================================================
    # CLEANUP
    # ==================================================================

    def cleanup(self):
        """Clean up test artifacts (informational only -- Telegram does not expose delete for bots easily)."""
        print_section("CLEANUP")

        if self.sent_message_ids:
            print_info(f"Sent {len(self.sent_message_ids)} test message(s) during this run:")
            for api_type, msg_id in self.sent_message_ids:
                print_info(f"  - [{api_type}] message_id={msg_id}")
            print_info("Note: Telegram Bot API does not support bulk message deletion.")
            print_info("Test messages are tagged with '[CraftOS Integration Test]' for easy identification.")
        else:
            print_info("No test messages were sent (nothing to clean up).")

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def print_summary(self):
        """Print test summary with color-coded results."""
        print_header("TEST SUMMARY")

        passed = sum(1 for v in self.test_results.values() if v == 'PASS')
        failed = sum(1 for v in self.test_results.values() if v == 'FAIL')
        errors = sum(1 for v in self.test_results.values() if v == 'ERROR')
        skipped = sum(1 for v in self.test_results.values() if v == 'SKIP')
        total = len(self.test_results)

        print(f"\n  Total tests: {total}")
        print(f"  {Colors.GREEN}Passed:  {passed}{Colors.END}")
        print(f"  {Colors.RED}Failed:  {failed}{Colors.END}")
        print(f"  {Colors.YELLOW}Errors:  {errors}{Colors.END}")
        print(f"  {Colors.MAGENTA}Skipped: {skipped}{Colors.END}")

        print(f"\n  {Colors.BOLD}Detailed Results:{Colors.END}")
        for name, result in self.test_results.items():
            if result == 'PASS':
                print(f"    {Colors.GREEN}[PASS]{Colors.END}  {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}[FAIL]{Colors.END}  {name}")
            elif result == 'ERROR':
                print(f"    {Colors.YELLOW}[ERR] {Colors.END}  {name}")
            elif result == 'SKIP':
                print(f"    {Colors.MAGENTA}[SKIP]{Colors.END}  {name}")

        # Overall verdict
        print()
        if failed == 0 and errors == 0:
            print(f"  {Colors.BOLD}{Colors.GREEN}ALL EXECUTED TESTS PASSED{Colors.END}")
        else:
            print(f"  {Colors.BOLD}{Colors.RED}{failed + errors} TEST(S) FAILED OR ERRORED{Colors.END}")


def list_credentials():
    """List all stored Telegram credentials (Bot API and MTProto)."""
    print_header("STORED TELEGRAM CREDENTIALS")

    TelegramAppLibrary.initialize()
    cred_store = TelegramAppLibrary.get_credential_store()

    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No Telegram credentials found.")
        print_info("Please authenticate via the CraftOS control panel first.")
        return None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    bot_creds = [c for c in all_credentials if c.connection_type == "bot_api"]
    mtproto_creds = [c for c in all_credentials if c.connection_type == "mtproto"]

    if bot_creds:
        print(f"  {Colors.BOLD}Bot API Credentials:{Colors.END}")
        for i, cred in enumerate(bot_creds, 1):
            print(f"    [{i}] User ID:      {cred.user_id}")
            print(f"        Bot ID:       {cred.bot_id}")
            print(f"        Bot Username: @{cred.bot_username}")
            print(f"        Has Token:    {bool(cred.bot_token)}")
            print()

    if mtproto_creds:
        print(f"  {Colors.BOLD}MTProto (User Account) Credentials:{Colors.END}")
        for i, cred in enumerate(mtproto_creds, 1):
            print(f"    [{i}] User ID:        {cred.user_id}")
            print(f"        Phone Number:    {cred.phone_number}")
            print(f"        Account Name:    {cred.account_name}")
            print(f"        Telegram User:   {cred.telegram_user_id}")
            print(f"        Has Session:     {bool(cred.session_string)}")
            print(f"        API ID:          {cred.api_id}")
            print()

    return all_credentials[0].user_id


def main():
    parser = argparse.ArgumentParser(
        description='Integration test suite for Telegram API (Bot API + MTProto)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test groups (--only):
  bot        All Bot API tests (read-only + send)
  bot-read   Bot API read-only tests (no messages sent)
  send       Bot API send tests only (send_message, send_photo, etc.)
  mtproto    All MTProto tests (read-only + send)
  mtproto-read  MTProto read-only tests
  mtproto-send  MTProto send tests only
  all        Run everything (default)

Examples:
  python test_telegram_library.py --list
  python test_telegram_library.py --user-id myuser --chat-id 123456789
  python test_telegram_library.py --only bot-read
  python test_telegram_library.py --only send --chat-id 123456789 --skip-send
  python test_telegram_library.py --only mtproto --skip-send
        """
    )
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--chat-id', type=str, help='Target chat ID for send tests and chat info tests')
    parser.add_argument('--list', action='store_true', help='List stored Telegram credentials')
    parser.add_argument('--skip-send', action='store_true', help='Skip tests that send messages')
    parser.add_argument(
        '--only', type=str,
        choices=['bot', 'bot-read', 'send', 'mtproto', 'mtproto-read', 'mtproto-send', 'all'],
        default='all',
        help='Only run a specific test group'
    )
    args = parser.parse_args()

    print_header("TELEGRAM EXTERNAL LIBRARY INTEGRATION TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Test group: {args.only}")
    print(f"  Skip send: {args.skip_send}")

    # Initialize the library
    TelegramAppLibrary.initialize()
    print_success("TelegramAppLibrary initialized")

    # List credentials if requested
    if args.list:
        list_credentials()
        return

    # Get credentials
    user_id = args.user_id

    if not user_id:
        print_section("CREDENTIAL LOOKUP")
        user_id = list_credentials()

        if not user_id:
            print_error("No credentials available. Exiting.")
            return

        print_info(f"Using: user_id={user_id}")

    # Quick validation
    has_bot = TelegramAppLibrary.validate_connection(user_id=user_id)
    has_mtproto = False
    try:
        has_mtproto = TelegramAppLibrary.validate_mtproto_connection(user_id=user_id)
    except Exception:
        pass

    print_info(f"Bot API credentials:   {'found' if has_bot else 'NOT FOUND'}")
    print_info(f"MTProto credentials:   {'found' if has_mtproto else 'NOT FOUND'}")

    if not has_bot and not has_mtproto:
        print_error("No valid Telegram credentials found for this user. Exiting.")
        return

    if args.chat_id:
        print_info(f"Target chat ID:        {args.chat_id}")

    # Create tester
    tester = TelegramTester(
        user_id=user_id,
        chat_id=args.chat_id,
        skip_send=args.skip_send,
    )

    try:
        if args.only == 'all':
            tester.test_all()
        elif args.only == 'bot':
            tester.test_bot_readonly()
            tester.test_bot_send()
        elif args.only == 'bot-read':
            tester.test_bot_readonly()
        elif args.only == 'send':
            # Need initialization and bot info first for some send tests
            tester.test_initialize()
            tester.test_get_bot_info()
            tester.test_bot_send()
        elif args.only == 'mtproto':
            tester.test_initialize()
            tester.test_mtproto_readonly()
            tester.test_mtproto_send()
        elif args.only == 'mtproto-read':
            tester.test_initialize()
            tester.test_mtproto_readonly()
        elif args.only == 'mtproto-send':
            tester.test_initialize()
            tester.test_mtproto_send()

    finally:
        tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
