from typing import Optional, Dict, Any, List
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.notion.credentials import NotionCredential
from core.external_libraries.notion.helpers.notion_helpers import (
    search_notion,
    get_page,
    get_database,
    query_database,
    create_page,
    update_page,
    get_block_children,
    append_block_children,
)


class NotionAppLibrary(ExternalAppLibrary):
    _name = "Notion"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the Notion library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=NotionCredential,
            persistence_file="notion_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("NotionAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, workspace_id: Optional[str] = None) -> bool:
        """
        Returns True if a Notion credential exists for the given
        user_id and optional workspace_id, False otherwise.
        """
        cred_store = cls.get_credential_store()
        if workspace_id:
            credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
        else:
            credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[NotionCredential]:
        """
        Retrieve the Notion credential for the given user_id and optional workspace_id.
        Returns the credential if found, None otherwise.
        """
        cred_store = cls.get_credential_store()
        if workspace_id:
            credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
        else:
            credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    # --------------------------------------------------
    # Search
    # --------------------------------------------------
    @classmethod
    def search(
        cls,
        user_id: str,
        query: str,
        filter_type: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search Notion for pages and databases matching the query.

        Args:
            user_id: The user ID
            query: Search query string
            filter_type: Optional filter - "page" or "database"
            workspace_id: Optional workspace ID to use specific credentials

        Returns:
            Dict with status and results
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            results = search_notion(
                token=credential.token,
                query=query,
                filter_type=filter_type,
            )

            return {"status": "success", "results": results}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Page
    # --------------------------------------------------
    @classmethod
    def get_page(
        cls,
        user_id: str,
        page_id: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a Notion page by ID.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            page = get_page(token=credential.token, page_id=page_id)

            if "error" in page:
                return {"status": "error", "details": page}

            return {"status": "success", "page": page}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Database
    # --------------------------------------------------
    @classmethod
    def get_database(
        cls,
        user_id: str,
        database_id: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a Notion database schema by ID.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            database = get_database(token=credential.token, database_id=database_id)

            if "error" in database:
                return {"status": "error", "details": database}

            return {"status": "success", "database": database}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Query Database
    # --------------------------------------------------
    @classmethod
    def query_database(
        cls,
        user_id: str,
        database_id: str,
        filter_obj: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query a Notion database with optional filters and sorts.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            results = query_database(
                token=credential.token,
                database_id=database_id,
                filter_obj=filter_obj,
                sorts=sorts,
            )

            if "error" in results:
                return {"status": "error", "details": results}

            return {"status": "success", "results": results.get("results", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Create Page
    # --------------------------------------------------
    @classmethod
    def create_page(
        cls,
        user_id: str,
        parent_id: str,
        parent_type: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict[str, Any]]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new page in Notion.

        Args:
            user_id: The user ID
            parent_id: ID of the parent page or database
            parent_type: "page_id" or "database_id"
            properties: Page properties (title, etc.)
            children: Optional list of block children
            workspace_id: Optional workspace ID

        Returns:
            Dict with status and created page
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            page = create_page(
                token=credential.token,
                parent_id=parent_id,
                parent_type=parent_type,
                properties=properties,
                children=children,
            )

            if "error" in page:
                return {"status": "error", "details": page}

            return {"status": "success", "page": page}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Update Page
    # --------------------------------------------------
    @classmethod
    def update_page(
        cls,
        user_id: str,
        page_id: str,
        properties: Dict[str, Any],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update page properties.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            page = update_page(
                token=credential.token,
                page_id=page_id,
                properties=properties,
            )

            if "error" in page:
                return {"status": "error", "details": page}

            return {"status": "success", "page": page}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Page Content (Blocks)
    # --------------------------------------------------
    @classmethod
    def get_page_content(
        cls,
        user_id: str,
        page_id: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the content blocks of a page.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            blocks = get_block_children(token=credential.token, block_id=page_id)

            if "error" in blocks:
                return {"status": "error", "details": blocks}

            return {"status": "success", "blocks": blocks.get("results", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Append Content to Page
    # --------------------------------------------------
    @classmethod
    def append_to_page(
        cls,
        user_id: str,
        page_id: str,
        children: List[Dict[str, Any]],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Append content blocks to a page.

        Args:
            user_id: The user ID
            page_id: The page ID to append to
            children: List of block objects to append
            workspace_id: Optional workspace ID

        Returns:
            Dict with status and appended blocks
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Notion credential found."}

            result = append_block_children(
                token=credential.token,
                block_id=page_id,
                children=children,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "blocks": result.get("results", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
