"""
Comprehensive test script for LinkedIn external library.

This script tests ALL LinkedIn API methods using stored credentials.
Run this to verify LinkedIn integration without going through the agent cycle.

Usage:
    python test_linkedin_library.py [--user-id YOUR_USER_ID] [--linkedin-id YOUR_LINKEDIN_URN]

If no arguments provided, it will use defaults or prompt you.
"""
import sys
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add parent directories to path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.linkedin.external_app_library import LinkedInAppLibrary

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
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


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


class LinkedInTester:
    """Test runner for LinkedIn API methods."""

    def __init__(self, user_id: str, linkedin_id: Optional[str] = None):
        self.user_id = user_id
        self.linkedin_id = linkedin_id
        self.test_results = {}
        self.created_post_urn = None  # Store for cleanup
        self.created_comment_urn = None

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

    def test_profile_operations(self):
        """Test profile-related operations."""
        print_section("PROFILE OPERATIONS")

        # Test get_my_profile
        result = self.run_test(
            "get_my_profile",
            LinkedInAppLibrary.get_my_profile,
            user_id=self.user_id,
            linkedin_id=self.linkedin_id
        )
        if result.get('status') == 'success':
            profile = result.get('profile', {})
            print_info(f"Name: {profile.get('name', 'N/A')}")
            print_info(f"LinkedIn ID: {profile.get('sub', profile.get('id', 'N/A'))}")

        # Test get_profile_details
        result = self.run_test(
            "get_profile_details",
            LinkedInAppLibrary.get_profile_details,
            user_id=self.user_id,
            linkedin_id=self.linkedin_id
        )
        if result.get('status') == 'success':
            print_result(result.get('profile', {}))

    def test_post_operations(self, skip_create: bool = False):
        """Test post-related operations."""
        print_section("POST OPERATIONS")

        # Test get_my_posts
        result = self.run_test(
            "get_my_posts",
            LinkedInAppLibrary.get_my_posts,
            user_id=self.user_id,
            count=5,
            linkedin_id=self.linkedin_id
        )

        existing_post_urn = None
        if result.get('status') == 'success':
            posts = result.get('posts', {}).get('elements', [])
            print_info(f"Found {len(posts)} posts")
            if posts:
                existing_post_urn = posts[0].get('id')
                print_info(f"Latest post URN: {existing_post_urn}")

        if not skip_create:
            # Test create_post (text only)
            test_text = f"Test post from CraftOS LinkedIn integration - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            result = self.run_test(
                "create_post (text)",
                LinkedInAppLibrary.create_post,
                user_id=self.user_id,
                text=test_text,
                visibility="CONNECTIONS",  # Limited visibility for test
                linkedin_id=self.linkedin_id
            )

            if result.get('status') == 'success':
                self.created_post_urn = result.get('post', {}).get('id')
                print_info(f"Created post URN: {self.created_post_urn}")

                # Test get_post for the created post
                if self.created_post_urn:
                    self.run_test(
                        "get_post",
                        LinkedInAppLibrary.get_post,
                        user_id=self.user_id,
                        post_urn=self.created_post_urn,
                        linkedin_id=self.linkedin_id
                    )

                    # Test get_post_analytics
                    self.run_test(
                        "get_post_analytics",
                        LinkedInAppLibrary.get_post_analytics,
                        user_id=self.user_id,
                        post_urn=self.created_post_urn,
                        linkedin_id=self.linkedin_id
                    )

        return existing_post_urn

    def test_social_actions(self, post_urn: Optional[str] = None):
        """Test like/unlike operations."""
        print_section("SOCIAL ACTIONS (LIKES)")

        if not post_urn:
            print_warning("No post URN available for like tests. Skipping.")
            return

        # Test like_post
        result = self.run_test(
            "like_post",
            LinkedInAppLibrary.like_post,
            user_id=self.user_id,
            post_urn=post_urn,
            linkedin_id=self.linkedin_id
        )

        # Test get_post_likes
        self.run_test(
            "get_post_likes",
            LinkedInAppLibrary.get_post_likes,
            user_id=self.user_id,
            post_urn=post_urn,
            count=10,
            linkedin_id=self.linkedin_id
        )

        # Test unlike_post
        self.run_test(
            "unlike_post",
            LinkedInAppLibrary.unlike_post,
            user_id=self.user_id,
            post_urn=post_urn,
            linkedin_id=self.linkedin_id
        )

    def test_comment_operations(self, post_urn: Optional[str] = None):
        """Test comment-related operations."""
        print_section("COMMENT OPERATIONS")

        if not post_urn:
            print_warning("No post URN available for comment tests. Skipping.")
            return

        # Test get_post_comments
        self.run_test(
            "get_post_comments",
            LinkedInAppLibrary.get_post_comments,
            user_id=self.user_id,
            post_urn=post_urn,
            count=10,
            linkedin_id=self.linkedin_id
        )

        # Test comment_on_post
        result = self.run_test(
            "comment_on_post",
            LinkedInAppLibrary.comment_on_post,
            user_id=self.user_id,
            post_urn=post_urn,
            text="Test comment from CraftOS integration",
            linkedin_id=self.linkedin_id
        )

        if result.get('status') == 'success':
            self.created_comment_urn = result.get('comment', {}).get('id')
            print_info(f"Created comment URN: {self.created_comment_urn}")

            # Test delete_comment
            if self.created_comment_urn:
                self.run_test(
                    "delete_comment",
                    LinkedInAppLibrary.delete_comment,
                    user_id=self.user_id,
                    post_urn=post_urn,
                    comment_urn=self.created_comment_urn,
                    linkedin_id=self.linkedin_id
                )

    def test_organization_operations(self):
        """Test organization-related operations."""
        print_section("ORGANIZATION OPERATIONS")

        # Test get_my_organizations
        result = self.run_test(
            "get_my_organizations",
            LinkedInAppLibrary.get_my_organizations,
            user_id=self.user_id,
            linkedin_id=self.linkedin_id
        )

        org_id = None
        if result.get('status') == 'success':
            orgs = result.get('organizations', {}).get('elements', [])
            print_info(f"Found {len(orgs)} organizations with admin access")
            if orgs:
                # Get first org ID
                org_data = orgs[0].get('organizationalTarget', '')
                if org_data:
                    org_id = org_data.split(':')[-1] if ':' in org_data else org_data
                    print_info(f"Using organization: {org_id}")

        if org_id:
            # Test get_organization_info
            self.run_test(
                "get_organization_info",
                LinkedInAppLibrary.get_organization_info,
                user_id=self.user_id,
                organization_id=org_id,
                linkedin_id=self.linkedin_id
            )

            # Test get_organization_analytics
            org_urn = f"urn:li:organization:{org_id}"
            self.run_test(
                "get_organization_analytics",
                LinkedInAppLibrary.get_organization_analytics,
                user_id=self.user_id,
                organization_urn=org_urn,
                linkedin_id=self.linkedin_id
            )

            # Test get_organization_posts
            self.run_test(
                "get_organization_posts",
                LinkedInAppLibrary.get_organization_posts,
                user_id=self.user_id,
                organization_urn=org_urn,
                count=5,
                linkedin_id=self.linkedin_id
            )

    def test_network_operations(self):
        """Test connections and network operations."""
        print_section("NETWORK OPERATIONS")

        # Test get_connections
        result = self.run_test(
            "get_connections",
            LinkedInAppLibrary.get_connections,
            user_id=self.user_id,
            count=10,
            linkedin_id=self.linkedin_id
        )

        if result.get('status') == 'success':
            connections = result.get('connections', {}).get('elements', [])
            print_info(f"Found {len(connections)} connections")

        # Test get_sent_invitations
        self.run_test(
            "get_sent_invitations",
            LinkedInAppLibrary.get_sent_invitations,
            user_id=self.user_id,
            count=10,
            linkedin_id=self.linkedin_id
        )

        # Test get_received_invitations
        self.run_test(
            "get_received_invitations",
            LinkedInAppLibrary.get_received_invitations,
            user_id=self.user_id,
            count=10,
            linkedin_id=self.linkedin_id
        )

    def test_search_operations(self):
        """Test search operations."""
        print_section("SEARCH OPERATIONS")

        # Test search_companies
        result = self.run_test(
            "search_companies",
            LinkedInAppLibrary.search_companies,
            user_id=self.user_id,
            keywords="Microsoft",
            count=5,
            linkedin_id=self.linkedin_id
        )

        # Test lookup_company
        self.run_test(
            "lookup_company",
            LinkedInAppLibrary.lookup_company,
            user_id=self.user_id,
            vanity_name="microsoft",
            linkedin_id=self.linkedin_id
        )

        # Test search_jobs
        self.run_test(
            "search_jobs",
            LinkedInAppLibrary.search_jobs,
            user_id=self.user_id,
            keywords="software engineer",
            location="United States",
            count=5,
            linkedin_id=self.linkedin_id
        )

    def test_messaging_operations(self):
        """Test messaging operations."""
        print_section("MESSAGING OPERATIONS")

        # Test get_conversations
        # Note: This often requires special permissions
        self.run_test(
            "get_conversations",
            LinkedInAppLibrary.get_conversations,
            user_id=self.user_id,
            count=10,
            linkedin_id=self.linkedin_id
        )

    def test_follow_operations(self):
        """Test follow/unfollow operations."""
        print_section("FOLLOW OPERATIONS")

        # Test with a well-known company (Microsoft)
        test_org_urn = "urn:li:organization:1035"  # Microsoft

        # Test follow_organization
        self.run_test(
            "follow_organization",
            LinkedInAppLibrary.follow_organization,
            user_id=self.user_id,
            organization_urn=test_org_urn,
            linkedin_id=self.linkedin_id
        )

        # Test unfollow_organization
        self.run_test(
            "unfollow_organization",
            LinkedInAppLibrary.unfollow_organization,
            user_id=self.user_id,
            organization_urn=test_org_urn,
            linkedin_id=self.linkedin_id
        )

    def cleanup(self):
        """Clean up any created test data."""
        print_section("CLEANUP")

        if self.created_post_urn:
            print_info(f"Deleting test post: {self.created_post_urn}")
            result = LinkedInAppLibrary.delete_post(
                user_id=self.user_id,
                post_urn=self.created_post_urn,
                linkedin_id=self.linkedin_id
            )
            if result.get('status') == 'success':
                print_success("Test post deleted")
            else:
                print_error(f"Failed to delete test post: {result.get('reason')}")
        else:
            print_info("No test posts to clean up")

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
                print(f"    {Colors.GREEN}✓{Colors.END} {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}✗{Colors.END} {name}")
            else:
                print(f"    {Colors.YELLOW}!{Colors.END} {name}")


