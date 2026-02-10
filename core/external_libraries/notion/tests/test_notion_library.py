"""
Tests for Notion external library.

Uses pytest with unittest.mock to mock the Notion API helper functions,
allowing all library methods to be tested without making real API calls.

Usage:
    pytest core/external_libraries/notion/tests/test_notion_library.py -v
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from core.external_libraries.notion.credentials import NotionCredential
from core.external_libraries.notion.external_app_library import NotionAppLibrary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_library():
    """Reset NotionAppLibrary state before each test."""
    NotionAppLibrary._initialized = False
    NotionAppLibrary._credential_store = None
    yield
    NotionAppLibrary._initialized = False
    NotionAppLibrary._credential_store = None


@pytest.fixture
def mock_credential():
    """Return a sample Notion credential."""
    return NotionCredential(
        user_id="test_user",
        workspace_id="ws_abc123",
        workspace_name="Test Workspace",
        token="ntn_test_token_abc123",
    )


@pytest.fixture
def second_credential():
    """Return a second Notion credential for a different workspace."""
    return NotionCredential(
        user_id="test_user",
        workspace_id="ws_def456",
        workspace_name="Second Workspace",
        token="ntn_test_token_def456",
    )


@pytest.fixture
def initialized_library(mock_credential):
    """Initialize the library and inject a mock credential store."""
    NotionAppLibrary.initialize()
    NotionAppLibrary.get_credential_store().add(mock_credential)
    return NotionAppLibrary


# ---------------------------------------------------------------------------
# Initialization & Credential Tests
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_initialize(self):
        assert not NotionAppLibrary._initialized
        NotionAppLibrary.initialize()
        assert NotionAppLibrary._initialized
        assert NotionAppLibrary._credential_store is not None

    def test_initialize_idempotent(self):
        NotionAppLibrary.initialize()
        store = NotionAppLibrary._credential_store
        NotionAppLibrary.initialize()
        assert NotionAppLibrary._credential_store is store

    def test_get_name(self):
        assert NotionAppLibrary.get_name() == "Notion"

    def test_get_credential_store_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            NotionAppLibrary.get_credential_store()

    def test_get_credential_store_after_init(self):
        NotionAppLibrary.initialize()
        store = NotionAppLibrary.get_credential_store()
        assert store is not None


class TestValidateConnection:

    def test_validate_no_credentials(self):
        NotionAppLibrary.initialize()
        assert NotionAppLibrary.validate_connection(user_id="nonexistent") is False

    def test_validate_with_credentials(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(user_id="test_user") is True

    def test_validate_with_wrong_user(self, initialized_library):
        assert initialized_library.validate_connection(user_id="other_user") is False

    def test_validate_with_workspace_id(self, initialized_library, mock_credential):
        assert initialized_library.validate_connection(
            user_id="test_user",
            workspace_id="ws_abc123",
        ) is True

    def test_validate_with_wrong_workspace_id(self, initialized_library):
        assert initialized_library.validate_connection(
            user_id="test_user",
            workspace_id="ws_wrong",
        ) is False


class TestGetCredentials:

    def test_get_credentials_found(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        assert cred.user_id == "test_user"
        assert cred.token == "ntn_test_token_abc123"
        assert cred.workspace_id == "ws_abc123"
        assert cred.workspace_name == "Test Workspace"

    def test_get_credentials_not_found(self, initialized_library):
        cred = initialized_library.get_credentials(user_id="nonexistent")
        assert cred is None

    def test_get_credentials_with_workspace_id(self, initialized_library, mock_credential):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            workspace_id="ws_abc123",
        )
        assert cred is not None
        assert cred.workspace_id == "ws_abc123"

    def test_get_credentials_with_wrong_workspace_id(self, initialized_library):
        cred = initialized_library.get_credentials(
            user_id="test_user",
            workspace_id="ws_nonexistent",
        )
        assert cred is None

    def test_get_credentials_returns_first_when_multiple(
        self, initialized_library, mock_credential, second_credential
    ):
        """When multiple credentials exist, get_credentials returns the first."""
        initialized_library.get_credential_store().add(second_credential)
        cred = initialized_library.get_credentials(user_id="test_user")
        assert cred is not None
        # Should return the first credential added
        assert cred.workspace_id == "ws_abc123"

    def test_get_credentials_selects_by_workspace_id_from_multiple(
        self, initialized_library, mock_credential, second_credential
    ):
        """When multiple credentials exist, workspace_id selects the right one."""
        initialized_library.get_credential_store().add(second_credential)
        cred = initialized_library.get_credentials(
            user_id="test_user",
            workspace_id="ws_def456",
        )
        assert cred is not None
        assert cred.workspace_id == "ws_def456"
        assert cred.token == "ntn_test_token_def456"


# ---------------------------------------------------------------------------
# Search Tests
# ---------------------------------------------------------------------------

class TestSearch:

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_success(self, mock_search, initialized_library):
        mock_search.return_value = [
            {"object": "page", "id": "page-1", "properties": {"title": "My Page"}},
            {"object": "database", "id": "db-1", "title": [{"text": {"content": "My DB"}}]},
        ]

        result = initialized_library.search(
            user_id="test_user",
            query="test query",
        )

        assert result["status"] == "success"
        assert len(result["results"]) == 2
        mock_search.assert_called_once_with(
            token="ntn_test_token_abc123",
            query="test query",
            filter_type=None,
        )

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_with_filter_type(self, mock_search, initialized_library):
        mock_search.return_value = [
            {"object": "page", "id": "page-1"},
        ]

        result = initialized_library.search(
            user_id="test_user",
            query="test",
            filter_type="page",
        )

        assert result["status"] == "success"
        mock_search.assert_called_once_with(
            token="ntn_test_token_abc123",
            query="test",
            filter_type="page",
        )

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_with_database_filter(self, mock_search, initialized_library):
        mock_search.return_value = [
            {"object": "database", "id": "db-1"},
        ]

        result = initialized_library.search(
            user_id="test_user",
            query="my db",
            filter_type="database",
        )

        assert result["status"] == "success"
        mock_search.assert_called_once_with(
            token="ntn_test_token_abc123",
            query="my db",
            filter_type="database",
        )

    def test_search_no_credential(self, initialized_library):
        result = initialized_library.search(
            user_id="nonexistent",
            query="anything",
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_empty_results(self, mock_search, initialized_library):
        mock_search.return_value = []

        result = initialized_library.search(
            user_id="test_user",
            query="nonexistent query",
        )

        assert result["status"] == "success"
        assert result["results"] == []

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_exception(self, mock_search, initialized_library):
        mock_search.side_effect = Exception("Network error")

        result = initialized_library.search(
            user_id="test_user",
            query="test",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Network error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_uses_workspace_credential(
        self, mock_search, initialized_library, second_credential
    ):
        """Search with workspace_id uses the correct credential token."""
        initialized_library.get_credential_store().add(second_credential)
        mock_search.return_value = []

        result = initialized_library.search(
            user_id="test_user",
            query="test",
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_search.assert_called_once_with(
            token="ntn_test_token_def456",
            query="test",
            filter_type=None,
        )


# ---------------------------------------------------------------------------
# Get Page Tests
# ---------------------------------------------------------------------------

class TestGetPage:

    @patch("core.external_libraries.notion.external_app_library.get_page")
    def test_get_page_success(self, mock_get_page, initialized_library):
        mock_get_page.return_value = {
            "object": "page",
            "id": "page-123",
            "properties": {
                "title": {
                    "title": [{"text": {"content": "My Page"}}]
                }
            },
        }

        result = initialized_library.get_page(
            user_id="test_user",
            page_id="page-123",
        )

        assert result["status"] == "success"
        assert result["page"]["id"] == "page-123"
        assert result["page"]["object"] == "page"
        mock_get_page.assert_called_once_with(
            token="ntn_test_token_abc123",
            page_id="page-123",
        )

    def test_get_page_no_credential(self, initialized_library):
        result = initialized_library.get_page(
            user_id="nonexistent",
            page_id="page-123",
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_page")
    def test_get_page_not_found(self, mock_get_page, initialized_library):
        mock_get_page.return_value = {
            "error": {
                "status": 404,
                "code": "object_not_found",
                "message": "Could not find page with ID: page-999.",
            }
        }

        result = initialized_library.get_page(
            user_id="test_user",
            page_id="page-999",
        )

        assert result["status"] == "error"
        assert "details" in result
        assert "error" in result["details"]

    @patch("core.external_libraries.notion.external_app_library.get_page")
    def test_get_page_unauthorized(self, mock_get_page, initialized_library):
        mock_get_page.return_value = {
            "error": {
                "status": 401,
                "code": "unauthorized",
                "message": "API token is invalid.",
            }
        }

        result = initialized_library.get_page(
            user_id="test_user",
            page_id="page-123",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.get_page")
    def test_get_page_exception(self, mock_get_page, initialized_library):
        mock_get_page.side_effect = Exception("Connection timeout")

        result = initialized_library.get_page(
            user_id="test_user",
            page_id="page-123",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Connection timeout" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_page")
    def test_get_page_with_workspace_id(
        self, mock_get_page, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_get_page.return_value = {"object": "page", "id": "page-123"}

        result = initialized_library.get_page(
            user_id="test_user",
            page_id="page-123",
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_get_page.assert_called_once_with(
            token="ntn_test_token_def456",
            page_id="page-123",
        )


# ---------------------------------------------------------------------------
# Get Database Tests
# ---------------------------------------------------------------------------

class TestGetDatabase:

    @patch("core.external_libraries.notion.external_app_library.get_database")
    def test_get_database_success(self, mock_get_db, initialized_library):
        mock_get_db.return_value = {
            "object": "database",
            "id": "db-123",
            "title": [{"text": {"content": "Tasks DB"}}],
            "properties": {
                "Name": {"id": "title", "type": "title"},
                "Status": {"id": "abc", "type": "select"},
            },
        }

        result = initialized_library.get_database(
            user_id="test_user",
            database_id="db-123",
        )

        assert result["status"] == "success"
        assert result["database"]["id"] == "db-123"
        assert result["database"]["object"] == "database"
        assert "properties" in result["database"]
        mock_get_db.assert_called_once_with(
            token="ntn_test_token_abc123",
            database_id="db-123",
        )

    def test_get_database_no_credential(self, initialized_library):
        result = initialized_library.get_database(
            user_id="nonexistent",
            database_id="db-123",
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_database")
    def test_get_database_not_found(self, mock_get_db, initialized_library):
        mock_get_db.return_value = {
            "error": {
                "status": 404,
                "code": "object_not_found",
                "message": "Could not find database with ID: db-999.",
            }
        }

        result = initialized_library.get_database(
            user_id="test_user",
            database_id="db-999",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.get_database")
    def test_get_database_exception(self, mock_get_db, initialized_library):
        mock_get_db.side_effect = Exception("API unavailable")

        result = initialized_library.get_database(
            user_id="test_user",
            database_id="db-123",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_database")
    def test_get_database_with_workspace_id(
        self, mock_get_db, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_get_db.return_value = {"object": "database", "id": "db-123"}

        result = initialized_library.get_database(
            user_id="test_user",
            database_id="db-123",
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_get_db.assert_called_once_with(
            token="ntn_test_token_def456",
            database_id="db-123",
        )


# ---------------------------------------------------------------------------
# Query Database Tests
# ---------------------------------------------------------------------------

class TestQueryDatabase:

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_success(self, mock_query, initialized_library):
        mock_query.return_value = {
            "results": [
                {"object": "page", "id": "page-1", "properties": {}},
                {"object": "page", "id": "page-2", "properties": {}},
            ],
            "has_more": False,
        }

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
        )

        assert result["status"] == "success"
        assert len(result["results"]) == 2
        mock_query.assert_called_once_with(
            token="ntn_test_token_abc123",
            database_id="db-123",
            filter_obj=None,
            sorts=None,
        )

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_with_filter(self, mock_query, initialized_library):
        filter_obj = {
            "property": "Status",
            "select": {"equals": "Done"},
        }
        mock_query.return_value = {
            "results": [{"object": "page", "id": "page-1"}],
            "has_more": False,
        }

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
            filter_obj=filter_obj,
        )

        assert result["status"] == "success"
        assert len(result["results"]) == 1
        mock_query.assert_called_once_with(
            token="ntn_test_token_abc123",
            database_id="db-123",
            filter_obj=filter_obj,
            sorts=None,
        )

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_with_sorts(self, mock_query, initialized_library):
        sorts = [{"property": "Created", "direction": "descending"}]
        mock_query.return_value = {
            "results": [{"object": "page", "id": "page-1"}],
            "has_more": False,
        }

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
            sorts=sorts,
        )

        assert result["status"] == "success"
        mock_query.assert_called_once_with(
            token="ntn_test_token_abc123",
            database_id="db-123",
            filter_obj=None,
            sorts=sorts,
        )

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_with_filter_and_sorts(self, mock_query, initialized_library):
        filter_obj = {"property": "Priority", "select": {"equals": "High"}}
        sorts = [{"property": "Due Date", "direction": "ascending"}]
        mock_query.return_value = {
            "results": [{"object": "page", "id": "page-3"}],
            "has_more": False,
        }

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
            filter_obj=filter_obj,
            sorts=sorts,
        )

        assert result["status"] == "success"
        mock_query.assert_called_once_with(
            token="ntn_test_token_abc123",
            database_id="db-123",
            filter_obj=filter_obj,
            sorts=sorts,
        )

    def test_query_database_no_credential(self, initialized_library):
        result = initialized_library.query_database(
            user_id="nonexistent",
            database_id="db-123",
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_empty_results(self, mock_query, initialized_library):
        mock_query.return_value = {
            "results": [],
            "has_more": False,
        }

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
        )

        assert result["status"] == "success"
        assert result["results"] == []

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_api_error(self, mock_query, initialized_library):
        mock_query.return_value = {
            "error": {
                "status": 400,
                "code": "validation_error",
                "message": "Invalid filter property.",
            }
        }

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
            filter_obj={"invalid": "filter"},
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_exception(self, mock_query, initialized_library):
        mock_query.side_effect = Exception("Timeout")

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_with_workspace_id(
        self, mock_query, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_query.return_value = {"results": [], "has_more": False}

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-123",
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_query.assert_called_once_with(
            token="ntn_test_token_def456",
            database_id="db-123",
            filter_obj=None,
            sorts=None,
        )


# ---------------------------------------------------------------------------
# Create Page Tests
# ---------------------------------------------------------------------------

class TestCreatePage:

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_in_database_success(self, mock_create, initialized_library):
        mock_create.return_value = {
            "object": "page",
            "id": "new-page-1",
            "parent": {"database_id": "db-123"},
            "properties": {
                "Name": {"title": [{"text": {"content": "New Task"}}]},
            },
        }

        properties = {
            "Name": {"title": [{"text": {"content": "New Task"}}]},
        }

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="db-123",
            parent_type="database_id",
            properties=properties,
        )

        assert result["status"] == "success"
        assert result["page"]["id"] == "new-page-1"
        mock_create.assert_called_once_with(
            token="ntn_test_token_abc123",
            parent_id="db-123",
            parent_type="database_id",
            properties=properties,
            children=None,
        )

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_under_page_success(self, mock_create, initialized_library):
        mock_create.return_value = {
            "object": "page",
            "id": "new-page-2",
            "parent": {"page_id": "parent-page-1"},
        }

        properties = {
            "title": {"title": [{"text": {"content": "Sub Page"}}]},
        }

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="parent-page-1",
            parent_type="page_id",
            properties=properties,
        )

        assert result["status"] == "success"
        assert result["page"]["id"] == "new-page-2"
        mock_create.assert_called_once_with(
            token="ntn_test_token_abc123",
            parent_id="parent-page-1",
            parent_type="page_id",
            properties=properties,
            children=None,
        )

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_with_children(self, mock_create, initialized_library):
        mock_create.return_value = {
            "object": "page",
            "id": "new-page-3",
        }

        properties = {
            "title": {"title": [{"text": {"content": "Page With Content"}}]},
        }
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "Hello World"}}]
                },
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "Section Title"}}]
                },
            },
        ]

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="parent-page-1",
            parent_type="page_id",
            properties=properties,
            children=children,
        )

        assert result["status"] == "success"
        mock_create.assert_called_once_with(
            token="ntn_test_token_abc123",
            parent_id="parent-page-1",
            parent_type="page_id",
            properties=properties,
            children=children,
        )

    def test_create_page_no_credential(self, initialized_library):
        result = initialized_library.create_page(
            user_id="nonexistent",
            parent_id="db-123",
            parent_type="database_id",
            properties={"Name": {"title": [{"text": {"content": "Test"}}]}},
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_api_error(self, mock_create, initialized_library):
        mock_create.return_value = {
            "error": {
                "status": 400,
                "code": "validation_error",
                "message": "Title is not a property that exists.",
            }
        }

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="db-123",
            parent_type="database_id",
            properties={"invalid": "property"},
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_exception(self, mock_create, initialized_library):
        mock_create.side_effect = Exception("Server error")

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="db-123",
            parent_type="database_id",
            properties={},
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_with_workspace_id(
        self, mock_create, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_create.return_value = {"object": "page", "id": "new-page-4"}

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="db-123",
            parent_type="database_id",
            properties={},
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_create.assert_called_once_with(
            token="ntn_test_token_def456",
            parent_id="db-123",
            parent_type="database_id",
            properties={},
            children=None,
        )


# ---------------------------------------------------------------------------
# Update Page Tests
# ---------------------------------------------------------------------------

class TestUpdatePage:

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_success(self, mock_update, initialized_library):
        mock_update.return_value = {
            "object": "page",
            "id": "page-123",
            "properties": {
                "Status": {"select": {"name": "Done"}},
            },
        }

        properties = {"Status": {"select": {"name": "Done"}}}

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-123",
            properties=properties,
        )

        assert result["status"] == "success"
        assert result["page"]["id"] == "page-123"
        mock_update.assert_called_once_with(
            token="ntn_test_token_abc123",
            page_id="page-123",
            properties=properties,
        )

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_multiple_properties(self, mock_update, initialized_library):
        mock_update.return_value = {
            "object": "page",
            "id": "page-123",
            "properties": {
                "Status": {"select": {"name": "In Progress"}},
                "Priority": {"select": {"name": "High"}},
                "Assignee": {"people": [{"id": "user-1"}]},
            },
        }

        properties = {
            "Status": {"select": {"name": "In Progress"}},
            "Priority": {"select": {"name": "High"}},
            "Assignee": {"people": [{"id": "user-1"}]},
        }

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-123",
            properties=properties,
        )

        assert result["status"] == "success"
        mock_update.assert_called_once_with(
            token="ntn_test_token_abc123",
            page_id="page-123",
            properties=properties,
        )

    def test_update_page_no_credential(self, initialized_library):
        result = initialized_library.update_page(
            user_id="nonexistent",
            page_id="page-123",
            properties={"Status": {"select": {"name": "Done"}}},
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_not_found(self, mock_update, initialized_library):
        mock_update.return_value = {
            "error": {
                "status": 404,
                "code": "object_not_found",
                "message": "Could not find page.",
            }
        }

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-999",
            properties={"Status": {"select": {"name": "Done"}}},
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_validation_error(self, mock_update, initialized_library):
        mock_update.return_value = {
            "error": {
                "status": 400,
                "code": "validation_error",
                "message": "Property does not exist.",
            }
        }

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-123",
            properties={"NonExistentProp": {"text": "value"}},
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_exception(self, mock_update, initialized_library):
        mock_update.side_effect = Exception("Rate limited")

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-123",
            properties={},
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_with_workspace_id(
        self, mock_update, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_update.return_value = {"object": "page", "id": "page-123"}

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-123",
            properties={},
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_update.assert_called_once_with(
            token="ntn_test_token_def456",
            page_id="page-123",
            properties={},
        )


# ---------------------------------------------------------------------------
# Get Page Content (Block Children) Tests
# ---------------------------------------------------------------------------

class TestGetPageContent:

    @patch("core.external_libraries.notion.external_app_library.get_block_children")
    def test_get_page_content_success(self, mock_blocks, initialized_library):
        mock_blocks.return_value = {
            "results": [
                {
                    "object": "block",
                    "id": "block-1",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": "Hello"}}]
                    },
                },
                {
                    "object": "block",
                    "id": "block-2",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"text": {"content": "Title"}}]
                    },
                },
            ],
            "has_more": False,
        }

        result = initialized_library.get_page_content(
            user_id="test_user",
            page_id="page-123",
        )

        assert result["status"] == "success"
        assert len(result["blocks"]) == 2
        assert result["blocks"][0]["type"] == "paragraph"
        assert result["blocks"][1]["type"] == "heading_1"
        mock_blocks.assert_called_once_with(
            token="ntn_test_token_abc123",
            block_id="page-123",
        )

    def test_get_page_content_no_credential(self, initialized_library):
        result = initialized_library.get_page_content(
            user_id="nonexistent",
            page_id="page-123",
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_block_children")
    def test_get_page_content_empty(self, mock_blocks, initialized_library):
        mock_blocks.return_value = {
            "results": [],
            "has_more": False,
        }

        result = initialized_library.get_page_content(
            user_id="test_user",
            page_id="page-123",
        )

        assert result["status"] == "success"
        assert result["blocks"] == []

    @patch("core.external_libraries.notion.external_app_library.get_block_children")
    def test_get_page_content_api_error(self, mock_blocks, initialized_library):
        mock_blocks.return_value = {
            "error": {
                "status": 404,
                "code": "object_not_found",
                "message": "Could not find block.",
            }
        }

        result = initialized_library.get_page_content(
            user_id="test_user",
            page_id="page-999",
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.get_block_children")
    def test_get_page_content_exception(self, mock_blocks, initialized_library):
        mock_blocks.side_effect = Exception("Service unavailable")

        result = initialized_library.get_page_content(
            user_id="test_user",
            page_id="page-123",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_block_children")
    def test_get_page_content_with_workspace_id(
        self, mock_blocks, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_blocks.return_value = {"results": [], "has_more": False}

        result = initialized_library.get_page_content(
            user_id="test_user",
            page_id="page-123",
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_blocks.assert_called_once_with(
            token="ntn_test_token_def456",
            block_id="page-123",
        )


# ---------------------------------------------------------------------------
# Append to Page Tests
# ---------------------------------------------------------------------------

class TestAppendToPage:

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_success(self, mock_append, initialized_library):
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "New paragraph"}}]
                },
            },
        ]
        mock_append.return_value = {
            "results": children,
            "has_more": False,
        }

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-123",
            children=children,
        )

        assert result["status"] == "success"
        assert len(result["blocks"]) == 1
        mock_append.assert_called_once_with(
            token="ntn_test_token_abc123",
            block_id="page-123",
            children=children,
        )

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_multiple_blocks(self, mock_append, initialized_library):
        children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "New Section"}}]
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "Content here"}}]
                },
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": "Item 1"}}]
                },
            },
        ]
        mock_append.return_value = {
            "results": children,
            "has_more": False,
        }

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-123",
            children=children,
        )

        assert result["status"] == "success"
        assert len(result["blocks"]) == 3

    def test_append_to_page_no_credential(self, initialized_library):
        result = initialized_library.append_to_page(
            user_id="nonexistent",
            page_id="page-123",
            children=[{"type": "paragraph"}],
        )
        assert result["status"] == "error"
        assert "No valid Notion credential" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_api_error(self, mock_append, initialized_library):
        mock_append.return_value = {
            "error": {
                "status": 400,
                "code": "validation_error",
                "message": "Invalid block type.",
            }
        }

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-123",
            children=[{"type": "invalid_block_type"}],
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_page_not_found(self, mock_append, initialized_library):
        mock_append.return_value = {
            "error": {
                "status": 404,
                "code": "object_not_found",
                "message": "Could not find block with ID: page-999.",
            }
        }

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-999",
            children=[{"type": "paragraph"}],
        )

        assert result["status"] == "error"
        assert "details" in result

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_exception(self, mock_append, initialized_library):
        mock_append.side_effect = Exception("Connection reset")

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-123",
            children=[{"type": "paragraph"}],
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_with_workspace_id(
        self, mock_append, initialized_library, second_credential
    ):
        initialized_library.get_credential_store().add(second_credential)
        mock_append.return_value = {"results": [], "has_more": False}

        children = [{"type": "paragraph"}]

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-123",
            children=children,
            workspace_id="ws_def456",
        )

        assert result["status"] == "success"
        mock_append.assert_called_once_with(
            token="ntn_test_token_def456",
            block_id="page-123",
            children=children,
        )


# ---------------------------------------------------------------------------
# Notion Credential Model Tests
# ---------------------------------------------------------------------------

class TestNotionCredential:

    def test_credential_fields(self):
        cred = NotionCredential(
            user_id="u1",
            workspace_id="ws1",
            workspace_name="My Workspace",
            token="ntn_secret_abc",
        )
        assert cred.user_id == "u1"
        assert cred.workspace_id == "ws1"
        assert cred.workspace_name == "My Workspace"
        assert cred.token == "ntn_secret_abc"

    def test_credential_unique_keys(self):
        assert NotionCredential.UNIQUE_KEYS == ("user_id", "workspace_id")

    def test_credential_to_dict(self):
        cred = NotionCredential(
            user_id="u1",
            workspace_id="ws1",
            workspace_name="My Workspace",
            token="ntn_secret_abc",
        )
        d = cred.to_dict()
        assert d["user_id"] == "u1"
        assert d["workspace_id"] == "ws1"
        assert d["workspace_name"] == "My Workspace"
        assert d["token"] == "ntn_secret_abc"

    def test_credential_equality(self):
        cred1 = NotionCredential(
            user_id="u1",
            workspace_id="ws1",
            workspace_name="WS",
            token="tok",
        )
        cred2 = NotionCredential(
            user_id="u1",
            workspace_id="ws1",
            workspace_name="WS",
            token="tok",
        )
        assert cred1 == cred2

    def test_credential_inequality_different_workspace(self):
        cred1 = NotionCredential(
            user_id="u1",
            workspace_id="ws1",
            workspace_name="WS",
            token="tok",
        )
        cred2 = NotionCredential(
            user_id="u1",
            workspace_id="ws2",
            workspace_name="WS",
            token="tok",
        )
        assert cred1 != cred2


# ---------------------------------------------------------------------------
# Notion API Helpers Tests (unit-testing the helper functions directly)
# ---------------------------------------------------------------------------

class TestNotionHelpers:
    """Test the low-level Notion API helper functions with mocked requests."""

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_search_notion_success(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import search_notion

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"object": "page", "id": "p1"},
                {"object": "database", "id": "d1"},
            ]
        }
        mock_post.return_value = mock_response

        results = search_notion(token="test_token", query="meeting notes")

        assert len(results) == 2
        assert results[0]["id"] == "p1"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["query"] == "meeting notes"

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_search_notion_with_filter(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import search_notion

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response

        search_notion(token="test_token", query="q", filter_type="page")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["filter"] == {"property": "object", "value": "page"}

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_search_notion_invalid_filter_ignored(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import search_notion

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response

        search_notion(token="test_token", query="q", filter_type="invalid")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert "filter" not in payload

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_search_notion_api_error(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import search_notion

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "object": "error",
            "status": 401,
            "message": "Unauthorized",
        }
        mock_post.return_value = mock_response

        results = search_notion(token="bad_token", query="q")

        assert len(results) == 1
        assert "error" in results[0]

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_page_success(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_page

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"object": "page", "id": "page-1"}
        mock_get.return_value = mock_response

        result = get_page(token="test_token", page_id="page-1")

        assert result["id"] == "page-1"
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_page_not_found(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_page

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "object": "error",
            "status": 404,
            "message": "Not found",
        }
        mock_get.return_value = mock_response

        result = get_page(token="test_token", page_id="bad-id")

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_database_success(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_database

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "database",
            "id": "db-1",
            "properties": {},
        }
        mock_get.return_value = mock_response

        result = get_database(token="test_token", database_id="db-1")

        assert result["id"] == "db-1"
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_database_error(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_database

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"object": "error", "status": 404}
        mock_get.return_value = mock_response

        result = get_database(token="test_token", database_id="bad-id")

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_query_database_success(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import query_database

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"id": "row-1"}],
            "has_more": False,
        }
        mock_post.return_value = mock_response

        result = query_database(token="test_token", database_id="db-1")

        assert "results" in result
        assert len(result["results"]) == 1

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_query_database_with_filter_and_sorts(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import query_database

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "has_more": False}
        mock_post.return_value = mock_response

        filter_obj = {"property": "Status", "select": {"equals": "Done"}}
        sorts = [{"property": "Date", "direction": "ascending"}]

        query_database(
            token="test_token",
            database_id="db-1",
            filter_obj=filter_obj,
            sorts=sorts,
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["filter"] == filter_obj
        assert payload["sorts"] == sorts

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_query_database_error(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import query_database

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"object": "error", "status": 400}
        mock_post.return_value = mock_response

        result = query_database(token="test_token", database_id="db-1")

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_create_page_success(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import create_page

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"object": "page", "id": "new-page"}
        mock_post.return_value = mock_response

        result = create_page(
            token="test_token",
            parent_id="db-1",
            parent_type="database_id",
            properties={"Name": {"title": [{"text": {"content": "Test"}}]}},
        )

        assert result["id"] == "new-page"
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_create_page_with_children(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import create_page

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"object": "page", "id": "new-page"}
        mock_post.return_value = mock_response

        children = [{"type": "paragraph", "paragraph": {"rich_text": []}}]

        create_page(
            token="test_token",
            parent_id="p-1",
            parent_type="page_id",
            properties={},
            children=children,
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["children"] == children
        assert payload["parent"] == {"page_id": "p-1"}

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.post")
    def test_create_page_error(self, mock_post):
        from core.external_libraries.notion.helpers.notion_helpers import create_page

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"object": "error", "status": 400}
        mock_post.return_value = mock_response

        result = create_page(
            token="test_token",
            parent_id="db-1",
            parent_type="database_id",
            properties={},
        )

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.patch")
    def test_update_page_success(self, mock_patch):
        from core.external_libraries.notion.helpers.notion_helpers import update_page

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"object": "page", "id": "page-1"}
        mock_patch.return_value = mock_response

        result = update_page(
            token="test_token",
            page_id="page-1",
            properties={"Status": {"select": {"name": "Done"}}},
        )

        assert result["id"] == "page-1"
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.patch")
    def test_update_page_error(self, mock_patch):
        from core.external_libraries.notion.helpers.notion_helpers import update_page

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"object": "error", "status": 400}
        mock_patch.return_value = mock_response

        result = update_page(
            token="test_token",
            page_id="page-1",
            properties={},
        )

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_block_children_success(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_block_children

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"object": "block", "id": "b1", "type": "paragraph"}],
            "has_more": False,
        }
        mock_get.return_value = mock_response

        result = get_block_children(token="test_token", block_id="page-1")

        assert len(result["results"]) == 1
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_block_children_error(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_block_children

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"object": "error", "status": 404}
        mock_get.return_value = mock_response

        result = get_block_children(token="test_token", block_id="bad-id")

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.patch")
    def test_append_block_children_success(self, mock_patch):
        from core.external_libraries.notion.helpers.notion_helpers import append_block_children

        children = [{"type": "paragraph", "paragraph": {"rich_text": []}}]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": children}
        mock_patch.return_value = mock_response

        result = append_block_children(
            token="test_token", block_id="page-1", children=children
        )

        assert "results" in result
        assert "error" not in result
        call_kwargs = mock_patch.call_args
        assert call_kwargs[1]["json"]["children"] == children

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.patch")
    def test_append_block_children_error(self, mock_patch):
        from core.external_libraries.notion.helpers.notion_helpers import append_block_children

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"object": "error", "status": 400}
        mock_patch.return_value = mock_response

        result = append_block_children(
            token="test_token", block_id="page-1", children=[]
        )

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.delete")
    def test_delete_block_success(self, mock_delete):
        from core.external_libraries.notion.helpers.notion_helpers import delete_block

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "block",
            "id": "block-1",
            "archived": True,
        }
        mock_delete.return_value = mock_response

        result = delete_block(token="test_token", block_id="block-1")

        assert result["id"] == "block-1"
        assert result["archived"] is True
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.delete")
    def test_delete_block_error(self, mock_delete):
        from core.external_libraries.notion.helpers.notion_helpers import delete_block

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"object": "error", "status": 404}
        mock_delete.return_value = mock_response

        result = delete_block(token="test_token", block_id="bad-id")

        assert "error" in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_user_success(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_user

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "user",
            "id": "user-1",
            "name": "Bot User",
            "type": "bot",
        }
        mock_get.return_value = mock_response

        result = get_user(token="test_token")

        assert result["id"] == "user-1"
        assert result["name"] == "Bot User"
        assert "error" not in result

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_user_with_specific_id(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_user

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "user",
            "id": "user-42",
            "name": "John",
        }
        mock_get.return_value = mock_response

        result = get_user(token="test_token", user_id="user-42")

        assert result["id"] == "user-42"
        # Verify the URL contains the specific user_id
        call_args = mock_get.call_args
        assert "user-42" in call_args[0][0]

    @patch("core.external_libraries.notion.helpers.notion_helpers.requests.get")
    def test_get_user_error(self, mock_get):
        from core.external_libraries.notion.helpers.notion_helpers import get_user

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"object": "error", "status": 401}
        mock_get.return_value = mock_response

        result = get_user(token="bad_token")

        assert "error" in result

    def test_get_headers(self):
        from core.external_libraries.notion.helpers.notion_helpers import _get_headers

        headers = _get_headers("my_token")

        assert headers["Authorization"] == "Bearer my_token"
        assert headers["Content-Type"] == "application/json"
        assert headers["Notion-Version"] == "2022-06-28"


# ---------------------------------------------------------------------------
# Edge Cases & Error Handling Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch("core.external_libraries.notion.external_app_library.search_notion")
    def test_search_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Network error")

        result = initialized_library.search(
            user_id="test_user",
            query="test",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_page")
    def test_get_page_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("DNS failure")

        result = initialized_library.get_page(
            user_id="test_user",
            page_id="page-1",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_database")
    def test_get_database_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("SSL error")

        result = initialized_library.get_database(
            user_id="test_user",
            database_id="db-1",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.query_database")
    def test_query_database_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Timeout")

        result = initialized_library.query_database(
            user_id="test_user",
            database_id="db-1",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.create_page")
    def test_create_page_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Server 500")

        result = initialized_library.create_page(
            user_id="test_user",
            parent_id="db-1",
            parent_type="database_id",
            properties={},
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.update_page")
    def test_update_page_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Rate limited")

        result = initialized_library.update_page(
            user_id="test_user",
            page_id="page-1",
            properties={},
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.get_block_children")
    def test_get_page_content_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Service unavailable")

        result = initialized_library.get_page_content(
            user_id="test_user",
            page_id="page-1",
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    @patch("core.external_libraries.notion.external_app_library.append_block_children")
    def test_append_to_page_handles_exception(self, mock_fn, initialized_library):
        mock_fn.side_effect = Exception("Connection reset by peer")

        result = initialized_library.append_to_page(
            user_id="test_user",
            page_id="page-1",
            children=[{"type": "paragraph"}],
        )

        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    def test_all_methods_fail_before_initialization(self):
        """All credential-dependent methods should raise RuntimeError before init."""
        with pytest.raises(RuntimeError, match="not initialized"):
            NotionAppLibrary.get_credential_store()

    def test_search_not_initialized(self):
        """search() catches the RuntimeError and returns an error dict."""
        result = NotionAppLibrary.search(user_id="test_user", query="test")
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "not initialized" in result["reason"]

    def test_get_page_not_initialized(self):
        result = NotionAppLibrary.get_page(user_id="test_user", page_id="p1")
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_get_database_not_initialized(self):
        result = NotionAppLibrary.get_database(user_id="test_user", database_id="db1")
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_query_database_not_initialized(self):
        result = NotionAppLibrary.query_database(user_id="test_user", database_id="db1")
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_create_page_not_initialized(self):
        result = NotionAppLibrary.create_page(
            user_id="test_user",
            parent_id="p1",
            parent_type="page_id",
            properties={},
        )
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_update_page_not_initialized(self):
        result = NotionAppLibrary.update_page(
            user_id="test_user",
            page_id="p1",
            properties={},
        )
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_get_page_content_not_initialized(self):
        result = NotionAppLibrary.get_page_content(user_id="test_user", page_id="p1")
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]

    def test_append_to_page_not_initialized(self):
        result = NotionAppLibrary.append_to_page(
            user_id="test_user",
            page_id="p1",
            children=[],
        )
        assert result["status"] == "error"
        assert "not initialized" in result["reason"]
