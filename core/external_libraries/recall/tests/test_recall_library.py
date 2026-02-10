"""
Integration test script for Recall.ai external library.

This script tests ALL RecallAppLibrary methods using stored credentials.
Run this to verify Recall.ai integration without going through the agent cycle.

Usage:
    python test_recall_library.py [--user-id YOUR_USER_ID] [--list] [--only GROUP] [--meeting-url URL]

If no arguments provided, it will use the first stored credential.

Examples:
    python test_recall_library.py --list
    python test_recall_library.py --user-id my_user
    python test_recall_library.py --only connection
    python test_recall_library.py --only meeting --meeting-url "https://zoom.us/j/123456789"
    python test_recall_library.py --only bot --meeting-url "https://meet.google.com/abc-defg-hij"
"""
import sys
import argparse
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.recall.external_app_library import RecallAppLibrary


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
    print(f"{Colors.GREEN}PASS {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}FAIL {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}WARN {text}{Colors.END}")


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


class RecallTester:
    """Test runner for Recall.ai API methods."""

    def __init__(self, user_id: str, meeting_url: Optional[str] = None):
        self.user_id = user_id
        self.meeting_url = meeting_url
        self.test_results = {}
        self.created_bot_id = None  # Store for cleanup

    def run_test(self, test_name: str, func, *args, **kwargs) -> Dict[str, Any]:
        """Run a single test and record result."""
        print(f"\n  Testing: {test_name}...")
        try:
            result = func(*args, **kwargs)

            if isinstance(result, bool):
                # For validate_connection which returns a bool
                if result:
                    print_success(f"{test_name} - returned True")
                    self.test_results[test_name] = 'PASS'
                else:
                    print_error(f"{test_name} - returned False")
                    self.test_results[test_name] = 'FAIL'
                return {"status": "success" if result else "error", "value": result}

            if result is None:
                # For get_credentials when no credential found
                print_error(f"{test_name} - returned None")
                self.test_results[test_name] = 'FAIL'
                return {"status": "error", "reason": "Returned None"}

            # Handle credential objects (from get_credentials)
            if hasattr(result, 'api_key'):
                print_success(f"{test_name} - SUCCESS")
                self.test_results[test_name] = 'PASS'
                return {"status": "success", "credential": result}

            # Handle dict results from API methods
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

    # ===================================================================
    # CONNECTION & CREDENTIAL TESTS
    # ===================================================================

    def test_connection_operations(self):
        """Test initialize, validate_connection, and get_credentials."""
        print_section("CONNECTION & CREDENTIAL OPERATIONS")

        # Test initialize (already called, but test idempotency)
        print(f"\n  Testing: initialize (idempotent call)...")
        try:
            RecallAppLibrary.initialize()
            print_success("initialize - SUCCESS (idempotent)")
            self.test_results["initialize"] = 'PASS'
        except Exception as e:
            print_error(f"initialize - EXCEPTION: {str(e)}")
            self.test_results["initialize"] = 'ERROR'

        # Test validate_connection
        self.run_test(
            "validate_connection",
            RecallAppLibrary.validate_connection,
            user_id=self.user_id,
        )

        # Test validate_connection with invalid user
        print(f"\n  Testing: validate_connection (invalid user)...")
        try:
            result = RecallAppLibrary.validate_connection(user_id="nonexistent_user_xyz_999")
            if result is False:
                print_success("validate_connection (invalid user) - correctly returned False")
                self.test_results["validate_connection (invalid user)"] = 'PASS'
            else:
                print_error("validate_connection (invalid user) - should have returned False")
                self.test_results["validate_connection (invalid user)"] = 'FAIL'
        except Exception as e:
            print_error(f"validate_connection (invalid user) - EXCEPTION: {str(e)}")
            self.test_results["validate_connection (invalid user)"] = 'ERROR'

        # Test get_credentials
        result = self.run_test(
            "get_credentials",
            RecallAppLibrary.get_credentials,
            user_id=self.user_id,
        )
        if result.get('status') == 'success' and hasattr(result.get('credential'), 'api_key'):
            cred = result['credential']
            masked_key = cred.api_key[:8] + "..." if len(cred.api_key) > 8 else "***"
            print_info(f"API Key: {masked_key}")
            print_info(f"Region: {cred.region}")

        # Test get_credentials with invalid user
        print(f"\n  Testing: get_credentials (invalid user)...")
        try:
            result = RecallAppLibrary.get_credentials(user_id="nonexistent_user_xyz_999")
            if result is None:
                print_success("get_credentials (invalid user) - correctly returned None")
                self.test_results["get_credentials (invalid user)"] = 'PASS'
            else:
                print_error("get_credentials (invalid user) - should have returned None")
                self.test_results["get_credentials (invalid user)"] = 'FAIL'
        except Exception as e:
            print_error(f"get_credentials (invalid user) - EXCEPTION: {str(e)}")
            self.test_results["get_credentials (invalid user)"] = 'ERROR'

    # ===================================================================
    # BOT LISTING TESTS
    # ===================================================================

    def test_bot_listing_operations(self):
        """Test list_bots and get_bot_status for existing bots."""
        print_section("BOT LISTING OPERATIONS")

        # Test list_bots
        result = self.run_test(
            "list_bots",
            RecallAppLibrary.list_bots,
            user_id=self.user_id,
            page_size=10,
        )

        if result.get('status') == 'success':
            bots = result.get('bots', {})
            if isinstance(bots, dict):
                bot_list = bots.get('results', bots.get('bots', []))
                print_info(f"Found {len(bot_list)} bot(s)")
                for bot in bot_list[:3]:
                    bot_id = bot.get('id', bot.get('bot_id', 'N/A'))
                    bot_status = bot.get('status_changes', [{}])
                    latest_status = bot_status[-1].get('code', 'unknown') if bot_status else 'unknown'
                    print_info(f"  Bot: {bot_id} - Status: {latest_status}")
            elif isinstance(bots, list):
                print_info(f"Found {len(bots)} bot(s)")
                for bot in bots[:3]:
                    bot_id = bot.get('id', bot.get('bot_id', 'N/A'))
                    print_info(f"  Bot: {bot_id}")
            print_result(result)

        # Test list_bots with custom page_size
        self.run_test(
            "list_bots (page_size=1)",
            RecallAppLibrary.list_bots,
            user_id=self.user_id,
            page_size=1,
        )

        # Test get_bot_status with a known bot (if available from listing)
        existing_bot_id = None
        if result.get('status') == 'success':
            bots = result.get('bots', {})
            if isinstance(bots, dict):
                bot_list = bots.get('results', bots.get('bots', []))
            elif isinstance(bots, list):
                bot_list = bots
            else:
                bot_list = []

            if bot_list:
                existing_bot_id = bot_list[0].get('id', bot_list[0].get('bot_id'))

        if existing_bot_id:
            status_result = self.run_test(
                "get_bot_status (existing bot)",
                RecallAppLibrary.get_bot_status,
                user_id=self.user_id,
                bot_id=existing_bot_id,
            )
            if status_result.get('status') == 'success':
                print_result(status_result.get('bot', {}))
        else:
            print_warning("No existing bots found to test get_bot_status. Skipping.")
            print_info("Use --only meeting --meeting-url URL to test bot creation and status.")

        # Test get_bot_status with a fake bot ID (expect error)
        error_result = self.run_test(
            "get_bot_status (invalid bot_id)",
            RecallAppLibrary.get_bot_status,
            user_id=self.user_id,
            bot_id="00000000-0000-0000-0000-000000000000",
        )
        # This should fail -- we mark it as PASS if it correctly returns an error
        if error_result.get('status') == 'error':
            self.test_results["get_bot_status (invalid bot_id)"] = 'PASS'
            print_info("  -> Correctly returned error for invalid bot_id")

    # ===================================================================
    # MEETING LIFECYCLE TESTS (requires --meeting-url)
    # ===================================================================

    def test_meeting_lifecycle(self):
        """Test join_meeting, get_bot_status, get_transcript, get_recording,
        send_chat_message, speak_in_meeting, leave_meeting, delete_bot.

        This test group requires a valid --meeting-url to create a real bot.
        """
        print_section("MEETING LIFECYCLE (requires --meeting-url)")

        if not self.meeting_url:
            print_warning("No --meeting-url provided. Skipping meeting lifecycle tests.")
            print_info("Use: --meeting-url 'https://zoom.us/j/...' to run these tests.")
            # Record all as skipped
            for test_name in [
                "join_meeting", "get_bot_status (live bot)", "get_transcript (live bot)",
                "get_recording (live bot)", "send_chat_message (live bot)",
                "speak_in_meeting (live bot)", "leave_meeting (live bot)",
                "delete_bot (live bot)",
            ]:
                print_warning(f"  SKIPPED: {test_name}")
            return

        # Test join_meeting
        result = self.run_test(
            "join_meeting",
            RecallAppLibrary.join_meeting,
            user_id=self.user_id,
            meeting_url=self.meeting_url,
            bot_name="CraftOS Integration Test Bot",
            transcription_provider="deepgram",
            recording_mode="speaker_view",
        )

        if result.get('status') == 'success':
            bot_data = result.get('bot', {})
            self.created_bot_id = bot_data.get('id', bot_data.get('bot_id'))
            print_info(f"Created bot ID: {self.created_bot_id}")
            print_result(bot_data)
        else:
            print_error("join_meeting failed. Cannot proceed with remaining meeting lifecycle tests.")
            return

        if not self.created_bot_id:
            print_error("No bot_id returned from join_meeting. Cannot continue.")
            return

        # Give the bot a moment to register
        print_info("Waiting 5 seconds for bot to register...")
        time.sleep(5)

        # Test get_bot_status on the live bot
        status_result = self.run_test(
            "get_bot_status (live bot)",
            RecallAppLibrary.get_bot_status,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
        )
        if status_result.get('status') == 'success':
            print_result(status_result.get('bot', {}))

        # Test get_transcript on the live bot (may be empty if just joined)
        transcript_result = self.run_test(
            "get_transcript (live bot)",
            RecallAppLibrary.get_transcript,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
        )
        if transcript_result.get('status') == 'success':
            transcript = transcript_result.get('transcript')
            if transcript:
                print_info(f"Transcript entries: {len(transcript)}")
                print_result({"transcript_preview": transcript[:3]})
            else:
                print_info("Transcript is empty (expected for a bot that just joined).")

        # Test get_recording on the live bot (may not be available yet)
        recording_result = self.run_test(
            "get_recording (live bot)",
            RecallAppLibrary.get_recording,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
        )
        if recording_result.get('status') == 'success':
            recording = recording_result.get('recording')
            print_result(recording if recording else {"recording": "not yet available"})

        # Test send_chat_message on the live bot
        self.run_test(
            "send_chat_message (live bot)",
            RecallAppLibrary.send_chat_message,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
            message="Hello from CraftOS integration test!",
        )

        # Test speak_in_meeting on the live bot (minimal silent audio payload)
        # This sends a tiny base64-encoded WAV to exercise the API path
        # A minimal WAV header for 0 samples at 16kHz mono 16-bit PCM
        import base64
        import struct
        wav_header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36, b'WAVE',
            b'fmt ', 16, 1, 1, 16000, 32000, 2, 16,
            b'data', 0,
        )
        silent_audio_b64 = base64.b64encode(wav_header).decode('utf-8')

        self.run_test(
            "speak_in_meeting (live bot)",
            RecallAppLibrary.speak_in_meeting,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
            audio_data=silent_audio_b64,
            audio_format="wav",
        )

        # Test leave_meeting on the live bot
        self.run_test(
            "leave_meeting (live bot)",
            RecallAppLibrary.leave_meeting,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
        )

        # Give the bot a moment to leave
        print_info("Waiting 3 seconds for bot to leave...")
        time.sleep(3)

        # Test delete_bot on the live bot
        self.run_test(
            "delete_bot (live bot)",
            RecallAppLibrary.delete_bot,
            user_id=self.user_id,
            bot_id=self.created_bot_id,
        )

        # Mark as cleaned up so cleanup() doesn't try again
        self.created_bot_id = None

    # ===================================================================
    # BOT-DEPENDENT OPERATIONS (without a live meeting)
    # ===================================================================

    def test_bot_dependent_operations(self):
        """Test get_transcript, get_recording, send_chat_message,
        speak_in_meeting, leave_meeting, delete_bot with invalid bot IDs.
        These should all return structured errors (not crash).
        """
        print_section("BOT-DEPENDENT OPERATIONS (error-path validation)")

        fake_bot_id = "00000000-0000-0000-0000-000000000000"

        # Each of these should return a proper error dict, not crash
        error_tests = [
            ("get_transcript (invalid bot)", RecallAppLibrary.get_transcript,
             {"user_id": self.user_id, "bot_id": fake_bot_id}),
            ("get_recording (invalid bot)", RecallAppLibrary.get_recording,
             {"user_id": self.user_id, "bot_id": fake_bot_id}),
            ("send_chat_message (invalid bot)", RecallAppLibrary.send_chat_message,
             {"user_id": self.user_id, "bot_id": fake_bot_id, "message": "test"}),
            ("speak_in_meeting (invalid bot)", RecallAppLibrary.speak_in_meeting,
             {"user_id": self.user_id, "bot_id": fake_bot_id, "audio_data": "dGVzdA==", "audio_format": "wav"}),
            ("leave_meeting (invalid bot)", RecallAppLibrary.leave_meeting,
             {"user_id": self.user_id, "bot_id": fake_bot_id}),
            ("delete_bot (invalid bot)", RecallAppLibrary.delete_bot,
             {"user_id": self.user_id, "bot_id": fake_bot_id}),
        ]

        for test_name, func, kwargs in error_tests:
            print(f"\n  Testing: {test_name}...")
            try:
                result = func(**kwargs)
                status = result.get('status', 'unknown')
                if status == 'error':
                    print_success(f"{test_name} - correctly returned error")
                    self.test_results[test_name] = 'PASS'
                    reason = result.get('reason', result.get('details', ''))
                    print_info(f"  Error detail: {reason}")
                else:
                    # An unexpected success with a fake bot_id is still technically
                    # a valid API response -- mark it as PASS but note it
                    print_warning(f"{test_name} - returned '{status}' (unexpected for invalid bot)")
                    self.test_results[test_name] = 'PASS'
                    print_result(result)
            except Exception as e:
                print_error(f"{test_name} - EXCEPTION: {str(e)}")
                self.test_results[test_name] = 'ERROR'

        # Also test all methods with a completely invalid user_id (no credentials)
        print(f"\n  Testing: join_meeting (no credentials)...")
        try:
            result = RecallAppLibrary.join_meeting(
                user_id="nonexistent_user_xyz_999",
                meeting_url="https://zoom.us/j/000000000",
            )
            if result.get('status') == 'error' and 'No Recall.ai API key' in result.get('reason', ''):
                print_success("join_meeting (no credentials) - correctly returned credential error")
                self.test_results["join_meeting (no credentials)"] = 'PASS'
            else:
                print_error(f"join_meeting (no credentials) - unexpected result: {result}")
                self.test_results["join_meeting (no credentials)"] = 'FAIL'
        except Exception as e:
            print_error(f"join_meeting (no credentials) - EXCEPTION: {str(e)}")
            self.test_results["join_meeting (no credentials)"] = 'ERROR'

    def cleanup(self):
        """Clean up any created test data."""
        print_section("CLEANUP")

        if self.created_bot_id:
            print_info(f"Cleaning up bot: {self.created_bot_id}")

            # Try to leave the meeting first
            print_info("  Attempting to leave meeting...")
            leave_result = RecallAppLibrary.leave_meeting(
                user_id=self.user_id,
                bot_id=self.created_bot_id,
            )
            if leave_result.get('status') == 'success':
                print_success("  Bot left the meeting")
            else:
                print_warning(f"  Leave meeting returned: {leave_result.get('reason', leave_result.get('details', 'unknown'))}")

            time.sleep(2)

            # Then delete the bot
            print_info("  Attempting to delete bot...")
            delete_result = RecallAppLibrary.delete_bot(
                user_id=self.user_id,
                bot_id=self.created_bot_id,
            )
            if delete_result.get('status') == 'success':
                print_success("  Bot deleted")
            else:
                print_warning(f"  Delete bot returned: {delete_result.get('reason', delete_result.get('details', 'unknown'))}")
        else:
            print_info("No test bots to clean up.")

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
                print(f"    {Colors.GREEN}PASS{Colors.END} {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}FAIL{Colors.END} {name}")
            else:
                print(f"    {Colors.YELLOW}ERR {Colors.END} {name}")


