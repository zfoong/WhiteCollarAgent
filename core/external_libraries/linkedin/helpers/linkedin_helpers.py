"""
LinkedIn API helper functions.

These functions make direct calls to the LinkedIn REST API v2.
LinkedIn uses URNs for identifiers (e.g., urn:li:person:xxx).
"""
import requests
import time
from typing import Optional, Dict, Any, List
from urllib.parse import quote

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
LINKEDIN_OAUTH_BASE = "https://www.linkedin.com/oauth/v2"


def _encode_urn(urn: str) -> str:
    """URL-encode a LinkedIn URN for use in API paths."""
    return quote(urn, safe="")


def _get_headers(access_token: str) -> Dict[str, str]:
    """Get standard headers for LinkedIn API requests."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401",
    }


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Optional[tuple]:
    """
    Refresh the LinkedIn OAuth access token.

    Returns:
        Tuple of (new_access_token, token_expiry_timestamp) if successful, None otherwise
    """
    if not all([client_id, client_secret, refresh_token]):
        return None

    url = f"{LINKEDIN_OAUTH_BASE}/accessToken"

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = requests.post(url, data=payload, timeout=15)

        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get("access_token")
            expires_in = data.get("expires_in", 5184000)  # Default 60 days
            # Subtract 24 hours as safety buffer
            token_expiry = time.time() + expires_in - 86400
            return (new_access_token, token_expiry)
        else:
            print(f"[LINKEDIN_TOKEN_REFRESH] Failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[LINKEDIN_TOKEN_REFRESH] Exception: {str(e)}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_user_profile(access_token: str) -> Dict[str, Any]:
    """
    Get the authenticated user's profile information.
    Uses /userinfo endpoint for basic profile data.
    """
    url = "https://api.linkedin.com/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "result": {
                    "linkedin_id": data.get("sub"),
                    "name": data.get("name"),
                    "given_name": data.get("given_name"),
                    "family_name": data.get("family_name"),
                    "email": data.get("email"),
                    "picture": data.get("picture"),
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_profile_details(access_token: str) -> Dict[str, Any]:
    """
    Get detailed profile information including headline.
    Uses the /me endpoint.
    """
    url = f"{LINKEDIN_API_BASE}/me"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# POST OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def create_text_post(
    access_token: str,
    author_urn: str,
    text: str,
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Create a text-only post on LinkedIn.

    Args:
        access_token: OAuth access token
        author_urn: URN of author (urn:li:person:xxx or urn:li:organization:xxx)
        text: Post text content (max 3000 characters)
        visibility: "PUBLIC", "CONNECTIONS", or "LOGGED_IN" (members only)
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = _get_headers(access_token)

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text[:3000]
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": visibility
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def create_post_with_link(
    access_token: str,
    author_urn: str,
    text: str,
    link_url: str,
    link_title: str = "",
    link_description: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Create a post with a link/article on LinkedIn.
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = _get_headers(access_token)

    media_item = {
        "status": "READY",
        "originalUrl": link_url,
    }
    if link_title:
        media_item["title"] = {"text": link_title}
    if link_description:
        media_item["description"] = {"text": link_description}

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text[:3000]
                },
                "shareMediaCategory": "ARTICLE",
                "media": [media_item]
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": visibility
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def create_post_with_image(
    access_token: str,
    author_urn: str,
    text: str,
    image_url: str,
    image_title: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Create a post with an image on LinkedIn.
    Note: This version supports external image URLs.
    For uploaded images, use the image upload flow first.
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = _get_headers(access_token)

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text[:3000]
                },
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status": "READY",
                    "originalUrl": image_url,
                    "title": {"text": image_title or ""},
                }]
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": visibility
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def delete_post(access_token: str, post_urn: str) -> Dict[str, Any]:
    """
    Delete a LinkedIn post.

    Args:
        access_token: OAuth access token
        post_urn: URN of the post (urn:li:share:xxx or urn:li:ugcPost:xxx)
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts/{_encode_urn(post_urn)}"
    headers = _get_headers(access_token)

    try:
        response = requests.delete(url, headers=headers, timeout=15)

        if response.status_code in (200, 204):
            return {"ok": True, "result": {"deleted": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# ORGANIZATION/COMPANY OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_organization_info(access_token: str, organization_id: str) -> Dict[str, Any]:
    """
    Get information about a LinkedIn organization/company.

    Args:
        access_token: OAuth access token
        organization_id: Organization ID (numeric, not URN)
    """
    url = f"{LINKEDIN_API_BASE}/organizations/{organization_id}"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_organization_admin_roles(access_token: str) -> Dict[str, Any]:
    """
    Get organizations where the authenticated user has admin access.
    Required for posting as a company page.
    """
    url = f"{LINKEDIN_API_BASE}/organizationAcls"
    params = {
        "q": "roleAssignee",
        "role": "ADMINISTRATOR",
        "projection": "(elements*(organization~,roleAssignee))"
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_organization_followers_count(access_token: str, organization_urn: str) -> Dict[str, Any]:
    """
    Get follower statistics for an organization.
    """
    org_id = organization_urn.split(":")[-1] if ":" in organization_urn else organization_urn
    url = f"{LINKEDIN_API_BASE}/organizationalEntityFollowerStatistics"
    params = {
        "q": "organizationalEntity",
        "organizationalEntity": f"urn:li:organization:{org_id}"
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_organization_page_statistics(
    access_token: str,
    organization_urn: str,
) -> Dict[str, Any]:
    """
    Get page statistics/analytics for an organization.
    Requires rw_organization_admin scope.
    """
    org_id = organization_urn.split(":")[-1] if ":" in organization_urn else organization_urn
    url = f"{LINKEDIN_API_BASE}/organizationPageStatistics"
    params = {
        "q": "organization",
        "organization": f"urn:li:organization:{org_id}"
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# JOB OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def search_jobs(
    access_token: str,
    keywords: str,
    location: Optional[str] = None,
    count: int = 25,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Search for job postings on LinkedIn.
    Note: Job search API access may be limited and require special permissions.

    Args:
        access_token: OAuth access token
        keywords: Job search keywords
        location: Optional location filter
        count: Number of results (max 50)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/jobSearch"
    params = {
        "keywords": keywords,
        "count": min(count, 50),
        "start": start,
    }

    if location:
        params["locationGeoUrn"] = location

    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {
                "error": f"API error: {response.status_code}",
                "details": response.text,
                "note": "LinkedIn Job Search API access may be restricted."
            }
    except Exception as e:
        return {"error": str(e)}


def get_job_details(access_token: str, job_id: str) -> Dict[str, Any]:
    """
    Get details about a specific job posting.
    """
    url = f"{LINKEDIN_API_BASE}/jobs/{job_id}"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# CONNECTIONS/NETWORK
# ═══════════════════════════════════════════════════════════════════════════

def get_connections(access_token: str, count: int = 50, start: int = 0) -> Dict[str, Any]:
    """
    Get the authenticated user's connections.
    Note: Access to connections is limited in LinkedIn API v2.
    """
    url = f"{LINKEDIN_API_BASE}/connections"
    params = {
        "q": "viewer",
        "count": min(count, 50),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# CONNECTION REQUESTS / INVITATIONS
# ═══════════════════════════════════════════════════════════════════════════

def send_connection_request(
    access_token: str,
    invitee_profile_urn: str,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a connection request (invitation) to another LinkedIn user.

    Args:
        access_token: OAuth access token
        invitee_profile_urn: URN of the person to invite (urn:li:person:xxx)
        message: Optional personalized message (max 300 characters)
    """
    url = f"{LINKEDIN_API_BASE}/invitations"
    headers = _get_headers(access_token)

    payload = {
        "invitee": invitee_profile_urn,
    }

    if message:
        payload["message"] = message[:300]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json() if response.text else {"sent": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def withdraw_connection_request(
    access_token: str,
    invitation_urn: str,
) -> Dict[str, Any]:
    """
    Withdraw a pending connection request.

    Args:
        access_token: OAuth access token
        invitation_urn: URN of the invitation to withdraw
    """
    url = f"{LINKEDIN_API_BASE}/invitations/{_encode_urn(invitation_urn)}"
    headers = _get_headers(access_token)

    try:
        response = requests.delete(url, headers=headers, timeout=15)

        if response.status_code in (200, 204):
            return {"ok": True, "result": {"withdrawn": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_sent_invitations(
    access_token: str,
    count: int = 50,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get sent connection invitations (pending).

    Args:
        access_token: OAuth access token
        count: Number of results (max 50)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/invitations"
    params = {
        "q": "inviter",
        "count": min(count, 50),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_received_invitations(
    access_token: str,
    count: int = 50,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get received connection invitations (pending).

    Args:
        access_token: OAuth access token
        count: Number of results (max 50)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/invitations"
    params = {
        "q": "invitee",
        "count": min(count, 50),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def respond_to_invitation(
    access_token: str,
    invitation_urn: str,
    action: str,  # "accept" or "ignore"
) -> Dict[str, Any]:
    """
    Accept or ignore a received connection invitation.

    Args:
        access_token: OAuth access token
        invitation_urn: URN of the invitation
        action: "accept" or "ignore"
    """
    url = f"{LINKEDIN_API_BASE}/invitations/{_encode_urn(invitation_urn)}"
    headers = _get_headers(access_token)

    payload = {
        "action": action.upper()
    }

    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 204):
            return {"ok": True, "result": {"action": action, "completed": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SOCIAL ACTIONS (LIKES/REACTIONS)
# ═══════════════════════════════════════════════════════════════════════════

def like_post(
    access_token: str,
    actor_urn: str,
    post_urn: str,
) -> Dict[str, Any]:
    """
    Like/react to a LinkedIn post.

    Args:
        access_token: OAuth access token
        actor_urn: URN of the person liking (urn:li:person:xxx)
        post_urn: URN of the post to like (urn:li:share:xxx or urn:li:ugcPost:xxx)
    """
    url = f"{LINKEDIN_API_BASE}/socialActions/{_encode_urn(post_urn)}/likes"
    headers = _get_headers(access_token)

    payload = {
        "actor": actor_urn,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json() if response.text else {"liked": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def unlike_post(
    access_token: str,
    actor_urn: str,
    post_urn: str,
) -> Dict[str, Any]:
    """
    Remove like/reaction from a LinkedIn post.

    Args:
        access_token: OAuth access token
        actor_urn: URN of the person who liked
        post_urn: URN of the post
    """
    # LinkedIn REST.li uses composite key format - URN inside () should NOT be URL-encoded
    # But the entire composite key portion needs to be encoded
    composite_key = quote(f"(liker:{actor_urn})", safe="")
    url = f"{LINKEDIN_API_BASE}/socialActions/{_encode_urn(post_urn)}/likes/{composite_key}"
    headers = _get_headers(access_token)

    try:
        response = requests.delete(url, headers=headers, timeout=15)

        if response.status_code in (200, 204):
            return {"ok": True, "result": {"unliked": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_post_likes(
    access_token: str,
    post_urn: str,
    count: int = 50,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get likes/reactions on a LinkedIn post.

    Args:
        access_token: OAuth access token
        post_urn: URN of the post
        count: Number of results (max 100)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/socialActions/{_encode_urn(post_urn)}/likes"
    params = {
        "count": min(count, 100),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# COMMENTS
# ═══════════════════════════════════════════════════════════════════════════

def create_comment(
    access_token: str,
    actor_urn: str,
    post_urn: str,
    text: str,
    parent_comment_urn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a comment on a LinkedIn post.

    Args:
        access_token: OAuth access token
        actor_urn: URN of the commenter (urn:li:person:xxx)
        post_urn: URN of the post to comment on
        text: Comment text (max 1250 characters)
        parent_comment_urn: Optional parent comment URN for replies
    """
    url = f"{LINKEDIN_API_BASE}/socialActions/{_encode_urn(post_urn)}/comments"
    headers = _get_headers(access_token)

    payload = {
        "actor": actor_urn,
        "message": {
            "text": text[:1250]
        }
    }

    if parent_comment_urn:
        payload["parentComment"] = parent_comment_urn

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_post_comments(
    access_token: str,
    post_urn: str,
    count: int = 50,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get comments on a LinkedIn post.

    Args:
        access_token: OAuth access token
        post_urn: URN of the post
        count: Number of results (max 100)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/socialActions/{_encode_urn(post_urn)}/comments"
    params = {
        "count": min(count, 100),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def delete_comment(
    access_token: str,
    actor_urn: str,
    post_urn: str,
    comment_urn: str,
) -> Dict[str, Any]:
    """
    Delete a comment from a LinkedIn post.

    Args:
        access_token: OAuth access token
        actor_urn: URN of the person deleting the comment
        post_urn: URN of the post
        comment_urn: URN of the comment to delete
    """
    url = f"{LINKEDIN_API_BASE}/socialActions/{_encode_urn(post_urn)}/comments/{_encode_urn(comment_urn)}"
    headers = _get_headers(access_token)
    params = {"actor": actor_urn}

    try:
        response = requests.delete(url, headers=headers, params=params, timeout=15)

        if response.status_code in (200, 204):
            return {"ok": True, "result": {"deleted": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# USER POSTS / FEED
# ═══════════════════════════════════════════════════════════════════════════

def get_user_posts(
    access_token: str,
    author_urn: str,
    count: int = 50,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get posts authored by a specific user.

    Args:
        access_token: OAuth access token
        author_urn: URN of the author (urn:li:person:xxx)
        count: Number of results (max 100)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    params = {
        "q": "authors",
        "authors": f"List({author_urn})",
        "count": min(count, 100),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_organization_posts(
    access_token: str,
    organization_urn: str,
    count: int = 50,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get posts authored by an organization.

    Args:
        access_token: OAuth access token
        organization_urn: URN of the organization (urn:li:organization:xxx)
        count: Number of results (max 100)
        start: Pagination offset
    """
    org_id = organization_urn.split(":")[-1] if ":" in organization_urn else organization_urn
    full_urn = f"urn:li:organization:{org_id}"

    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    params = {
        "q": "authors",
        "authors": f"List({full_urn})",
        "count": min(count, 100),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_post(
    access_token: str,
    post_urn: str,
) -> Dict[str, Any]:
    """
    Get a specific post by URN.

    Args:
        access_token: OAuth access token
        post_urn: URN of the post (urn:li:share:xxx or urn:li:ugcPost:xxx)
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts/{_encode_urn(post_urn)}"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# RESHARE / REPOST
# ═══════════════════════════════════════════════════════════════════════════

def reshare_post(
    access_token: str,
    author_urn: str,
    original_post_urn: str,
    commentary: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Reshare/repost existing content with optional commentary.

    Args:
        access_token: OAuth access token
        author_urn: URN of the person resharing
        original_post_urn: URN of the original post to reshare
        commentary: Optional text to add (max 3000 chars)
        visibility: "PUBLIC", "CONNECTIONS", or "LOGGED_IN"
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = _get_headers(access_token)

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": commentary[:3000] if commentary else ""
                },
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": visibility
        }
    }

    # Add the reshared content reference
    payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "ARTICLE"
    payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
        "status": "READY",
        "originalUrl": f"https://www.linkedin.com/feed/update/{original_post_urn}",
    }]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════════════

def search_companies(
    access_token: str,
    keywords: str,
    count: int = 25,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Search for companies/organizations on LinkedIn.

    Args:
        access_token: OAuth access token
        keywords: Search keywords
        count: Number of results (max 50)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/organizationLookup"
    params = {
        "q": "vanityName",
        "vanityName": keywords,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            # Try alternative search endpoint
            alt_url = f"{LINKEDIN_API_BASE}/organizations"
            alt_params = {
                "q": "search",
                "keywords": keywords,
                "count": min(count, 50),
                "start": start,
            }
            alt_response = requests.get(alt_url, headers=headers, params=alt_params, timeout=15)

            if alt_response.status_code == 200:
                return {"ok": True, "result": alt_response.json()}
            else:
                return {
                    "error": f"API error: {response.status_code}",
                    "details": response.text,
                    "note": "Organization search may require specific API access."
                }
    except Exception as e:
        return {"error": str(e)}


def lookup_company_by_vanity_name(
    access_token: str,
    vanity_name: str,
) -> Dict[str, Any]:
    """
    Look up a company by its vanity name (URL slug).

    Args:
        access_token: OAuth access token
        vanity_name: Company's vanity name (e.g., "microsoft" from linkedin.com/company/microsoft)
    """
    url = f"{LINKEDIN_API_BASE}/organizations"
    params = {
        "q": "vanityName",
        "vanityName": vanity_name,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_person_by_id(
    access_token: str,
    person_id: str,
) -> Dict[str, Any]:
    """
    Get a person's profile by their LinkedIn ID.

    Args:
        access_token: OAuth access token
        person_id: LinkedIn person ID (numeric, not URN)
    """
    url = f"{LINKEDIN_API_BASE}/people/(id:{person_id})"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGING (Limited API Access)
# ═══════════════════════════════════════════════════════════════════════════

def send_message(
    access_token: str,
    sender_urn: str,
    recipient_urns: List[str],
    subject: str,
    body: str,
) -> Dict[str, Any]:
    """
    Send a message to one or more LinkedIn users.
    Note: This requires specific messaging permissions which may not be
    available for all API applications. Works best with InMail credits
    or for users you're already connected with.

    Args:
        access_token: OAuth access token
        sender_urn: URN of the sender (urn:li:person:xxx)
        recipient_urns: List of recipient URNs
        subject: Message subject
        body: Message body text
    """
    url = f"{LINKEDIN_API_BASE}/messages"
    headers = _get_headers(access_token)

    payload = {
        "recipients": recipient_urns,
        "subject": subject,
        "body": body,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json() if response.text else {"sent": True}}
        else:
            return {
                "error": f"API error: {response.status_code}",
                "details": response.text,
                "note": "Messaging API requires special permissions. You may need to be connected with the recipient."
            }
    except Exception as e:
        return {"error": str(e)}


def get_conversations(
    access_token: str,
    count: int = 20,
    start: int = 0,
) -> Dict[str, Any]:
    """
    Get message conversations.
    Note: Requires messaging permissions which may be restricted.

    Args:
        access_token: OAuth access token
        count: Number of conversations (max 50)
        start: Pagination offset
    """
    url = f"{LINKEDIN_API_BASE}/conversations"
    params = {
        "count": min(count, 50),
        "start": start,
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {
                "error": f"API error: {response.status_code}",
                "details": response.text,
                "note": "Messaging API requires special permissions."
            }
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# MEDIA UPLOAD
# ═══════════════════════════════════════════════════════════════════════════

def register_image_upload(
    access_token: str,
    owner_urn: str,
) -> Dict[str, Any]:
    """
    Register an image upload to get upload URL.
    First step in uploading images for posts.

    Args:
        access_token: OAuth access token
        owner_urn: URN of the owner (urn:li:person:xxx or urn:li:organization:xxx)
    """
    url = f"{LINKEDIN_API_BASE}/assets?action=registerUpload"
    headers = _get_headers(access_token)

    payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": owner_urn,
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent"
            }]
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            data = response.json()
            # Extract upload URL and asset URN
            upload_info = data.get("value", {})
            upload_mechanism = upload_info.get("uploadMechanism", {})
            media_upload = upload_mechanism.get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})

            return {
                "ok": True,
                "result": {
                    "upload_url": media_upload.get("uploadUrl"),
                    "asset": upload_info.get("asset"),
                    "full_response": data
                }
            }
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def upload_image_binary(
    upload_url: str,
    access_token: str,
    image_data: bytes,
) -> Dict[str, Any]:
    """
    Upload image binary data to LinkedIn.
    Second step after register_image_upload.

    Args:
        upload_url: The upload URL from register_image_upload
        access_token: OAuth access token
        image_data: Binary image data
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/octet-stream",
    }

    try:
        response = requests.put(upload_url, headers=headers, data=image_data, timeout=60)

        if response.status_code in (200, 201):
            return {"ok": True, "result": {"uploaded": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def create_post_with_uploaded_image(
    access_token: str,
    author_urn: str,
    text: str,
    asset_urn: str,
    image_title: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Create a post with an uploaded image (using asset URN).

    Args:
        access_token: OAuth access token
        author_urn: URN of author
        text: Post text
        asset_urn: Asset URN from the upload process
        image_title: Optional image title
        visibility: Post visibility
    """
    url = f"{LINKEDIN_API_BASE}/ugcPosts"
    headers = _get_headers(access_token)

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text[:3000]
                },
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status": "READY",
                    "media": asset_urn,
                    "title": {"text": image_title or ""},
                }]
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": visibility
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# POST ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════

def get_share_statistics(
    access_token: str,
    share_urns: List[str],
) -> Dict[str, Any]:
    """
    Get statistics (views, likes, comments, shares) for posts.

    Args:
        access_token: OAuth access token
        share_urns: List of share/post URNs
    """
    url = f"{LINKEDIN_API_BASE}/organizationalEntityShareStatistics"
    params = {
        "q": "organizationalEntity",
        "shares": ",".join(share_urns),
    }
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            # Try alternative endpoint for personal posts
            alt_url = f"{LINKEDIN_API_BASE}/socialMetadata"
            alt_params = {
                "ids": f"List({','.join(share_urns)})",
            }
            alt_response = requests.get(alt_url, headers=headers, params=alt_params, timeout=15)

            if alt_response.status_code == 200:
                return {"ok": True, "result": alt_response.json()}
            else:
                return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def get_social_metadata(
    access_token: str,
    post_urn: str,
) -> Dict[str, Any]:
    """
    Get social metadata (likes count, comments count, shares count) for a post.

    Args:
        access_token: OAuth access token
        post_urn: URN of the post
    """
    url = f"{LINKEDIN_API_BASE}/socialMetadata/{_encode_urn(post_urn)}"
    headers = _get_headers(access_token)

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return {"ok": True, "result": response.json()}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# FOLLOW / UNFOLLOW
# ═══════════════════════════════════════════════════════════════════════════

def follow_organization(
    access_token: str,
    follower_urn: str,
    organization_urn: str,
) -> Dict[str, Any]:
    """
    Follow an organization/company page.

    Args:
        access_token: OAuth access token
        follower_urn: URN of the follower (urn:li:person:xxx)
        organization_urn: URN of the organization to follow
    """
    url = f"{LINKEDIN_API_BASE}/organizationFollows"
    headers = _get_headers(access_token)

    org_id = organization_urn.split(":")[-1] if ":" in organization_urn else organization_urn

    payload = {
        "followee": f"urn:li:organization:{org_id}",
        "follower": follower_urn,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            return {"ok": True, "result": response.json() if response.text else {"following": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}


def unfollow_organization(
    access_token: str,
    follower_urn: str,
    organization_urn: str,
) -> Dict[str, Any]:
    """
    Unfollow an organization/company page.

    Args:
        access_token: OAuth access token
        follower_urn: URN of the follower
        organization_urn: URN of the organization to unfollow
    """
    org_id = organization_urn.split(":")[-1] if ":" in organization_urn else organization_urn
    followee_urn = f"urn:li:organization:{org_id}"
    # LinkedIn uses a special path format with encoded URNs
    url = f"{LINKEDIN_API_BASE}/organizationFollows/follower={_encode_urn(follower_urn)}&followee={_encode_urn(followee_urn)}"
    headers = _get_headers(access_token)

    try:
        response = requests.delete(url, headers=headers, timeout=15)

        if response.status_code in (200, 204):
            return {"ok": True, "result": {"unfollowed": True}}
        else:
            return {"error": f"API error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}
