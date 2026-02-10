"""
Notion API helper functions.

These functions make direct calls to the Notion API.
"""
import requests
from typing import Optional, Dict, Any, List

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_headers(token: str) -> Dict[str, str]:
    """Get headers for Notion API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def search_notion(
    token: str,
    query: str,
    filter_type: Optional[str] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    Search Notion workspace for pages and databases.

    Args:
        token: Notion API token
        query: Search query string
        filter_type: Optional - "page" or "database"
        page_size: Number of results (max 100)

    Returns:
        List of search results
    """
    url = f"{NOTION_API_BASE}/search"
    headers = _get_headers(token)

    payload: Dict[str, Any] = {
        "query": query,
        "page_size": page_size,
    }

    if filter_type in ("page", "database"):
        payload["filter"] = {"property": "object", "value": filter_type}

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code != 200:
        return [{"error": data}]

    return data.get("results", [])


def get_page(token: str, page_id: str) -> Dict[str, Any]:
    """
    Get a Notion page by ID.

    Args:
        token: Notion API token
        page_id: The page ID

    Returns:
        Page object or error
    """
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    headers = _get_headers(token)

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def get_database(token: str, database_id: str) -> Dict[str, Any]:
    """
    Get a Notion database schema by ID.

    Args:
        token: Notion API token
        database_id: The database ID

    Returns:
        Database object or error
    """
    url = f"{NOTION_API_BASE}/databases/{database_id}"
    headers = _get_headers(token)

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def query_database(
    token: str,
    database_id: str,
    filter_obj: Optional[Dict[str, Any]] = None,
    sorts: Optional[List[Dict[str, Any]]] = None,
    page_size: int = 100,
) -> Dict[str, Any]:
    """
    Query a Notion database.

    Args:
        token: Notion API token
        database_id: The database ID
        filter_obj: Optional filter object
        sorts: Optional list of sort objects
        page_size: Number of results (max 100)

    Returns:
        Query results or error
    """
    url = f"{NOTION_API_BASE}/databases/{database_id}/query"
    headers = _get_headers(token)

    payload: Dict[str, Any] = {"page_size": page_size}

    if filter_obj:
        payload["filter"] = filter_obj

    if sorts:
        payload["sorts"] = sorts

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def create_page(
    token: str,
    parent_id: str,
    parent_type: str,
    properties: Dict[str, Any],
    children: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Create a new page in Notion.

    Args:
        token: Notion API token
        parent_id: ID of the parent page or database
        parent_type: "page_id" or "database_id"
        properties: Page properties
        children: Optional list of block children

    Returns:
        Created page object or error
    """
    url = f"{NOTION_API_BASE}/pages"
    headers = _get_headers(token)

    payload: Dict[str, Any] = {
        "parent": {parent_type: parent_id},
        "properties": properties,
    }

    if children:
        payload["children"] = children

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def update_page(
    token: str,
    page_id: str,
    properties: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Update a Notion page's properties.

    Args:
        token: Notion API token
        page_id: The page ID
        properties: Properties to update

    Returns:
        Updated page object or error
    """
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    headers = _get_headers(token)

    payload = {"properties": properties}

    response = requests.patch(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def get_block_children(
    token: str,
    block_id: str,
    page_size: int = 100,
) -> Dict[str, Any]:
    """
    Get the children blocks of a block (or page).

    Args:
        token: Notion API token
        block_id: The block or page ID
        page_size: Number of results (max 100)

    Returns:
        Block children or error
    """
    url = f"{NOTION_API_BASE}/blocks/{block_id}/children"
    headers = _get_headers(token)

    params = {"page_size": page_size}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def append_block_children(
    token: str,
    block_id: str,
    children: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Append children blocks to a block (or page).

    Args:
        token: Notion API token
        block_id: The block or page ID
        children: List of block objects to append

    Returns:
        Appended blocks or error
    """
    url = f"{NOTION_API_BASE}/blocks/{block_id}/children"
    headers = _get_headers(token)

    payload = {"children": children}

    response = requests.patch(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def delete_block(token: str, block_id: str) -> Dict[str, Any]:
    """
    Delete (archive) a block.

    Args:
        token: Notion API token
        block_id: The block ID

    Returns:
        Deleted block object or error
    """
    url = f"{NOTION_API_BASE}/blocks/{block_id}"
    headers = _get_headers(token)

    response = requests.delete(url, headers=headers)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def get_user(token: str, user_id: str = "me") -> Dict[str, Any]:
    """
    Get a Notion user.

    Args:
        token: Notion API token
        user_id: The user ID or "me" for the bot user

    Returns:
        User object or error
    """
    url = f"{NOTION_API_BASE}/users/{user_id}"
    headers = _get_headers(token)

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data
