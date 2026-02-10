"""
Comprehensive integration test script for Slack external library.

This script tests ALL Slack API methods using stored credentials.
Run this to verify Slack integration without going through the agent cycle.

Usage:
    python test_slack_library.py [--user-id YOUR_USER_ID] [--workspace-id YOUR_WORKSPACE_ID]

If no arguments provided, it will use defaults or prompt you.
"""
import sys
import argparse
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.slack.external_app_library import SlackAppLibrary

# ANSI colors for output
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
    print(f"{Colors.GREEN}  PASS  {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}  FAIL  {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}  WARN  {text}{Colors.END}")


def print_info(text: str):
    """Print info message."""
    print(f"  {text}")


def print_result(result: Dict[str, Any], indent: int = 2):
    """Pretty print a result dict."""
    formatted = json.dumps(result, indent=indent, default=str)
    for line in formatted.split('\n')[:30]:  # Limit output
        print(f"  {line}")
    if len(formatted.split('\n')) > 30:
        print(f"  ... (output truncated)")


def _archive_channel(bot_token: str, channel_id: str) -> Dict[str, Any]:
    """Archive a Slack channel (direct API call for cleanup)."""
    url = "https://slack.com/api/conversations.archive"
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }
    payload = {"channel": channel_id}
    response = requests.post(url, headers=headers, json=payload)
    return response.json()


def _delete_message(bot_token: str, channel: str, ts: str) -> Dict[str, Any]:
    """Delete a Slack message (direct API call for cleanup)."""
    url = "https://slack.com/api/chat.delete"
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }
    payload = {"channel": channel, "ts": ts}
    response = requests.post(url, headers=headers, json=payload)
    return response.json()


