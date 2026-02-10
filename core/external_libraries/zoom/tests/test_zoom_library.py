"""
Comprehensive integration test script for Zoom external library.

This script tests ALL Zoom API methods using stored credentials.
Run this to verify Zoom integration without going through the agent cycle.

Usage:
    python test_zoom_library.py [--user-id YOUR_USER_ID] [--zoom-user-id YOUR_ZOOM_USER_ID]

If no arguments provided, it will use defaults or prompt you.
"""
import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.zoom.external_app_library import ZoomAppLibrary


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


class ZoomTester:
    """Test runner for Zoom API methods."""

    def __init__(self, user_id: str, zoom_user_id: Optional[str] = None):
        self.user_id = user_id
        self.zoom_user_id = zoom_user_id
        self.test_results = {}
        self.created_meeting_id = None  # Store for cleanup

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

    # ------------------------------------------------------------------
    # INITIALIZATION & CREDENTIAL TESTS
    # ------------------------------------------------------------------

    def test_initialization(self):
        """Test library initialization and credential access."""
        print_section("INITIALIZATION & CREDENTIALS")

        # Test initialize (already called, but verify idempotency)
        print(f"\n  Testing: initialize (idempotent)...")
        try:
            ZoomAppLibrary.initialize()
            print_success("initialize (idempotent) - SUCCESS")
            self.test_results["initialize"] = 'PASS'
        except Exception as e:
            print_error(f"initialize (idempotent) - EXCEPTION: {str(e)}")
            self.test_results["initialize"] = 'ERROR'

        # Test validate_connection
        print(f"\n  Testing: validate_connection...")
        try:
            is_valid = ZoomAppLibrary.validate_connection(
                user_id=self.user_id,
                zoom_user_id=self.zoom_user_id
            )
            if is_valid:
                print_success("validate_connection - SUCCESS")
                self.test_results["validate_connection"] = 'PASS'
            else:
                print_error("validate_connection - FAILED: No valid connection")
                self.test_results["validate_connection"] = 'FAIL'
        except Exception as e:
            print_error(f"validate_connection - EXCEPTION: {str(e)}")
            self.test_results["validate_connection"] = 'ERROR'

        # Test get_credentials
        print(f"\n  Testing: get_credentials...")
        try:
            cred = ZoomAppLibrary.get_credentials(
                user_id=self.user_id,
                zoom_user_id=self.zoom_user_id
            )
            if cred is not None:
                print_success("get_credentials - SUCCESS")
                print_info(f"Zoom User ID: {cred.zoom_user_id}")
                print_info(f"Email: {cred.email}")
                print_info(f"Display Name: {cred.display_name}")
                print_info(f"Has Access Token: {bool(cred.access_token)}")
                print_info(f"Has Refresh Token: {bool(cred.refresh_token)}")
                self.test_results["get_credentials"] = 'PASS'
            else:
                print_error("get_credentials - FAILED: No credential returned")
                self.test_results["get_credentials"] = 'FAIL'
        except Exception as e:
            print_error(f"get_credentials - EXCEPTION: {str(e)}")
            self.test_results["get_credentials"] = 'ERROR'

        # Test ensure_valid_token
        print(f"\n  Testing: ensure_valid_token...")
        try:
            cred = ZoomAppLibrary.ensure_valid_token(
                user_id=self.user_id,
                zoom_user_id=self.zoom_user_id
            )
            if cred is not None:
                print_success("ensure_valid_token - SUCCESS")
                if cred.token_expiry:
                    expiry_dt = datetime.fromtimestamp(cred.token_expiry)
                    print_info(f"Token expires: {expiry_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                self.test_results["ensure_valid_token"] = 'PASS'
            else:
                print_error("ensure_valid_token - FAILED: No credential returned")
                self.test_results["ensure_valid_token"] = 'FAIL'
        except Exception as e:
            print_error(f"ensure_valid_token - EXCEPTION: {str(e)}")
            self.test_results["ensure_valid_token"] = 'ERROR'

    # ------------------------------------------------------------------
    # USER OPERATIONS
    # ------------------------------------------------------------------

    def test_user_operations(self):
        """Test user-related operations."""
        print_section("USER OPERATIONS")

        # Test get_my_profile
        result = self.run_test(
            "get_my_profile",
            ZoomAppLibrary.get_my_profile,
            user_id=self.user_id,
            zoom_user_id=self.zoom_user_id,
        )
        if result.get('status') == 'success':
            profile = result.get('profile', {})
            print_info(f"Email: {profile.get('email', 'N/A')}")
            print_info(f"Display Name: {profile.get('display_name', 'N/A')}")
            print_info(f"Zoom User ID: {profile.get('zoom_user_id', 'N/A')}")
            print_info(f"Account ID: {profile.get('account_id', 'N/A')}")
            print_info(f"Timezone: {profile.get('timezone', 'N/A')}")
            print_info(f"PMI: {profile.get('pmi', 'N/A')}")

        # Test list_users (admin accounts only -- may fail for non-admin)
        result = self.run_test(
            "list_users",
            ZoomAppLibrary.list_users,
            user_id=self.user_id,
            status="active",
            page_size=5,
            zoom_user_id=self.zoom_user_id,
        )
        if result.get('status') == 'success':
            users = result.get('users', {})
            user_list = users.get('users', []) if isinstance(users, dict) else []
            print_info(f"Found {len(user_list)} user(s)")
            for u in user_list[:3]:
                print_info(f"  - {u.get('email', 'N/A')} ({u.get('id', 'N/A')})")

    # ------------------------------------------------------------------
    # MEETING LIST OPERATIONS
    # ------------------------------------------------------------------

    def test_meeting_list_operations(self):
        """Test meeting listing operations."""
        print_section("MEETING LIST OPERATIONS")

        # Test list_meetings (scheduled)
        result = self.run_test(
            "list_meetings (scheduled)",
            ZoomAppLibrary.list_meetings,
            user_id=self.user_id,
            meeting_type="scheduled",
            page_size=10,
            zoom_user_id=self.zoom_user_id,
        )
        existing_meeting_id = None
        if result.get('status') == 'success':
            meetings = result.get('meetings', {})
            meeting_list = meetings.get('meetings', []) if isinstance(meetings, dict) else []
            print_info(f"Found {len(meeting_list)} scheduled meeting(s)")
            for m in meeting_list[:3]:
                print_info(f"  - [{m.get('id')}] {m.get('topic', 'N/A')} @ {m.get('start_time', 'N/A')}")
            if meeting_list:
                existing_meeting_id = str(meeting_list[0].get('id'))
                print_info(f"Will use meeting ID {existing_meeting_id} for detail tests")

        # Test get_upcoming_meetings
        result = self.run_test(
            "get_upcoming_meetings",
            ZoomAppLibrary.get_upcoming_meetings,
            user_id=self.user_id,
            page_size=10,
            zoom_user_id=self.zoom_user_id,
        )
        if result.get('status') == 'success':
            meetings = result.get('meetings', {})
            meeting_list = meetings.get('meetings', []) if isinstance(meetings, dict) else []
            print_info(f"Found {len(meeting_list)} upcoming meeting(s)")
            for m in meeting_list[:3]:
                print_info(f"  - [{m.get('id')}] {m.get('topic', 'N/A')} @ {m.get('start_time', 'N/A')}")

        # Test get_live_meetings
        result = self.run_test(
            "get_live_meetings",
            ZoomAppLibrary.get_live_meetings,
            user_id=self.user_id,
            zoom_user_id=self.zoom_user_id,
        )
        if result.get('status') == 'success':
            meetings = result.get('meetings', {})
            meeting_list = meetings.get('meetings', []) if isinstance(meetings, dict) else []
            print_info(f"Found {len(meeting_list)} live meeting(s)")

        return existing_meeting_id

    # ------------------------------------------------------------------
    # MEETING DETAIL OPERATIONS
    # ------------------------------------------------------------------

    def test_meeting_detail_operations(self, meeting_id: Optional[str] = None):
        """Test operations that require a specific meeting ID."""
        print_section("MEETING DETAIL OPERATIONS")

        if not meeting_id:
            print_warning("No meeting ID available for detail tests. Skipping.")
            return

        # Test get_meeting
        result = self.run_test(
            "get_meeting",
            ZoomAppLibrary.get_meeting,
            user_id=self.user_id,
            meeting_id=meeting_id,
            zoom_user_id=self.zoom_user_id,
        )
        if result.get('status') == 'success':
            meeting = result.get('meeting', {})
            print_info(f"Topic: {meeting.get('topic', 'N/A')}")
            print_info(f"Start Time: {meeting.get('start_time', 'N/A')}")
            print_info(f"Duration: {meeting.get('duration', 'N/A')} minutes")
            print_info(f"Join URL: {meeting.get('join_url', 'N/A')}")

        # Test get_meeting_invitation
        result = self.run_test(
            "get_meeting_invitation",
            ZoomAppLibrary.get_meeting_invitation,
            user_id=self.user_id,
            meeting_id=meeting_id,
            zoom_user_id=self.zoom_user_id,
        )
        if result.get('status') == 'success':
            invitation = result.get('invitation', {})
            inv_text = invitation.get('invitation', '') if isinstance(invitation, dict) else str(invitation)
            # Show first few lines of the invitation
            lines = inv_text.split('\n')[:5]
            for line in lines:
                print_info(f"  {line}")
            if len(inv_text.split('\n')) > 5:
                print_info("  ... (invitation text truncated)")

    # ------------------------------------------------------------------
    # MEETING CRUD OPERATIONS
    # ------------------------------------------------------------------

    def test_meeting_crud_operations(self):
        """Test create, update, and delete meeting operations."""
        print_section("MEETING CRUD OPERATIONS (create / update / delete)")

        # Create a test meeting scheduled for tomorrow
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        start_time = tomorrow.strftime('%Y-%m-%dT10:00:00Z')
        test_topic = f"CraftOS Integration Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # Test create_meeting
        result = self.run_test(
            "create_meeting",
            ZoomAppLibrary.create_meeting,
            user_id=self.user_id,
            topic=test_topic,
            start_time=start_time,
            duration=30,
            timezone="UTC",
            agenda="Automated integration test meeting - safe to delete",
            meeting_type=2,
            zoom_user_id=self.zoom_user_id,
        )

        if result.get('status') == 'success':
            meeting = result.get('meeting', {})
            self.created_meeting_id = str(meeting.get('meeting_id', meeting.get('id', '')))
            print_info(f"Created meeting ID: {self.created_meeting_id}")
            print_info(f"Topic: {meeting.get('topic', 'N/A')}")
            print_info(f"Join URL: {meeting.get('join_url', 'N/A')}")
            print_info(f"Start URL: {meeting.get('start_url', 'N/A')}")

            # Test get_meeting on the newly created meeting
            if self.created_meeting_id:
                self.run_test(
                    "get_meeting (created)",
                    ZoomAppLibrary.get_meeting,
                    user_id=self.user_id,
                    meeting_id=self.created_meeting_id,
                    zoom_user_id=self.zoom_user_id,
                )

                # Test get_meeting_invitation on the newly created meeting
                self.run_test(
                    "get_meeting_invitation (created)",
                    ZoomAppLibrary.get_meeting_invitation,
                    user_id=self.user_id,
                    meeting_id=self.created_meeting_id,
                    zoom_user_id=self.zoom_user_id,
                )

                # Test update_meeting
                updated_topic = f"{test_topic} [UPDATED]"
                result = self.run_test(
                    "update_meeting",
                    ZoomAppLibrary.update_meeting,
                    user_id=self.user_id,
                    meeting_id=self.created_meeting_id,
                    topic=updated_topic,
                    duration=45,
                    agenda="Updated agenda from integration test",
                    zoom_user_id=self.zoom_user_id,
                )

                # Verify the update by fetching the meeting again
                if result.get('status') == 'success':
                    verify_result = self.run_test(
                        "get_meeting (after update)",
                        ZoomAppLibrary.get_meeting,
                        user_id=self.user_id,
                        meeting_id=self.created_meeting_id,
                        zoom_user_id=self.zoom_user_id,
                    )
                    if verify_result.get('status') == 'success':
                        meeting = verify_result.get('meeting', {})
                        print_info(f"Updated topic: {meeting.get('topic', 'N/A')}")
                        print_info(f"Updated duration: {meeting.get('duration', 'N/A')} minutes")

    def cleanup(self):
        """Clean up any created test data."""
        print_section("CLEANUP")

        if self.created_meeting_id:
            print_info(f"Deleting test meeting: {self.created_meeting_id}")
            result = ZoomAppLibrary.delete_meeting(
                user_id=self.user_id,
                meeting_id=self.created_meeting_id,
                zoom_user_id=self.zoom_user_id,
            )
            if result.get('status') == 'success':
                print_success("delete_meeting - Test meeting deleted")
                self.test_results["delete_meeting"] = 'PASS'
            else:
                reason = result.get('reason', result.get('details', 'Unknown error'))
                print_error(f"delete_meeting - Failed to delete test meeting: {reason}")
                self.test_results["delete_meeting"] = 'FAIL'
        else:
            print_info("No test meetings to clean up")

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
    """List all stored Zoom credentials."""
    print_header("STORED ZOOM CREDENTIALS")

    ZoomAppLibrary.initialize()
    cred_store = ZoomAppLibrary.get_credential_store()

    # Access internal credentials dict to list all users
    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No Zoom credentials found.")
        print_info("Please authenticate via the CraftOS control panel first.")
        return None, None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    for i, cred in enumerate(all_credentials, 1):
        print(f"  [{i}] User ID: {cred.user_id}")
        print(f"      Zoom User ID: {cred.zoom_user_id}")
        print(f"      Display Name: {cred.display_name}")
        print(f"      Email: {cred.email}")
        print(f"      Account ID: {cred.account_id}")
        print(f"      Has Refresh Token: {bool(cred.refresh_token)}")
        if cred.token_expiry:
            expiry_dt = datetime.fromtimestamp(cred.token_expiry)
            print(f"      Token Expires: {expiry_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    return all_credentials[0].user_id, all_credentials[0].zoom_user_id


def main():
    parser = argparse.ArgumentParser(description='Test Zoom API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--zoom-user-id', type=str, help='Zoom user ID')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--skip-create', action='store_true', help='Skip tests that create meetings')
    parser.add_argument('--only', type=str, help='Only run specific test group (init, user, meetings, detail, crud)')
    args = parser.parse_args()

    print_header("ZOOM EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    ZoomAppLibrary.initialize()
    print_success("ZoomAppLibrary initialized")

    # List credentials if requested
    if args.list:
        list_credentials()
        return

    # Get credentials
    user_id = args.user_id
    zoom_user_id = args.zoom_user_id

    if not user_id:
        print_section("CREDENTIAL LOOKUP")
        user_id, zoom_user_id = list_credentials()

        if not user_id:
            print_error("No credentials available. Exiting.")
            return

        print_info(f"Using: user_id={user_id}")
        print_info(f"       zoom_user_id={zoom_user_id}")

    # Validate connection
    if not ZoomAppLibrary.validate_connection(user_id=user_id, zoom_user_id=zoom_user_id):
        print_error("Invalid credentials or no connection found.")
        return

    print_success("Credential validation passed")

    # Create tester
    tester = ZoomTester(user_id=user_id, zoom_user_id=zoom_user_id)

    try:
        # Run tests based on --only flag or all
        test_groups = {
            'init': tester.test_initialization,
            'user': tester.test_user_operations,
        }

        if args.only:
            if args.only in test_groups:
                test_groups[args.only]()
            elif args.only == 'meetings':
                tester.test_meeting_list_operations()
            elif args.only == 'detail':
                existing_meeting_id = tester.test_meeting_list_operations()
                tester.test_meeting_detail_operations(meeting_id=existing_meeting_id)
            elif args.only == 'crud':
                if args.skip_create:
                    print_warning("--skip-create with --only crud: nothing to run.")
                else:
                    tester.test_meeting_crud_operations()
            else:
                print_error(f"Unknown test group: {args.only}")
                print_info("Available: init, user, meetings, detail, crud")
                return
        else:
            # Run all tests
            tester.test_initialization()
            tester.test_user_operations()
            existing_meeting_id = tester.test_meeting_list_operations()
            tester.test_meeting_detail_operations(meeting_id=existing_meeting_id)
            if not args.skip_create:
                tester.test_meeting_crud_operations()

    finally:
        # Cleanup created meetings
        if not args.skip_create:
            tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
