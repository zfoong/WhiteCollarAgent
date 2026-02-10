"""
Comprehensive integration test script for Notion external library.

This script tests ALL Notion API methods using stored credentials.
Run this to verify Notion integration without going through the agent cycle.

Usage:
    python test_notion_library.py [--user-id YOUR_USER_ID] [--workspace-id YOUR_WORKSPACE_ID]

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

from core.external_libraries.notion.external_app_library import NotionAppLibrary
from core.external_libraries.notion.helpers.notion_helpers import delete_block

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


class NotionTester:
    """Test runner for Notion API methods."""

    def __init__(self, user_id: str, workspace_id: Optional[str] = None):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.test_results = {}
        self.created_page_id = None  # Store for cleanup
        self.created_subpage_id = None  # Store for cleanup

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
    # Initialization & credential tests
    # ------------------------------------------------------------------
    def test_initialization(self):
        """Test initialize and basic library access."""
        print_section("INITIALIZATION & CREDENTIALS")

        # Test initialize (already called, but verify idempotency)
        print(f"\n  Testing: initialize (idempotent)...")
        try:
            NotionAppLibrary.initialize()
            print_success("initialize (idempotent) - SUCCESS")
            self.test_results["initialize"] = 'PASS'
        except Exception as e:
            print_error(f"initialize - EXCEPTION: {str(e)}")
            self.test_results["initialize"] = 'ERROR'

        # Test validate_connection
        result_valid = NotionAppLibrary.validate_connection(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        print(f"\n  Testing: validate_connection...")
        if result_valid:
            print_success("validate_connection - SUCCESS (credential exists)")
            self.test_results["validate_connection"] = 'PASS'
        else:
            print_error("validate_connection - FAILED (no credential found)")
            self.test_results["validate_connection"] = 'FAIL'

        # Test get_credentials
        print(f"\n  Testing: get_credentials...")
        cred = NotionAppLibrary.get_credentials(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
        )
        if cred is not None:
            print_success("get_credentials - SUCCESS")
            print_info(f"Workspace ID: {cred.workspace_id}")
            print_info(f"Workspace Name: {cred.workspace_name}")
            print_info(f"Token prefix: {cred.token[:12]}...")
            self.test_results["get_credentials"] = 'PASS'
        else:
            print_error("get_credentials - FAILED (returned None)")
            self.test_results["get_credentials"] = 'FAIL'

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def test_search_operations(self):
        """Test search-related operations."""
        print_section("SEARCH OPERATIONS")

        # Test search (general)
        result = self.run_test(
            "search (general)",
            NotionAppLibrary.search,
            user_id=self.user_id,
            query="test",
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            results = result.get('results', [])
            print_info(f"Found {len(results)} results")
            for item in results[:3]:
                obj_type = item.get('object', 'unknown')
                obj_id = item.get('id', 'N/A')
                print_info(f"  - {obj_type}: {obj_id}")

        # Test search with page filter
        result = self.run_test(
            "search (filter=page)",
            NotionAppLibrary.search,
            user_id=self.user_id,
            query="test",
            filter_type="page",
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            print_info(f"Found {len(result.get('results', []))} page results")

        # Test search with database filter
        result = self.run_test(
            "search (filter=database)",
            NotionAppLibrary.search,
            user_id=self.user_id,
            query="test",
            filter_type="database",
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            print_info(f"Found {len(result.get('results', []))} database results")

        return result

    # ------------------------------------------------------------------
    # Page operations (read-only)
    # ------------------------------------------------------------------
    def test_page_read_operations(self, page_id: Optional[str] = None):
        """Test reading page data. Discovers a page via search if none given."""
        print_section("PAGE READ OPERATIONS")

        # Discover a page if not provided
        if not page_id:
            print_info("Discovering a page via search...")
            search_result = NotionAppLibrary.search(
                user_id=self.user_id,
                query="",
                filter_type="page",
                workspace_id=self.workspace_id,
            )
            if search_result.get('status') == 'success':
                pages = search_result.get('results', [])
                if pages:
                    page_id = pages[0].get('id')
                    print_info(f"Using discovered page: {page_id}")

        if not page_id:
            print_warning("No page found to test read operations. Skipping.")
            return None

        # Test get_page
        result = self.run_test(
            "get_page",
            NotionAppLibrary.get_page,
            user_id=self.user_id,
            page_id=page_id,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            page = result.get('page', {})
            print_info(f"Page object type: {page.get('object', 'N/A')}")
            parent = page.get('parent', {})
            print_info(f"Parent type: {list(parent.keys())}")

        # Test get_page_content
        result = self.run_test(
            "get_page_content",
            NotionAppLibrary.get_page_content,
            user_id=self.user_id,
            page_id=page_id,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            blocks = result.get('blocks', [])
            print_info(f"Found {len(blocks)} content blocks")
            for block in blocks[:5]:
                block_type = block.get('type', 'unknown')
                print_info(f"  - block type: {block_type}")

        return page_id

    # ------------------------------------------------------------------
    # Database operations (read-only)
    # ------------------------------------------------------------------
    def test_database_read_operations(self, database_id: Optional[str] = None):
        """Test reading database data. Discovers a database via search if none given."""
        print_section("DATABASE READ OPERATIONS")

        # Discover a database if not provided
        if not database_id:
            print_info("Discovering a database via search...")
            search_result = NotionAppLibrary.search(
                user_id=self.user_id,
                query="",
                filter_type="database",
                workspace_id=self.workspace_id,
            )
            if search_result.get('status') == 'success':
                dbs = search_result.get('results', [])
                if dbs:
                    database_id = dbs[0].get('id')
                    print_info(f"Using discovered database: {database_id}")

        if not database_id:
            print_warning("No database found to test database operations. Skipping.")
            return None

        # Test get_database
        result = self.run_test(
            "get_database",
            NotionAppLibrary.get_database,
            user_id=self.user_id,
            database_id=database_id,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            db = result.get('database', {})
            props = db.get('properties', {})
            print_info(f"Database has {len(props)} properties")
            for prop_name, prop_def in list(props.items())[:5]:
                print_info(f"  - {prop_name}: {prop_def.get('type', 'N/A')}")

        # Test query_database (no filter)
        result = self.run_test(
            "query_database (no filter)",
            NotionAppLibrary.query_database,
            user_id=self.user_id,
            database_id=database_id,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            rows = result.get('results', [])
            print_info(f"Query returned {len(rows)} rows")

        # Test query_database with sort
        result = self.run_test(
            "query_database (with sort)",
            NotionAppLibrary.query_database,
            user_id=self.user_id,
            database_id=database_id,
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            rows = result.get('results', [])
            print_info(f"Sorted query returned {len(rows)} rows")

        return database_id

    # ------------------------------------------------------------------
    # Create / update / append operations (mutating)
    # ------------------------------------------------------------------
    def test_create_operations(self, parent_page_id: Optional[str] = None):
        """Test page creation, update, and content append."""
        print_section("CREATE / UPDATE / APPEND OPERATIONS")

        # We need a parent page to create under. Discover one if not given.
        if not parent_page_id:
            print_info("Discovering a parent page via search...")
            search_result = NotionAppLibrary.search(
                user_id=self.user_id,
                query="",
                filter_type="page",
                workspace_id=self.workspace_id,
            )
            if search_result.get('status') == 'success':
                pages = search_result.get('results', [])
                if pages:
                    parent_page_id = pages[0].get('id')
                    print_info(f"Using parent page: {parent_page_id}")

        if not parent_page_id:
            print_warning("No parent page available. Skipping create/update tests.")
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Test create_page (under a page)
        properties = {
            "title": {
                "title": [
                    {"text": {"content": f"Integration Test Page - {timestamp}"}}
                ]
            },
        }
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"text": {"content": "This page was created by the Notion integration test suite."}}
                    ]
                },
            },
        ]

        result = self.run_test(
            "create_page",
            NotionAppLibrary.create_page,
            user_id=self.user_id,
            parent_id=parent_page_id,
            parent_type="page_id",
            properties=properties,
            children=children,
            workspace_id=self.workspace_id,
        )

        if result.get('status') == 'success':
            self.created_page_id = result.get('page', {}).get('id')
            print_info(f"Created page ID: {self.created_page_id}")
        else:
            print_warning("create_page failed; skipping update_page and append_to_page.")
            return

        # Test update_page (rename the created page)
        updated_properties = {
            "title": {
                "title": [
                    {"text": {"content": f"Updated Test Page - {timestamp}"}}
                ]
            },
        }
        result = self.run_test(
            "update_page",
            NotionAppLibrary.update_page,
            user_id=self.user_id,
            page_id=self.created_page_id,
            properties=updated_properties,
            workspace_id=self.workspace_id,
        )

        # Test append_to_page
        append_children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {"text": {"content": "Appended Section"}}
                    ]
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"text": {"content": f"Appended at {timestamp} by integration tests."}}
                    ]
                },
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"text": {"content": "Bullet item from test"}}
                    ]
                },
            },
        ]

        result = self.run_test(
            "append_to_page",
            NotionAppLibrary.append_to_page,
            user_id=self.user_id,
            page_id=self.created_page_id,
            children=append_children,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            blocks = result.get('blocks', [])
            print_info(f"Appended {len(blocks)} blocks")

        # Verify by reading the page content back
        result = self.run_test(
            "get_page_content (verify append)",
            NotionAppLibrary.get_page_content,
            user_id=self.user_id,
            page_id=self.created_page_id,
            workspace_id=self.workspace_id,
        )
        if result.get('status') == 'success':
            blocks = result.get('blocks', [])
            print_info(f"Page now has {len(blocks)} blocks total")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self):
        """Clean up any created test data by archiving pages."""
        print_section("CLEANUP")

        if self.created_page_id:
            print_info(f"Archiving test page: {self.created_page_id}")
            # Archive the page by setting archived=True via update_page properties
            # Notion API supports archiving via PATCH /pages/{id} with {"archived": true}
            cred = NotionAppLibrary.get_credentials(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
            )
            if cred:
                import requests
                url = f"https://api.notion.com/v1/pages/{self.created_page_id}"
                headers = {
                    "Authorization": f"Bearer {cred.token}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                }
                response = requests.patch(url, headers=headers, json={"archived": True})
                if response.status_code == 200:
                    print_success("Test page archived (deleted)")
                else:
                    print_error(f"Failed to archive test page: {response.status_code} - {response.text}")
            else:
                print_error("Could not get credential for cleanup")
        else:
            print_info("No test pages to clean up")

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
                print(f"    {Colors.GREEN}PASS{Colors.END} {name}")
            elif result == 'FAIL':
                print(f"    {Colors.RED}FAIL{Colors.END} {name}")
            else:
                print(f"    {Colors.YELLOW}ERR {Colors.END} {name}")


def list_credentials():
    """List all stored Notion credentials."""
    print_header("STORED NOTION CREDENTIALS")

    NotionAppLibrary.initialize()
    cred_store = NotionAppLibrary.get_credential_store()

    # Access internal credentials dict to list all users
    all_credentials = []
    for user_id, creds in cred_store.credentials.items():
        all_credentials.extend(creds)

    if not all_credentials:
        print_warning("No Notion credentials found.")
        print_info("Please authenticate via the CraftOS control panel first.")
        return None, None

    print(f"\nFound {len(all_credentials)} credential(s):\n")

    for i, cred in enumerate(all_credentials, 1):
        print(f"  [{i}] User ID: {cred.user_id}")
        print(f"      Workspace ID: {cred.workspace_id}")
        print(f"      Workspace Name: {cred.workspace_name}")
        print(f"      Token prefix: {cred.token[:12]}...")
        print()

    return all_credentials[0].user_id, all_credentials[0].workspace_id


def main():
    parser = argparse.ArgumentParser(description='Test Notion API integration')
    parser.add_argument('--user-id', type=str, help='CraftOS user ID')
    parser.add_argument('--workspace-id', type=str, help='Notion workspace ID')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--skip-create', action='store_true', help='Skip tests that create pages')
    parser.add_argument('--only', type=str, help='Only run specific test group (init, search, page, database, create)')
    args = parser.parse_args()

    print_header("NOTION EXTERNAL LIBRARY TEST SUITE")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize the library
    NotionAppLibrary.initialize()
    print_success("NotionAppLibrary initialized")

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
    if not NotionAppLibrary.validate_connection(user_id=user_id, workspace_id=workspace_id):
        print_error("Invalid credentials or no connection found.")
        return

    print_success("Credential validation passed")

    # Create tester
    tester = NotionTester(user_id=user_id, workspace_id=workspace_id)

    try:
        # Run tests based on --only flag or all
        test_groups = {
            'init': tester.test_initialization,
            'search': tester.test_search_operations,
        }

        if args.only:
            if args.only in test_groups:
                test_groups[args.only]()
            elif args.only == 'page':
                tester.test_page_read_operations()
            elif args.only == 'database':
                tester.test_database_read_operations()
            elif args.only == 'create':
                if args.skip_create:
                    print_warning("--skip-create and --only create are contradictory. Skipping.")
                else:
                    tester.test_create_operations()
            else:
                print_error(f"Unknown test group: {args.only}")
                print_info("Available: init, search, page, database, create")
                return
        else:
            # Run all tests
            tester.test_initialization()
            tester.test_search_operations()
            page_id = tester.test_page_read_operations()
            tester.test_database_read_operations()

            if not args.skip_create:
                tester.test_create_operations(parent_page_id=page_id)

    finally:
        # Cleanup
        if not args.skip_create:
            tester.cleanup()

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()
