"""
Comprehensive integration test script for WhatsApp external library.

This script tests ALL WhatsApp Web API methods using stored credentials.
Run this to verify WhatsApp Web integration without going through the agent cycle.

Usage:
    python test_whatsapp_library.py [--user-id YOUR_USER_ID] [--phone-number-id YOUR_PHONE_ID]
    python test_whatsapp_library.py --list
    python test_whatsapp_library.py --only session
    python test_whatsapp_library.py --skip-send

If no arguments provided, it will use the first stored credential found.
"""
import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.whatsapp.external_app_library import WhatsAppAppLibrary


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


def print_result(result: Dict[str, Any], indent: int = 2):
    """Pretty print a result dict."""
    formatted = json.dumps(result, indent=indent, default=str)
    for line in formatted.split('\n')[:30]:  # Limit output
        print(f"  {line}")
    if len(formatted.split('\n')) > 30:
        print(f"  ... (output truncated)")


class WhatsAppTester:
    """Test runner for WhatsApp Web API methods."""

    def __init__(self, user_id: str, phone_number_id: Optional[str] = None):
        self.user_id = user_id
        self.phone_number_id = phone_number_id
        self.test_results = {}

    def run_test(self, test_name: str, func, *args, **kwargs) -> Dict[str, Any]:
        """Run a single test and record result."""
        print(f"\n  Testing: {test_name}...")
        try:
            result = func(*args, **kwargs)

            if not isinstance(result, dict):
                print_error(f"{test_name} - returned non-dict: {type(result)}")
                self.test_results[test_name] = 'FAIL'
                return {"status": "error", "reason": f"Non-dict return: {result}"}

            status = result.get('status', 'unknown')

            if status == 'success':
                print_success(f"{test_name} - SUCCESS")
                self.test_results[test_name] = 'PASS'
            elif result.get('success') is True:
                # Some methods (reconnect) return {"success": True} instead of {"status": "success"}
                print_success(f"{test_name} - SUCCESS")
                self.test_results[test_name] = 'PASS'
            else:
                reason = result.get('reason', result.get('error', result.get('message', 'Unknown error')))
                print_error(f"{test_name} - FAILED: {reason}")
                self.test_results[test_name] = 'FAIL'

            return result
        except Exception as e:
            print_error(f"{test_name} - EXCEPTION: {str(e)}")
            self.test_results[test_name] = 'ERROR'
            return {"status": "error", "reason": str(e)}

    # ------------------------------------------------------------------
    # Initialization & Credential Tests
    # ------------------------------------------------------------------
    def test_initialization(self):
        """Test library initialization and credential access."""
        print_section("INITIALIZATION & CREDENTIALS")

        # Test initialize (already called, but verify idempotent)
        print(f"\n  Testing: initialize (idempotent)...")
        try:
            WhatsAppAppLibrary.initialize()
            assert WhatsAppAppLibrary._initialized is True
            assert WhatsAppAppLibrary._credential_store is not None
            print_success("initialize (idempotent) - SUCCESS")
            self.test_results["initialize"] = 'PASS'
        except Exception as e:
            print_error(f"initialize (idempotent) - EXCEPTION: {e}")
            self.test_results["initialize"] = 'ERROR'

        # Test validate_connection
        print(f"\n  Testing: validate_connection...")
        try:
            is_valid = WhatsAppAppLibrary.validate_connection(
                user_id=self.user_id,
                phone_number_id=self.phone_number_id,
            )
            if is_valid:
                print_success("validate_connection - SUCCESS (credential found)")
                self.test_results["validate_connection"] = 'PASS'
            else:
                print_error("validate_connection - FAILED (no credential found)")
                self.test_results["validate_connection"] = 'FAIL'
        except Exception as e:
            print_error(f"validate_connection - EXCEPTION: {e}")
            self.test_results["validate_connection"] = 'ERROR'

        # Test get_credentials
        print(f"\n  Testing: get_credentials...")
        try:
            cred = WhatsAppAppLibrary.get_credentials(
                user_id=self.user_id,
                phone_number_id=self.phone_number_id,
            )
            if cred is not None:
                print_success("get_credentials - SUCCESS")
                print_info(f"User ID:        {cred.user_id}")
                print_info(f"Phone Number ID: {cred.phone_number_id}")
                print_info(f"Session ID:      {cred.session_id}")
                print_info(f"JID:             {cred.jid}")
                print_info(f"Display Phone:   {cred.display_phone_number}")
                self.test_results["get_credentials"] = 'PASS'
            else:
                print_error("get_credentials - FAILED (returned None)")
                self.test_results["get_credentials"] = 'FAIL'
        except Exception as e:
            print_error(f"get_credentials - EXCEPTION: {e}")
            self.test_results["get_credentials"] = 'ERROR'

    # ------------------------------------------------------------------
    # Session Management Tests
    # ------------------------------------------------------------------
    def test_session_operations(self):
        """Test WhatsApp Web session management methods."""
        print_section("SESSION MANAGEMENT")

        # Test list_persisted_sessions (no user filter)
        result = self.run_test(
            "list_persisted_sessions (all)",
            WhatsAppAppLibrary.list_persisted_sessions,
        )
        if result.get('status') == 'success':
            sessions = result.get('sessions', [])
            print_info(f"Total persisted sessions: {result.get('count', len(sessions))}")
            for s in sessions[:5]:
                print_info(f"  Session: {s.get('session_id', 'N/A')}")

        # Test list_persisted_sessions (filtered by user)
        result = self.run_test(
            "list_persisted_sessions (user filtered)",
            WhatsAppAppLibrary.list_persisted_sessions,
            user_id=self.user_id,
        )
        if result.get('status') == 'success':
            sessions = result.get('sessions', [])
            print_info(f"Sessions for user '{self.user_id}': {result.get('count', len(sessions))}")

        # Test get_web_session_status
        result = self.run_test(
            "get_web_session_status",
            WhatsAppAppLibrary.get_web_session_status,
            user_id=self.user_id,
        )
        if result.get('status') in ('connected', 'success'):
            print_info(f"Session status: {result.get('status')}")
            if result.get('session_id'):
                print_info(f"Session ID: {result.get('session_id')}")

        # Test reconnect_whatsapp_web
        result = self.run_test(
            "reconnect_whatsapp_web",
            WhatsAppAppLibrary.reconnect_whatsapp_web,
            user_id=self.user_id,
        )
        reconnect_status = result.get('status', result.get('error', 'unknown'))
        print_info(f"Reconnect result: {reconnect_status}")
        if result.get('success'):
            print_info("Session reconnected successfully")
        elif reconnect_status == 'qr_required':
            print_warning("Session requires QR code re-scan (device was unlinked)")

    # ------------------------------------------------------------------
    # Contact / Search Tests
    # ------------------------------------------------------------------
    def test_contact_operations(self):
        """Test contact search."""
        print_section("CONTACT OPERATIONS")

        # Test search_contact with a generic name
        result = self.run_test(
            "search_contact",
            WhatsAppAppLibrary.search_contact,
            user_id=self.user_id,
            name="Mom",
            phone_number_id=self.phone_number_id,
        )
        if result.get('status') == 'success':
            contact = result.get('contact', {})
            print_info(f"Contact name:  {contact.get('name', 'N/A')}")
            print_info(f"Contact phone: {contact.get('phone', 'N/A')}")

    # ------------------------------------------------------------------
    # Chat History Tests
    # ------------------------------------------------------------------
    def test_chat_operations(self):
        """Test chat history and unread chat retrieval."""
        print_section("CHAT OPERATIONS")

        # Test get_unread_chats
        result = self.run_test(
            "get_unread_chats",
            WhatsAppAppLibrary.get_unread_chats,
            user_id=self.user_id,
            phone_number_id=self.phone_number_id,
        )
        chat_phone = None
        if result.get('status') == 'success':
            unread = result.get('unread_chats', [])
            print_info(f"Unread chats: {result.get('count', len(unread))}")
            for chat in unread[:5]:
                print_info(f"  {chat.get('name', 'Unknown')} - {chat.get('unread_count', '?')} unread")
                # Grab a phone number from an unread chat if available for history test
                if not chat_phone and chat.get('phone'):
                    chat_phone = chat['phone']

        # Test get_chat_history -- use a found phone or a placeholder
        test_phone = chat_phone or "0000000000"
        result = self.run_test(
            "get_chat_history",
            WhatsAppAppLibrary.get_chat_history,
            user_id=self.user_id,
            phone_number=test_phone,
            limit=10,
            phone_number_id=self.phone_number_id,
        )
        if result.get('status') == 'success':
            messages = result.get('messages', [])
            print_info(f"Messages retrieved: {result.get('count', len(messages))}")
            for msg in messages[:5]:
                sender = msg.get('sender', 'unknown')
                text = msg.get('text', msg.get('body', ''))[:80]
                print_info(f"  [{sender}] {text}")

    # ------------------------------------------------------------------
    # Send Message Tests (skippable)
    # ------------------------------------------------------------------
    def test_send_operations(self):
        """Test sending text and media messages (uses real delivery)."""
        print_section("SEND OPERATIONS (LIVE)")

        # Test send_text_message
        test_text = f"[CraftOS integration test] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        result = self.run_test(
            "send_text_message",
            WhatsAppAppLibrary.send_text_message,
            user_id=self.user_id,
            to=self._get_self_phone(),
            message=test_text,
            phone_number_id=self.phone_number_id,
        )
        if result.get('status') == 'success':
            print_info(f"Message sent to: {result.get('to')}")
            print_info(f"Via: {result.get('via')}")

        # Test send_media_message -- send a small text file to self
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, prefix='craftos_test_')
        tmp.write(f"CraftOS WhatsApp integration test file - {datetime.now().isoformat()}")
        tmp.close()

        try:
            result = self.run_test(
                "send_media_message",
                WhatsAppAppLibrary.send_media_message,
                user_id=self.user_id,
                to=self._get_self_phone(),
                media_type="document",
                media_url=tmp.name,
                caption="Integration test document",
                phone_number_id=self.phone_number_id,
            )
            if result.get('status') == 'success':
                print_info(f"Media sent to: {result.get('to')}")
                print_info(f"Media type: {result.get('media_type')}")
                print_info(f"Via: {result.get('via')}")
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp.name)
                print_info(f"Cleaned up temp file: {tmp.name}")
            except OSError:
                pass

    def _get_self_phone(self) -> str:
        """Get the user's own phone number for self-message tests."""
        cred = WhatsAppAppLibrary.get_credentials(
            user_id=self.user_id,
            phone_number_id=self.phone_number_id,
        )
        if cred and cred.display_phone_number:
            return cred.display_phone_number
        if cred and cred.jid:
            # Extract phone from JID like "1234567890@s.whatsapp.net"
            return cred.jid.split('@')[0]
        # Fallback: use phone_number_id as session identifier
        return cred.phone_number_id if cred else "0000000000"

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
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
                print(f"    {Colors.GREEN}[PASS]{Colors.END} {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}[FAIL]{Colors.END} {name}")
            else:
                print(f"    {Colors.YELLOW}[ERR] {Colors.END} {name}")


