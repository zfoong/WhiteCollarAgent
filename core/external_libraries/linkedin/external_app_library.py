import time
from typing import Optional, Dict, Any, List
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.linkedin.credentials import LinkedInCredential
from core.external_libraries.linkedin.helpers.linkedin_helpers import (
    refresh_access_token,
    get_user_profile,
    get_profile_details,
    create_text_post,
    create_post_with_link,
    create_post_with_image,
    delete_post,
    get_organization_info,
    get_organization_admin_roles,
    get_organization_followers_count,
    get_organization_page_statistics,
    search_jobs,
    get_job_details,
    get_connections,
    # Connection requests
    send_connection_request,
    withdraw_connection_request,
    get_sent_invitations,
    get_received_invitations,
    respond_to_invitation,
    # Social actions
    like_post,
    unlike_post,
    get_post_likes,
    # Comments
    create_comment,
    get_post_comments,
    delete_comment,
    # Posts/feed
    get_user_posts,
    get_organization_posts,
    get_post,
    reshare_post,
    # Search
    search_companies,
    lookup_company_by_vanity_name,
    get_person_by_id,
    # Messaging
    send_message,
    get_conversations,
    # Media
    register_image_upload,
    upload_image_binary,
    create_post_with_uploaded_image,
    # Analytics
    get_share_statistics,
    get_social_metadata,
    # Follow
    follow_organization,
    unfollow_organization,
)


