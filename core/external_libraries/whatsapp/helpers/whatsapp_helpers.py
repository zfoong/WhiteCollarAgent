"""
WhatsApp Business API helper functions.

These functions make direct calls to the WhatsApp Business Cloud API (via Meta Graph API).
"""
import requests
from typing import Optional, Dict, Any, List

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


def _get_headers(access_token: str) -> Dict[str, str]:
    """Get headers for WhatsApp API requests."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def send_text_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    message: str,
    preview_url: bool = False,
) -> Dict[str, Any]:
    """
    Send a text message via WhatsApp.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID to send from
        to: Recipient phone number (with country code, e.g., "1234567890")
        message: The text message to send
        preview_url: Whether to show URL previews in the message

    Returns:
        API response with message ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": preview_url,
            "body": message,
        },
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def send_template_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    template_name: str,
    language_code: str = "en_US",
    components: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Send a template message via WhatsApp.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID to send from
        to: Recipient phone number (with country code)
        template_name: Name of the approved template
        language_code: Language code for the template (default: en_US)
        components: Optional template components (header, body, button parameters)

    Returns:
        API response with message ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    template_obj: Dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }

    if components:
        template_obj["components"] = components

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template_obj,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def send_media_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    media_type: str,
    media_url: Optional[str] = None,
    media_id: Optional[str] = None,
    caption: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a media message (image, video, audio, document) via WhatsApp.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID to send from
        to: Recipient phone number (with country code)
        media_type: Type of media: "image", "video", "audio", "document"
        media_url: Public URL of the media (either media_url or media_id required)
        media_id: Media ID from previously uploaded media
        caption: Optional caption for the media (not supported for audio)
        filename: Optional filename for documents

    Returns:
        API response with message ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    if media_type not in ("image", "video", "audio", "document"):
        return {"error": {"message": f"Invalid media_type: {media_type}"}}

    if not media_url and not media_id:
        return {"error": {"message": "Either media_url or media_id is required"}}

    media_obj: Dict[str, Any] = {}
    if media_url:
        media_obj["link"] = media_url
    if media_id:
        media_obj["id"] = media_id
    if caption and media_type != "audio":
        media_obj["caption"] = caption
    if filename and media_type == "document":
        media_obj["filename"] = filename

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: media_obj,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def send_location_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    latitude: float,
    longitude: float,
    name: Optional[str] = None,
    address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a location message via WhatsApp.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID to send from
        to: Recipient phone number (with country code)
        latitude: Location latitude
        longitude: Location longitude
        name: Optional name of the location
        address: Optional address of the location

    Returns:
        API response with message ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    location_obj: Dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
    }
    if name:
        location_obj["name"] = name
    if address:
        location_obj["address"] = address

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "location",
        "location": location_obj,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def send_contact_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    contacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Send a contact card message via WhatsApp.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID to send from
        to: Recipient phone number (with country code)
        contacts: List of contact objects with name, phones, etc.

    Returns:
        API response with message ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "contacts",
        "contacts": contacts,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def send_interactive_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    interactive_type: str,
    interactive_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Send an interactive message (buttons, list) via WhatsApp.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID to send from
        to: Recipient phone number (with country code)
        interactive_type: Type of interactive message: "button", "list", "product", "product_list"
        interactive_obj: Interactive message object with body, action, etc.

    Returns:
        API response with message ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    interactive_obj["type"] = interactive_type

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": interactive_obj,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def mark_message_as_read(
    access_token: str,
    phone_number_id: str,
    message_id: str,
) -> Dict[str, Any]:
    """
    Mark a message as read.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID
        message_id: The ID of the message to mark as read

    Returns:
        API response or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
    headers = _get_headers(access_token)

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    if response.status_code not in (200, 201):
        return {"error": data}

    return data


def upload_media(
    access_token: str,
    phone_number_id: str,
    file_path: str,
    media_type: str,
) -> Dict[str, Any]:
    """
    Upload media to WhatsApp servers.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID
        file_path: Local path to the file to upload
        media_type: MIME type of the media (e.g., "image/jpeg", "application/pdf")

    Returns:
        API response with media ID or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        with open(file_path, "rb") as f:
            files = {
                "file": (file_path.split("/")[-1], f, media_type),
            }
            data = {
                "messaging_product": "whatsapp",
                "type": media_type,
            }
            response = requests.post(url, headers=headers, files=files, data=data)
    except FileNotFoundError:
        return {"error": {"message": f"File not found: {file_path}"}}

    result = response.json()

    if response.status_code not in (200, 201):
        return {"error": result}

    return result


def get_media_url(
    access_token: str,
    media_id: str,
) -> Dict[str, Any]:
    """
    Get the URL of an uploaded media file.

    Args:
        access_token: WhatsApp Business API access token
        media_id: The media ID

    Returns:
        API response with media URL or error
    """
    url = f"{WHATSAPP_API_BASE}/{media_id}"
    headers = _get_headers(access_token)

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def get_business_profile(
    access_token: str,
    phone_number_id: str,
) -> Dict[str, Any]:
    """
    Get the WhatsApp Business profile.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID

    Returns:
        Business profile data or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}/whatsapp_business_profile"
    headers = _get_headers(access_token)
    params = {"fields": "about,address,description,email,profile_picture_url,websites,vertical"}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def get_phone_number_info(
    access_token: str,
    phone_number_id: str,
) -> Dict[str, Any]:
    """
    Get information about a phone number.

    Args:
        access_token: WhatsApp Business API access token
        phone_number_id: The phone number ID

    Returns:
        Phone number info or error
    """
    url = f"{WHATSAPP_API_BASE}/{phone_number_id}"
    headers = _get_headers(access_token)
    params = {"fields": "verified_name,code_verification_status,display_phone_number,quality_rating,platform_type,throughput,id"}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data


def get_message_templates(
    access_token: str,
    business_account_id: str,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Get message templates for a WhatsApp Business Account.

    Args:
        access_token: WhatsApp Business API access token
        business_account_id: The WhatsApp Business Account ID
        limit: Maximum number of templates to return

    Returns:
        List of message templates or error
    """
    url = f"{WHATSAPP_API_BASE}/{business_account_id}/message_templates"
    headers = _get_headers(access_token)
    params = {"limit": limit}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if response.status_code != 200:
        return {"error": data}

    return data