def list_credentials():
    """List all stored WhatsApp credentials."""
    print_header("STORED WHATSAPP CREDENTIALS")

    WhatsAppAppLibrary.initialize()
    cred_store = WhatsAppAppLibrary.get_credential_store()

    # Access internal credentials dict to list all users
    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No WhatsApp credentials found.")
        print_info("Please authenticate via the CraftOS control panel first.")
        return None, None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    for i, cred in enumerate(all_credentials, 1):
        print(f"  [{i}] User ID:          {cred.user_id}")
        print(f"      Phone Number ID:  {cred.phone_number_id}")
        print(f"      Session ID:       {cred.session_id}")
        print(f"      JID:              {cred.jid}")
        print(f"      Display Phone:    {cred.display_phone_number}")
        print()

    return all_credentials[0].user_id, all_credentials[0].phone_number_id


def main():
    parser = argparse.ArgumentParser(description='Test WhatsApp Web API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--phone-number-id', type=str, help='WhatsApp phone number / session ID')
    parser.add_argument('--list', action='store_true', help='List stored credentials and exit')
    parser.add_argument('--skip-send', action='store_true', help='Skip tests that actually send messages')
    parser.add_argument(
        '--only', type=str,
        help='Only run specific test group (init, session, contact, chat, send)'
    )
    args = parser.parse_args()

    print_header("WHATSAPP EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    WhatsAppAppLibrary.initialize()
    print_success("WhatsAppAppLibrary initialized")

    # List credentials if requested
    if args.list:
        list_credentials()
        return

    # Get credentials
    user_id = args.user_id
    phone_number_id = args.phone_number_id

    if not user_id:
        print_section("CREDENTIAL LOOKUP")
        user_id, phone_number_id = list_credentials()

        if not user_id:
            print_error("No credentials available. Exiting.")
            return

        print_info(f"Using: user_id={user_id}")
        print_info(f"       phone_number_id={phone_number_id}")

    # Validate connection
    if not WhatsAppAppLibrary.validate_connection(user_id=user_id, phone_number_id=phone_number_id):
        print_error("Invalid credentials or no connection found.")
        return

    print_success("Credential validation passed")

    # Create tester
    tester = WhatsAppTester(user_id=user_id, phone_number_id=phone_number_id)

    try:
        # Run tests based on --only flag or all
        test_groups = {
            'init': tester.test_initialization,
            'session': tester.test_session_operations,
            'contact': tester.test_contact_operations,
            'chat': tester.test_chat_operations,
        }

        if args.only:
            if args.only in test_groups:
                test_groups[args.only]()
            elif args.only == 'send':
                if args.skip_send:
                    print_warning("--skip-send is set; nothing to run for 'send' group.")
                else:
                    tester.test_send_operations()
            else:
                print_error(f"Unknown test group: {args.only}")
                print_info("Available: init, session, contact, chat, send")
                return
        else:
            # Run all tests in order
            tester.test_initialization()
            tester.test_session_operations()
            tester.test_contact_operations()
            tester.test_chat_operations()

            if not args.skip_send:
                tester.test_send_operations()
            else:
                print_section("SEND OPERATIONS (SKIPPED)")
                print_warning("Skipped send_text_message and send_media_message (--skip-send)")

    finally:
        pass  # No persistent artifacts to clean up; temp file already removed in test_send_operations

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