class SlackTester:
    """Test runner for Slack API methods."""

    def __init__(self, user_id: str, workspace_id: Optional[str] = None, skip_send: bool = False):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.skip_send = skip_send
        self.test_results = {}

        # Track resources for cleanup
        self.created_channel_id = None
        self.sent_message_ts = None
        self.sent_message_channel = None
        self.uploaded_file_channel = None
        self.bot_token = None  # populated during get_credentials test

        # Discovered resources for downstream tests
        self.discovered_channel_id = None
        self.discovered_user_id = None

    def run_test(self, test_name: str, func, *args, **kwargs) -> Dict[str, Any]:
        """Run a single test and record result."""
        print(f"\n  Testing: {test_name}...")
        try:
            result = func(*args, **kwargs)
            status = result.get('status', 'unknown')

            if status == 'success':
                print_success(f"{test_name}")
                self.test_results[test_name] = 'PASS'
            else:
                reason = result.get('reason', result.get('details', 'Unknown error'))
                print_error(f"{test_name} - {reason}")
                self.test_results[test_name] = 'FAIL'

            return result
        except Exception as e:
            print_error(f"{test_name} - EXCEPTION: {str(e)}")
            self.test_results[test_name] = 'ERROR'
            return {"status": "error", "reason": str(e)}

    # ------------------------------------------------------------------
    # Initialization & Credentials
    # ------------------------------------------------------------------
    def test_initialization(self):
        """Test initialize, validate_connection, and get_credentials."""
        print_section("INITIALIZATION & CREDENTIALS")

        # Test initialize (already called, but verify state)
        print(f"\n  Testing: initialize...")
        try:
            SlackAppLibrary.initialize()
            if SlackAppLibrary._initialized and SlackAppLibrary._credential_store is not None:
                print_success("initialize")
                self.test_results["initialize"] = 'PASS'
            else:
                print_error("initialize - library not properly initialized")
                self.test_results["initialize"] = 'FAIL'
        except Exception as e:
            print_error(f"initialize - EXCEPTION: {str(e)}")
            self.test_results["initialize"] = 'ERROR'

        # Test validate_connection
        print(f"\n  Testing: validate_connection...")
        try:
            is_valid = SlackAppLibrary.validate_connection(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
            )
            if is_valid:
                print_success("validate_connection")
                self.test_results["validate_connection"] = 'PASS'
            else:
                print_error("validate_connection - no valid credential found")
                self.test_results["validate_connection"] = 'FAIL'
        except Exception as e:
            print_error(f"validate_connection - EXCEPTION: {str(e)}")
            self.test_results["validate_connection"] = 'ERROR'

        # Test get_credentials
        print(f"\n  Testing: get_credentials...")
        try:
            cred = SlackAppLibrary.get_credentials(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
            )
            if cred is not None:
                self.bot_token = cred.bot_token
                print_success("get_credentials")
                print_info(f"Workspace: {cred.workspace_name} ({cred.workspace_id})")
                print_info(f"Team ID: {cred.team_id}")
                print_info(f"Bot token: {cred.bot_token[:12]}...{cred.bot_token[-4:]}")
                self.test_results["get_credentials"] = 'PASS'
            else:
                print_error("get_credentials - returned None")
                self.test_results["get_credentials"] = 'FAIL'
        except Exception as e:
            print_error(f"get_credentials - EXCEPTION: {str(e)}")
            self.test_results["get_credentials"] = 'ERROR'

    # ------------------------------------------------------------------
    # Channel Operations (read-only)
    # ------------------------------------------------------------------
    def test_channel_operations(self):
        """Test list_channels, get_channel_info, get_channel_history."""
        print_section("CHANNEL OPERATIONS")

        # Test list_channels
        result = self.run_test(
            "list_channels",
            SlackAppLibrary.list_channels,
            user_id=self.user_id,
            types="public_channel,private_channel",
            limit=20,
            workspace_id=self.workspace_id,
        )

        if result.get('status') == 'success':
            channels = result.get('channels', [])
            print_info(f"Found {len(channels)} channels")
            for ch in channels[:5]:
                print_info(f"  #{ch.get('name', 'N/A')} (ID: {ch.get('id', 'N/A')})")

            # Pick the first channel for downstream tests
            if channels:
                self.discovered_channel_id = channels[0].get('id')
                print_info(f"Using channel for further tests: {self.discovered_channel_id}")

        # Test get_channel_info (requires a channel ID)
        if self.discovered_channel_id:
            result = self.run_test(
                "get_channel_info",
                SlackAppLibrary.get_channel_info,
                user_id=self.user_id,
                channel=self.discovered_channel_id,
                workspace_id=self.workspace_id,
            )
            if result.get('status') == 'success':
                ch = result.get('channel', {})
                print_info(f"Channel name: #{ch.get('name', 'N/A')}")
                print_info(f"Members: {ch.get('num_members', 'N/A')}")
                topic = ch.get('topic', {}).get('value', '')
                if topic:
                    print_info(f"Topic: {topic}")
        else:
            print_warning("No channel ID available, skipping get_channel_info")
            self.test_results["get_channel_info"] = 'SKIP'

        # Test get_channel_history
        if self.discovered_channel_id:
            result = self.run_test(
                "get_channel_history",
                SlackAppLibrary.get_channel_history,
                user_id=self.user_id,
                channel=self.discovered_channel_id,
                limit=5,
                workspace_id=self.workspace_id,
            )
            if result.get('status') == 'success':
                messages = result.get('messages', [])
                print_info(f"Retrieved {len(messages)} messages")
                for msg in messages[:3]:
                    text = msg.get('text', '')[:80]
                    print_info(f"  [{msg.get('user', 'bot')}] {text}")
        else:
            print_warning("No channel ID available, skipping get_channel_history")
            self.test_results["get_channel_history"] = 'SKIP'

    # ------------------------------------------------------------------
    # User Operations
    # ------------------------------------------------------------------
    def test_user_operations(self):
        """Test list_users and get_user_info."""
        print_section("USER OPERATIONS")

        # Test list_users
        result = self.run_test(
            "list_users",
            SlackAppLibrary.list_users,
            user_id=self.user_id,
            limit=20,
            workspace_id=self.workspace_id,
        )

        if result.get('status') == 'success':
            users = result.get('users', [])
            print_info(f"Found {len(users)} users")
            # Find a real (non-bot, non-slackbot) user for downstream tests
            for u in users:
                if not u.get('is_bot') and u.get('id') != 'USLACKBOT' and not u.get('deleted'):
                    self.discovered_user_id = u.get('id')
                    break
            for u in users[:5]:
                name = u.get('real_name', u.get('name', 'N/A'))
                print_info(f"  {name} (ID: {u.get('id', 'N/A')}, bot: {u.get('is_bot', False)})")
            if self.discovered_user_id:
                print_info(f"Using user for further tests: {self.discovered_user_id}")

        # Test get_user_info
        if self.discovered_user_id:
            result = self.run_test(
                "get_user_info",
                SlackAppLibrary.get_user_info,
                user_id=self.user_id,
                slack_user_id=self.discovered_user_id,
                workspace_id=self.workspace_id,
            )
            if result.get('status') == 'success':
                user = result.get('user', {})
                print_info(f"Name: {user.get('real_name', 'N/A')}")
                print_info(f"Display: {user.get('profile', {}).get('display_name', 'N/A')}")
                print_info(f"Email: {user.get('profile', {}).get('email', 'N/A')}")
                print_info(f"Timezone: {user.get('tz', 'N/A')}")
        else:
            print_warning("No user ID available, skipping get_user_info")
            self.test_results["get_user_info"] = 'SKIP'

    # ------------------------------------------------------------------
    # Messaging Operations (may send real messages)
    # ------------------------------------------------------------------
    def test_messaging_operations(self):
        """Test send_message and open_dm."""
        print_section("MESSAGING OPERATIONS")

        if self.skip_send:
            print_warning("--skip-send is set: skipping send_message")
            self.test_results["send_message"] = 'SKIP'
        elif not self.discovered_channel_id:
            print_warning("No channel ID available, skipping send_message")
            self.test_results["send_message"] = 'SKIP'
        else:
            # Test send_message
            test_text = f"[CraftOS Integration Test] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - This message will be deleted shortly."
            result = self.run_test(
                "send_message",
                SlackAppLibrary.send_message,
                user_id=self.user_id,
                channel=self.discovered_channel_id,
                text=test_text,
                workspace_id=self.workspace_id,
            )
            if result.get('status') == 'success':
                msg = result.get('message', {})
                self.sent_message_ts = msg.get('ts')
                self.sent_message_channel = msg.get('channel', self.discovered_channel_id)
                print_info(f"Message ts: {self.sent_message_ts}")
                print_info(f"Channel: {self.sent_message_channel}")

        # Test open_dm (requires a real user ID)
        if self.discovered_user_id:
            result = self.run_test(
                "open_dm",
                SlackAppLibrary.open_dm,
                user_id=self.user_id,
                users=[self.discovered_user_id],
                workspace_id=self.workspace_id,
            )
            if result.get('status') == 'success':
                dm_channel = result.get('channel', {})
                dm_id = dm_channel.get('id', 'N/A') if isinstance(dm_channel, dict) else dm_channel
                print_info(f"DM channel ID: {dm_id}")
        else:
            print_warning("No user ID available, skipping open_dm")
            self.test_results["open_dm"] = 'SKIP'

    # ------------------------------------------------------------------
    # Search Operations
    # ------------------------------------------------------------------
    def test_search_operations(self):
        """Test search_messages."""
        print_section("SEARCH OPERATIONS")

        # Note: search_messages often requires a user token (xoxp-), not bot token
        result = self.run_test(
            "search_messages",
            SlackAppLibrary.search_messages,
            user_id=self.user_id,
            query="hello",
            count=5,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            messages = result.get('messages', {})
            total = messages.get('total', 0) if isinstance(messages, dict) else 0
            print_info(f"Search returned {total} total matches")
            matches = messages.get('matches', []) if isinstance(messages, dict) else []
            for m in matches[:3]:
                text = m.get('text', '')[:80]
                ch_name = m.get('channel', {}).get('name', 'N/A') if isinstance(m.get('channel'), dict) else 'N/A'
                print_info(f"  [#{ch_name}] {text}")

    # ------------------------------------------------------------------
    # Channel Creation & Invite (mutating)
    # ------------------------------------------------------------------
    def test_channel_creation(self):
        """Test create_channel and invite_to_channel."""
        print_section("CHANNEL CREATION & INVITE")

        if self.skip_send:
            print_warning("--skip-send is set: skipping create_channel")
            self.test_results["create_channel"] = 'SKIP'
            self.test_results["invite_to_channel"] = 'SKIP'
            return

        # Test create_channel
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        channel_name = f"craftos-test-{timestamp}"
        result = self.run_test(
            "create_channel",
            SlackAppLibrary.create_channel,
            user_id=self.user_id,
            name=channel_name,
            is_private=False,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            ch = result.get('channel', {})
            self.created_channel_id = ch.get('id')
            print_info(f"Created channel: #{ch.get('name', 'N/A')} (ID: {self.created_channel_id})")
        else:
            print_info("Could not create channel; skipping invite_to_channel")
            self.test_results["invite_to_channel"] = 'SKIP'
            return

        # Test invite_to_channel
        if self.created_channel_id and self.discovered_user_id:
            result = self.run_test(
                "invite_to_channel",
                SlackAppLibrary.invite_to_channel,
                user_id=self.user_id,
                channel=self.created_channel_id,
                users=[self.discovered_user_id],
                workspace_id=self.workspace_id,
            )
            if result.get('status') == 'success':
                print_info(f"Invited {self.discovered_user_id} to {self.created_channel_id}")
        elif not self.discovered_user_id:
            print_warning("No user ID available, skipping invite_to_channel")
            self.test_results["invite_to_channel"] = 'SKIP'

    # ------------------------------------------------------------------
    # File Upload (mutating)
    # ------------------------------------------------------------------
    def test_file_upload(self):
        """Test upload_file."""
        print_section("FILE UPLOAD")

        if self.skip_send:
            print_warning("--skip-send is set: skipping upload_file")
            self.test_results["upload_file"] = 'SKIP'
            return

        target_channel = self.created_channel_id or self.discovered_channel_id
        if not target_channel:
            print_warning("No channel available, skipping upload_file")
            self.test_results["upload_file"] = 'SKIP'
            return

        self.uploaded_file_channel = target_channel
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = self.run_test(
            "upload_file",
            SlackAppLibrary.upload_file,
            user_id=self.user_id,
            channels=[target_channel],
            content=f"CraftOS Slack integration test file\nGenerated at: {timestamp}\nThis file can be safely deleted.",
            filename="craftos_test.txt",
            title="CraftOS Integration Test File",
            initial_comment="[Test] Automated upload - will be cleaned up.",
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            f = result.get('file', {})
            if f:
                print_info(f"File ID: {f.get('id', 'N/A')}")
                print_info(f"File name: {f.get('name', 'N/A')}")
                print_info(f"Size: {f.get('size', 'N/A')} bytes")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self):
        """Clean up test artifacts."""
        print_section("CLEANUP")

        if not self.bot_token:
            print_info("No bot token available, skipping cleanup")
            return

        # Delete the test message
        if self.sent_message_ts and self.sent_message_channel:
            print_info(f"Deleting test message {self.sent_message_ts} from {self.sent_message_channel}")
            resp = _delete_message(self.bot_token, self.sent_message_channel, self.sent_message_ts)
            if resp.get('ok'):
                print_success("Test message deleted")
            else:
                print_warning(f"Could not delete test message: {resp.get('error', 'unknown')}")

        # Archive the test channel
        if self.created_channel_id:
            print_info(f"Archiving test channel {self.created_channel_id}")
            resp = _archive_channel(self.bot_token, self.created_channel_id)
            if resp.get('ok'):
                print_success("Test channel archived")
            else:
                print_warning(f"Could not archive test channel: {resp.get('error', 'unknown')}")

        if not self.sent_message_ts and not self.created_channel_id:
            print_info("No test artifacts to clean up")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def print_summary(self):
        """Print test summary."""
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
        print(f"  {Colors.CYAN}Skipped: {skipped}{Colors.END}")

        print(f"\n  {Colors.BOLD}Detailed Results:{Colors.END}")
        for name, result in self.test_results.items():
            if result == 'PASS':
                print(f"    {Colors.GREEN}PASS{Colors.END}  {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}FAIL{Colors.END}  {name}")
            elif result == 'SKIP':
                print(f"    {Colors.CYAN}SKIP{Colors.END}  {name}")
            else:
                print(f"    {Colors.YELLOW}ERR {Colors.END}  {name}")


def list_credentials():
    """List all stored Slack credentials."""
    print_header("STORED SLACK CREDENTIALS")

    SlackAppLibrary.initialize()
    cred_store = SlackAppLibrary.get_credential_store()

    # Access internal credentials dict to list all users
    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No Slack credentials found.")
        print_info("Please authenticate via the CraftOS control panel first.")
        return None, None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    for i, cred in enumerate(all_credentials, 1):
        print(f"  [{i}] User ID:        {cred.user_id}")
        print(f"      Workspace ID:   {cred.workspace_id}")
        print(f"      Workspace Name: {cred.workspace_name}")
        print(f"      Team ID:        {cred.team_id}")
        print(f"      App ID:         {cred.app_id or '(none)'}")
        print(f"      Bot Token:      {cred.bot_token[:12]}...{cred.bot_token[-4:]}")
        print()

    return all_credentials[0].user_id, all_credentials[0].workspace_id


def main():
    parser = argparse.ArgumentParser(description='Test Slack API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--workspace-id', type=str, help='Slack workspace ID')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--skip-send', action='store_true', help='Skip tests that send messages, create channels, or upload files')
    parser.add_argument('--only', type=str, help='Only run specific test group (init, channel, user, message, search, create, upload)')
    args = parser.parse_args()

    print_header("SLACK EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    SlackAppLibrary.initialize()
    print_success("SlackAppLibrary initialized")

    # List credentials if requested
    if args.list:
        list_credentials()
        return

    # Get credentials
    user_id = args.user_id
    workspace_id = args.workspace_id

    if not user_id:
        print_section("CREDENTIAL LOOKUP")
        user_id, workspace_id = list_credentials()

        if not user_id:
            print_error("No credentials available. Exiting.")
            return

        print_info(f"Using: user_id={user_id}")
        print_info(f"       workspace_id={workspace_id}")

    # Validate connection
    if not SlackAppLibrary.validate_connection(user_id=user_id, workspace_id=workspace_id):
        print_error("Invalid credentials or no connection found.")
        return

    print_success("Credential validation passed")

    # Create tester
    tester = SlackTester(user_id=user_id, workspace_id=workspace_id, skip_send=args.skip_send)

    try:
        # Run tests based on --only flag or all
        test_groups = {
            'init': tester.test_initialization,
            'channel': tester.test_channel_operations,
            'user': tester.test_user_operations,
            'message': tester.test_messaging_operations,
            'search': tester.test_search_operations,
            'create': tester.test_channel_creation,
            'upload': tester.test_file_upload,
        }

        if args.only:
            if args.only in test_groups:
                # Always run init first so we have credentials and discovered IDs
                if args.only != 'init':
                    tester.test_initialization()
                    # For tests that need channel/user IDs, discover them first
                    if args.only in ('message', 'search', 'create', 'upload'):
                        tester.test_channel_operations()
                    if args.only in ('message', 'create'):
                        tester.test_user_operations()
                test_groups[args.only]()
            else:
                print_error(f"Unknown test group: {args.only}")
                print_info("Available: init, channel, user, message, search, create, upload")
                return
        else:
            # Run all tests in logical order
            tester.test_initialization()
            tester.test_channel_operations()
            tester.test_user_operations()
            tester.test_messaging_operations()
            tester.test_search_operations()
            tester.test_channel_creation()
            tester.test_file_upload()

    finally:
        # Cleanup created resources
        if not args.skip_send:
            tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