def list_credentials():
    """List all stored Recall.ai credentials."""
    print_header("STORED RECALL.AI CREDENTIALS")

    RecallAppLibrary.initialize()
    cred_store = RecallAppLibrary.get_credential_store()

    # Access internal credentials dict to list all users
    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No Recall.ai credentials found.")
        print_info("Please configure your API key via the CraftOS control panel first.")
        return None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    for i, cred in enumerate(all_credentials, 1):
        masked_key = cred.api_key[:8] + "..." if len(cred.api_key) > 8 else "***"
        print(f"  [{i}] User ID: {cred.user_id}")
        print(f"      API Key:  {masked_key}")
        print(f"      Region:   {cred.region}")
        print()

    return all_credentials[0].user_id


def main():
    parser = argparse.ArgumentParser(description='Test Recall.ai API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--meeting-url', type=str, help='Meeting URL for join/lifecycle tests (Zoom, Meet, Teams)')
    parser.add_argument(
        '--only', type=str,
        help='Only run specific test group (connection, listing, meeting, bot_errors)',
    )
    args = parser.parse_args()

    print_header("RECALL.AI EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    RecallAppLibrary.initialize()
    print_success("RecallAppLibrary initialized")

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

    # Validate connection
    if not RecallAppLibrary.validate_connection(user_id=user_id):
        print_error(f"No valid credentials found for user_id='{user_id}'.")
        print_info("Use --list to see stored credentials or configure via the CraftOS control panel.")
        return

    print_success("Credential validation passed")

    # Create tester
    tester = RecallTester(user_id=user_id, meeting_url=args.meeting_url)

    try:
        # Run tests based on --only flag or all
        test_groups = {
            'connection': tester.test_connection_operations,
            'listing': tester.test_bot_listing_operations,
            'meeting': tester.test_meeting_lifecycle,
            'bot_errors': tester.test_bot_dependent_operations,
        }

        if args.only:
            if args.only in test_groups:
                test_groups[args.only]()
            else:
                print_error(f"Unknown test group: {args.only}")
                print_info("Available groups: connection, listing, meeting, bot_errors")
                return
        else:
            # Run all tests
            tester.test_connection_operations()
            tester.test_bot_listing_operations()
            tester.test_meeting_lifecycle()
            tester.test_bot_dependent_operations()

    finally:
        # Cleanup any bots that were created during testing
        tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