def list_credentials():
    """List all stored LinkedIn credentials."""
    print_header("STORED LINKEDIN CREDENTIALS")

    LinkedInAppLibrary.initialize()
    cred_store = LinkedInAppLibrary.get_credential_store()

    # Access internal credentials dict to list all users
    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No LinkedIn credentials found.")
        print_info("Please authenticate via the CraftOS control panel first.")
        return None, None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    for i, cred in enumerate(all_credentials, 1):
        print(f"  [{i}] User ID: {cred.user_id}")
        print(f"      LinkedIn ID: {cred.linkedin_id}")
        print(f"      Name: {cred.name}")
        print(f"      Email: {cred.email}")
        print(f"      Has Refresh Token: {bool(cred.refresh_token)}")
        if cred.token_expiry:
            expiry_dt = datetime.fromtimestamp(cred.token_expiry)
            print(f"      Token Expires: {expiry_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    return all_credentials[0].user_id, all_credentials[0].linkedin_id


def main():
    parser = argparse.ArgumentParser(description='Test LinkedIn API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--linkedin-id', type=str, help='LinkedIn URN (urn:li:person:xxx)')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--skip-create', action='store_true', help='Skip tests that create posts')
    parser.add_argument('--only', type=str, help='Only run specific test group (profile, post, social, comment, org, network, search, message, follow)')
    args = parser.parse_args()

    print_header("LINKEDIN EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    LinkedInAppLibrary.initialize()
    print_success("LinkedInAppLibrary initialized")

    # List credentials if requested
    if args.list:
        list_credentials()
        return

    # Get credentials
    user_id = args.user_id
    linkedin_id = args.linkedin_id

    if not user_id:
        print_section("CREDENTIAL LOOKUP")
        user_id, linkedin_id = list_credentials()

        if not user_id:
            print_error("No credentials available. Exiting.")
            return

        print_info(f"Using: user_id={user_id}")
        print_info(f"       linkedin_id={linkedin_id}")

    # Validate connection
    if not LinkedInAppLibrary.validate_connection(user_id=user_id, linkedin_id=linkedin_id):
        print_error("Invalid credentials or no connection found.")
        return

    print_success("Credential validation passed")

    # Create tester
    tester = LinkedInTester(user_id=user_id, linkedin_id=linkedin_id)

    try:
        # Run tests based on --only flag or all
        test_groups = {
            'profile': tester.test_profile_operations,
            'org': tester.test_organization_operations,
            'network': tester.test_network_operations,
            'search': tester.test_search_operations,
            'message': tester.test_messaging_operations,
        }

        if args.only:
            if args.only in test_groups:
                test_groups[args.only]()
            elif args.only == 'post':
                tester.test_post_operations(skip_create=args.skip_create)
            elif args.only == 'social':
                existing_post = tester.test_post_operations(skip_create=True)
                tester.test_social_actions(post_urn=tester.created_post_urn or existing_post)
            elif args.only == 'comment':
                existing_post = tester.test_post_operations(skip_create=True)
                tester.test_comment_operations(post_urn=tester.created_post_urn or existing_post)
            elif args.only == 'follow':
                tester.test_follow_operations()
            else:
                print_error(f"Unknown test group: {args.only}")
                print_info("Available: profile, post, social, comment, org, network, search, message, follow")
                return
        else:
            # Run all tests
            tester.test_profile_operations()
            existing_post = tester.test_post_operations(skip_create=args.skip_create)
            tester.test_social_actions(post_urn=tester.created_post_urn or existing_post)
            tester.test_comment_operations(post_urn=tester.created_post_urn or existing_post)
            tester.test_organization_operations()
            tester.test_network_operations()
            tester.test_search_operations()
            tester.test_messaging_operations()
            tester.test_follow_operations()

    finally:
        # Cleanup
        if not args.skip_create:
            tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
