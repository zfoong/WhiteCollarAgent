import os
import requests
import base64
import mimetypes
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any, Tuple

def encode_email(to_email: str, from_email: str, subject: str, body: str, attachments: Optional[List[str]] = None) -> str:
    """
    Encode an email with optional attachments into a base64 URL-safe string for Gmail API.
    attachments: list of file paths
    """
    msg = MIMEMultipart()
    msg['to'] = to_email
    msg['from'] = from_email
    msg['subject'] = subject

    # Attach the email body
    msg.attach(MIMEText(body, "plain"))

    # Attach files if any
    if attachments:
        for file_path in attachments:
            if not os.path.isfile(file_path):
                continue  # Skip if file doesn't exist

            # Guess MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"
            maintype, subtype = mime_type.split("/", 1)

            with open(file_path, "rb") as f:
                part = MIMEBase(maintype, subtype)
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(file_path)}"'
                )
                msg.attach(part)

    # Encode the whole message as base64 urlsafe string
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()

def send_email_oauth2(access_token: str, encoded_message: str) -> bool:
    url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    data = {
        'raw': encoded_message
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return True
    else:
        return False

def create_google_meet_event(access_token, calendar_id="primary", event_data=None):
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    params = {"conferenceDataVersion": 1}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        params=params,
        json=event_data,
        timeout=15,
    )

    if response.status_code in (200, 201):
        return response.json()

    try:
        return {"error": response.status_code, "message": response.json()}
    except Exception:
        return {"error": response.status_code, "message": response.text}

def check_google_calendar_availability(
    access_token,
    calendar_id="primary",
    time_min=None,
    time_max=None,
):
    url = "https://www.googleapis.com/calendar/v3/freeBusy"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": [{"id": calendar_id}],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)

    if response.status_code == 200:
        return response.json()

    try:
        return {"error": response.status_code, "message": response.json()}
    except Exception:
        return {"error": response.status_code, "message": response.text}

def list_recent_emails(access_token: str, n: int = 5, unread_only: bool = True) -> List[Dict[str, Any]]:
    """
    List the top `n` recent emails from Gmail.
    """
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    params = {
        "maxResults": n,
        "labelIds": ["INBOX"],
    }
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers, params=params, timeout=15)
    if response.status_code != 200:
        return []

    messages = response.json().get("messages", [])
    return messages

def get_email_details(access_token: str, message_id: str, full_body: bool = False) -> Dict[str, Any]:
    """
    Get detailed information about a specific email message.
    If full_body=True, returns the entire body decoded from base64.
    """
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    format_type = "full" if full_body else "metadata"
    params = {
        "format": format_type,
        "metadataHeaders": ["From", "To", "Subject", "Date"]
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers, params=params, timeout=15)
    if response.status_code != 200:
        return {"error": response.text}

    msg = response.json()
    email_info = {
        "id": msg.get("id"),
        "snippet": msg.get("snippet", ""),
        "headers": {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    }

    # Decode body if requested
    if full_body and "parts" in msg.get("payload", {}):
        import base64
        parts = msg["payload"]["parts"]
        for part in parts:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                data = part["body"]["data"]
                email_info["body"] = base64.urlsafe_b64decode(data.encode("ASCII")).decode("utf-8")
                break

    return email_info

def read_top_n_emails(access_token: str, n: int = 5, full_body: bool = False) -> List[Dict[str, Any]]:
    """
    Helper function to get the top `n` recent emails with details.
    """
    messages = list_recent_emails(access_token, n=n)
    emails = []
    for msg in messages:
        email_info = get_email_details(access_token, msg["id"], full_body=full_body)
        emails.append(email_info)
    return emails

def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> Optional[Tuple[str, float]]:
    """
    Refresh the Google OAuth access token using the refresh token.

    Args:
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret
        refresh_token: The refresh token

    Returns:
        Tuple of (new_access_token, token_expiry_timestamp) if successful, None otherwise
    """
    if not all([client_id, client_secret, refresh_token]):
        return None

    token_url = "https://oauth2.googleapis.com/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    try:
        response = requests.post(token_url, data=payload, timeout=15)

        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)  # Default to 1 hour if not provided

            # Calculate expiry timestamp (current time + expires_in seconds)
            # Subtract 60 seconds as a safety buffer to refresh before actual expiry
            token_expiry = time.time() + expires_in - 60

            return (new_access_token, token_expiry)
        else:
            print(f"[TOKEN_REFRESH] Failed to refresh token: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"[TOKEN_REFRESH] Exception during token refresh: {str(e)}")
        return None