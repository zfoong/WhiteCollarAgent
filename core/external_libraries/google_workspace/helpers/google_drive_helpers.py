import requests
from typing import List, Dict, Any, Optional

def list_drive_files(
    access_token: str,
    folder_id: str,
    fields: str = "files(id,name,mimeType,parents)"
) -> List[Dict[str, Any]]:
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": fields,
    }

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        return []

    return resp.json().get("files", [])

def create_drive_folder(
    access_token: str,
    name: str,
    parent_folder_id: Optional[str] = None
) -> Dict[str, Any]:
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }

    if parent_folder_id:
        payload["parents"] = [parent_folder_id]

    resp = requests.post(url, headers=headers, json=payload, timeout=15)

    if resp.status_code in (200, 201):
        return resp.json()

    return {"error": resp.status_code, "message": resp.text}

def get_drive_file(
    access_token: str,
    file_id: str,
    fields: str = "id,parents"
) -> Dict[str, Any]:
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"fields": fields}

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        return {"error": resp.text}

    return resp.json()

def move_drive_file(
    access_token: str,
    file_id: str,
    add_parents: str,
    remove_parents: str,
) -> Dict[str, Any]:
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "addParents": add_parents,
        "fields": "id,parents",
    }
    if remove_parents:
        params["removeParents"] = remove_parents
        
    resp = requests.patch(url, headers=headers, params=params, timeout=15)
    if resp.status_code == 200:
        return resp.json()

    return {"error": resp.status_code, "message": resp.text}

def find_drive_folder_by_name_raw(
    access_token: str,
    name: str,
    parent_folder_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {"Authorization": f"Bearer {access_token}"}

    q = [
        f"name = '{name}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]
    if parent_folder_id:
        q.append(f"'{parent_folder_id}' in parents")

    params = {
        "q": " and ".join(q),
        "fields": "files(id,name)",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        return None

    files = resp.json().get("files", [])
    return files[0] if files else None