class LinkedInAppLibrary(ExternalAppLibrary):
    """
    LinkedIn integration library for the CraftOS agent system.

    Supports:
    - Personal profile posts
    - Company/organization page management
    - Profile data access
    - Job search (limited by LinkedIn API)
    - OAuth 2.0 token management with auto-refresh
    """

    _name = "LinkedIn"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @staticmethod
    def _ensure_person_urn(linkedin_id: str) -> str:
        """
        Ensure the LinkedIn ID is in proper URN format.
        LinkedIn API expects 'urn:li:person:xxx' or 'urn:li:organization:xxx'.
        """
        if not linkedin_id:
            return linkedin_id
        if linkedin_id.startswith("urn:li:"):
            return linkedin_id
        return f"urn:li:person:{linkedin_id}"

    @classmethod
    def initialize(cls):
        """Initialize the LinkedIn library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=LinkedInCredential,
            persistence_file="linkedin_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("LinkedInAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, linkedin_id: Optional[str] = None) -> bool:
        """
        Check if a LinkedIn credential exists for the given user.
        """
        cred_store = cls.get_credential_store()
        if linkedin_id:
            credentials = cred_store.get(user_id=user_id, linkedin_id=linkedin_id)
        else:
            credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        linkedin_id: Optional[str] = None
    ) -> Optional[LinkedInCredential]:
        """
        Retrieve LinkedIn credential for the given user.
        """
        cred_store = cls.get_credential_store()
        if linkedin_id:
            credentials = cred_store.get(user_id=user_id, linkedin_id=linkedin_id)
        else:
            credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    @classmethod
    def ensure_valid_token(
        cls,
        user_id: str,
        linkedin_id: Optional[str] = None
    ) -> Optional[LinkedInCredential]:
        """
        Get credentials and ensure the access token is valid.
        Auto-refresh if expired (LinkedIn tokens last ~60 days).
        """
        from core.config import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET

        credential = cls.get_credentials(user_id=user_id, linkedin_id=linkedin_id)
        if not credential:
            return None

        current_time = time.time()
        is_expired = credential.token_expiry is None or credential.token_expiry <= current_time

        if is_expired and credential.refresh_token:
            result = refresh_access_token(
                client_id=LINKEDIN_CLIENT_ID,
                client_secret=LINKEDIN_CLIENT_SECRET,
                refresh_token=credential.refresh_token
            )

            if result:
                new_token, new_expiry = result
                credential.access_token = new_token
                credential.token_expiry = new_expiry

                cred_store = cls.get_credential_store()
                cred_store.add(credential)

                print(f"[LINKEDIN_TOKEN_REFRESH] Refreshed token for {credential.linkedin_id}")
            else:
                print(f"[LINKEDIN_TOKEN_REFRESH] Failed for {credential.linkedin_id}")

        return credential

    # ═══════════════════════════════════════════════════════════════════════════
    # PROFILE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_my_profile(
        cls,
        user_id: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the authenticated user's LinkedIn profile."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_user_profile(access_token=credential.access_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "profile": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_profile_details(
        cls,
        user_id: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get detailed profile information."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_profile_details(access_token=credential.access_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "profile": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # POST OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def create_post(
        cls,
        user_id: str,
        text: str,
        visibility: str = "PUBLIC",
        link_url: Optional[str] = None,
        link_title: Optional[str] = None,
        image_url: Optional[str] = None,
        as_organization: Optional[str] = None,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a LinkedIn post.

        Args:
            user_id: CraftOS user ID
            text: Post text (max 3000 chars)
            visibility: "PUBLIC", "CONNECTIONS", or "LOGGED_IN"
            link_url: Optional URL to include as article
            link_title: Optional title for the link
            image_url: Optional image URL
            as_organization: Optional organization URN to post as company
            linkedin_id: Optional specific LinkedIn account
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            # Determine author URN (ensure proper URN format)
            if as_organization:
                author_urn = as_organization  # Organization URNs should already be formatted
            else:
                author_urn = cls._ensure_person_urn(credential.linkedin_id)
            if not author_urn:
                return {"status": "error", "reason": "No author URN available. Profile may not be fully loaded."}

            # Choose post type based on content
            if image_url:
                result = create_post_with_image(
                    access_token=credential.access_token,
                    author_urn=author_urn,
                    text=text,
                    image_url=image_url,
                    visibility=visibility,
                )
            elif link_url:
                result = create_post_with_link(
                    access_token=credential.access_token,
                    author_urn=author_urn,
                    text=text,
                    link_url=link_url,
                    link_title=link_title or "",
                    visibility=visibility,
                )
            else:
                result = create_text_post(
                    access_token=credential.access_token,
                    author_urn=author_urn,
                    text=text,
                    visibility=visibility,
                )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "post": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def delete_post(
        cls,
        user_id: str,
        post_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a LinkedIn post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = delete_post(access_token=credential.access_token, post_urn=post_urn)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "deleted": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # ORGANIZATION OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_my_organizations(
        cls,
        user_id: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get organizations where user has admin access."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_organization_admin_roles(access_token=credential.access_token)

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "organizations": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_organization_info(
        cls,
        user_id: str,
        organization_id: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get information about an organization."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_organization_info(
                access_token=credential.access_token,
                organization_id=organization_id
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "organization": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_organization_analytics(
        cls,
        user_id: str,
        organization_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get analytics for an organization page."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            # Get followers count
            followers_result = get_organization_followers_count(
                access_token=credential.access_token,
                organization_urn=organization_urn
            )

            # Get page statistics
            stats_result = get_organization_page_statistics(
                access_token=credential.access_token,
                organization_urn=organization_urn
            )

            return {
                "status": "success",
                "followers": followers_result.get("result") if "ok" in followers_result else None,
                "statistics": stats_result.get("result") if "ok" in stats_result else None,
            }

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # JOB OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def search_jobs(
        cls,
        user_id: str,
        keywords: str,
        location: Optional[str] = None,
        count: int = 25,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for jobs on LinkedIn."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = search_jobs(
                access_token=credential.access_token,
                keywords=keywords,
                location=location,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "jobs": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_job_details(
        cls,
        user_id: str,
        job_id: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get details about a job posting."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_job_details(
                access_token=credential.access_token,
                job_id=job_id
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "job": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # NETWORK OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_connections(
        cls,
        user_id: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get user's LinkedIn connections."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_connections(
                access_token=credential.access_token,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "connections": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION REQUESTS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def send_connection_request(
        cls,
        user_id: str,
        invitee_profile_urn: str,
        message: Optional[str] = None,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a connection request to another LinkedIn user.

        Args:
            user_id: CraftOS user ID
            invitee_profile_urn: URN of person to invite (urn:li:person:xxx)
            message: Optional personalized message (max 300 chars)
            linkedin_id: Optional specific LinkedIn account
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = send_connection_request(
                access_token=credential.access_token,
                invitee_profile_urn=invitee_profile_urn,
                message=message,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "invitation": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_sent_invitations(
        cls,
        user_id: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get sent connection invitations (pending)."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_sent_invitations(
                access_token=credential.access_token,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "invitations": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_received_invitations(
        cls,
        user_id: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get received connection invitations (pending)."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_received_invitations(
                access_token=credential.access_token,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "invitations": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def respond_to_invitation(
        cls,
        user_id: str,
        invitation_urn: str,
        action: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Accept or ignore a connection invitation.

        Args:
            action: "accept" or "ignore"
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = respond_to_invitation(
                access_token=credential.access_token,
                invitation_urn=invitation_urn,
                action=action,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "result": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def withdraw_invitation(
        cls,
        user_id: str,
        invitation_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Withdraw a pending connection request."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = withdraw_connection_request(
                access_token=credential.access_token,
                invitation_urn=invitation_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "withdrawn": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # SOCIAL ACTIONS (LIKES)
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def like_post(
        cls,
        user_id: str,
        post_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Like a LinkedIn post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = like_post(
                access_token=credential.access_token,
                actor_urn=cls._ensure_person_urn(credential.linkedin_id),
                post_urn=post_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "liked": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def unlike_post(
        cls,
        user_id: str,
        post_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Remove like from a LinkedIn post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = unlike_post(
                access_token=credential.access_token,
                actor_urn=cls._ensure_person_urn(credential.linkedin_id),
                post_urn=post_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "unliked": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_post_likes(
        cls,
        user_id: str,
        post_urn: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get likes on a LinkedIn post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_post_likes(
                access_token=credential.access_token,
                post_urn=post_urn,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "likes": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # COMMENTS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def comment_on_post(
        cls,
        user_id: str,
        post_urn: str,
        text: str,
        parent_comment_urn: Optional[str] = None,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Comment on a LinkedIn post.

        Args:
            post_urn: URN of the post
            text: Comment text (max 1250 chars)
            parent_comment_urn: Optional for replies to comments
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = create_comment(
                access_token=credential.access_token,
                actor_urn=cls._ensure_person_urn(credential.linkedin_id),
                post_urn=post_urn,
                text=text,
                parent_comment_urn=parent_comment_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "comment": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_post_comments(
        cls,
        user_id: str,
        post_urn: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get comments on a LinkedIn post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_post_comments(
                access_token=credential.access_token,
                post_urn=post_urn,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "comments": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def delete_comment(
        cls,
        user_id: str,
        post_urn: str,
        comment_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a comment from a post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = delete_comment(
                access_token=credential.access_token,
                actor_urn=cls._ensure_person_urn(credential.linkedin_id),
                post_urn=post_urn,
                comment_urn=comment_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "deleted": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # POSTS / FEED
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_my_posts(
        cls,
        user_id: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the authenticated user's own posts."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_user_posts(
                access_token=credential.access_token,
                author_urn=cls._ensure_person_urn(credential.linkedin_id),
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "posts": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_organization_posts(
        cls,
        user_id: str,
        organization_urn: str,
        count: int = 50,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get posts from an organization/company page."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_organization_posts(
                access_token=credential.access_token,
                organization_urn=organization_urn,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "posts": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_post(
        cls,
        user_id: str,
        post_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a specific post by URN."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_post(
                access_token=credential.access_token,
                post_urn=post_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "post": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def reshare_post(
        cls,
        user_id: str,
        original_post_urn: str,
        commentary: str = "",
        visibility: str = "PUBLIC",
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reshare/repost existing content with optional commentary."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = reshare_post(
                access_token=credential.access_token,
                author_urn=cls._ensure_person_urn(credential.linkedin_id),
                original_post_urn=original_post_urn,
                commentary=commentary,
                visibility=visibility,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "post": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # SEARCH
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def search_companies(
        cls,
        user_id: str,
        keywords: str,
        count: int = 25,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for companies/organizations on LinkedIn."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = search_companies(
                access_token=credential.access_token,
                keywords=keywords,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "companies": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def lookup_company(
        cls,
        user_id: str,
        vanity_name: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Look up a company by its vanity name (URL slug).

        Args:
            vanity_name: Company URL slug (e.g., "microsoft" from linkedin.com/company/microsoft)
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = lookup_company_by_vanity_name(
                access_token=credential.access_token,
                vanity_name=vanity_name,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "company": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_person(
        cls,
        user_id: str,
        person_id: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a person's profile by their LinkedIn ID."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_person_by_id(
                access_token=credential.access_token,
                person_id=person_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "person": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # MESSAGING
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def send_message(
        cls,
        user_id: str,
        recipient_urns: List[str],
        subject: str,
        body: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to LinkedIn users.
        Note: Requires specific messaging permissions. Works best with connections.
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = send_message(
                access_token=credential.access_token,
                sender_urn=cls._ensure_person_urn(credential.linkedin_id),
                recipient_urns=recipient_urns,
                subject=subject,
                body=body,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "message": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def get_conversations(
        cls,
        user_id: str,
        count: int = 20,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get message conversations.
        Note: Requires messaging permissions which may be restricted.
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_conversations(
                access_token=credential.access_token,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "conversations": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # POST ANALYTICS
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def get_post_analytics(
        cls,
        user_id: str,
        post_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get analytics/engagement metrics for a post."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = get_social_metadata(
                access_token=credential.access_token,
                post_urn=post_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "analytics": result.get("result")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # FOLLOW / UNFOLLOW
    # ═══════════════════════════════════════════════════════════════════════════

    @classmethod
    def follow_organization(
        cls,
        user_id: str,
        organization_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Follow an organization/company page."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = follow_organization(
                access_token=credential.access_token,
                follower_urn=cls._ensure_person_urn(credential.linkedin_id),
                organization_urn=organization_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "following": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    @classmethod
    def unfollow_organization(
        cls,
        user_id: str,
        organization_urn: str,
        linkedin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unfollow an organization/company page."""
        try:
            credential = cls.ensure_valid_token(user_id=user_id, linkedin_id=linkedin_id)
            if not credential:
                return {"status": "error", "reason": "No valid LinkedIn credential found."}

            result = unfollow_organization(
                access_token=credential.access_token,
                follower_urn=cls._ensure_person_urn(credential.linkedin_id),
                organization_urn=organization_urn,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "unfollowed": True}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
