import uuid
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.google_workspace.credentials import GoogleWorkspaceCredential
from core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

from core.external_libraries.google_workspace.helpers.google_helpers import (
    send_email_oauth2,
    encode_email,
    create_google_meet_event,
    check_google_calendar_availability,
    read_top_n_emails,
    refresh_access_token
)
from core.external_libraries.google_workspace.helpers.google_drive_helpers import (
    list_drive_files, 
    create_drive_folder, 
    get_drive_file, 
    move_drive_file, 
    find_drive_folder_by_name_raw
)

class GoogleWorkspaceAppLibrary(ExternalAppLibrary):
    _name = "Google Workspace"
    _version = "1.0.0"
    _credential_store: Optional[CredentialsStore] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize the Google Workspace library with its own credential store."""
        if cls._initialized:
            return

        cls._credential_store = CredentialsStore(
            credential_cls=GoogleWorkspaceCredential,
            persistence_file="google_workspace_credentials.json",
        )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> CredentialsStore:
        if cls._credential_store is None:
            raise RuntimeError("GoogleWorkspaceAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, email: str) -> bool:
        """
        Returns True if a Google Workspace credential exists for the given
        user_id and email, False otherwise.
        """
        cred_store = cls.get_credential_store()
        credentials = cred_store.get(user_id=user_id, email=email)
        return len(credentials) > 0

    @classmethod
    def get_credentials(
        cls,
        user_id: str,
        email: Optional[str] = None
    ) -> Optional[GoogleWorkspaceCredential]:
        """
        Retrieve the Google Workspace credential for the given user_id and optional email.
        Returns the credential if found, None otherwise.
        """
        cred_store = cls.get_credential_store()
        if email:
            credentials = cred_store.get(user_id=user_id, email=email)
        else:
            credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    @classmethod
    def ensure_valid_token(
        cls,
        user_id: str,
        email: Optional[str] = None
    ) -> Optional[GoogleWorkspaceCredential]:
        """
        Get credentials and ensure the access token is valid.
        If the token is expired, automatically refresh it using the refresh token.

        Returns:
            Updated credential with valid token, or None if refresh fails
        """
        credential = cls.get_credentials(user_id=user_id, email=email)
        if not credential:
            return None

        # Check if token is expired or will expire soon
        # If token_expiry is None, assume token might be expired and try to refresh
        current_time = time.time()
        is_expired = credential.token_expiry is None or credential.token_expiry <= current_time

        if is_expired and credential.refresh_token:
            # Try to refresh the token
            result = refresh_access_token(
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                refresh_token=credential.refresh_token
            )

            if result:
                new_token, new_expiry = result

                # Update the credential with new token and expiry
                credential.token = new_token
                credential.token_expiry = new_expiry

                # Save the updated credential to the store
                cred_store = cls.get_credential_store()
                cred_store.add(credential)

                print(f"[TOKEN_REFRESH] Successfully refreshed token for {credential.email}")
            else:
                print(f"[TOKEN_REFRESH] Failed to refresh token for {credential.email}")
                # Return the credential anyway - the API call might still work
                # or will fail with a proper error message

        return credential

    # --------------------------------------------------
    # Send Email
    # --------------------------------------------------
    @classmethod
    def send_email(
        cls,
        user_id: str,
        to_email: str,
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
        from_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email using the stored Google Workspace credential.
        Accepts optional attachments as list of file paths.
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, email=from_email)

            if not credential:
                return {"status": "error", "reason": "No valid credential found for this user/email."}

            encoded_message = encode_email(
                to_email=to_email,
                from_email=credential.email,
                subject=subject,
                body=body,
                attachments=attachments
            )

            success = send_email_oauth2(
                access_token=credential.token,
                encoded_message=encoded_message
            )

            if not success:
                return {"status": "error", "reason": "Sending failed due to API or network error."}

            return {"status": "success", "reason": "Email sent successfully."}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Schedule Meeting
    # --------------------------------------------------
    @classmethod
    def schedule_meeting(
        cls,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        summary: str,
        description: str = "",
        attendees: Optional[List[str]] = None,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
            if not credential:
                return {"status": "error", "reason": "No valid credential found."}

            formatted_attendees = (
                [{"email": a} for a in attendees] if attendees else []
            )

            event_payload = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start_time.isoformat() + "Z",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": end_time.isoformat() + "Z",
                    "timeZone": "UTC",
                },
                "attendees": formatted_attendees,
                "conferenceData": {
                    "createRequest": {
                        "requestId": f"meet-{uuid.uuid4()}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                },
            }

            result = create_google_meet_event(
                access_token=credential.token,
                event_data=event_payload,
            )

            if "error" in result:
                return {
                    "status": "error",
                    "reason": "Google Calendar API error",
                    "details": result,
                }

            return {
                "status": "success",
                "reason": "Meeting scheduled successfully.",
                "event": result,
            }

        except Exception as e:
            return {"status": "error", "reason": str(e)}

    # --------------------------------------------------
    # Check Availability (NO OVERLAP)
    # --------------------------------------------------
    @classmethod
    def check_availability(
        cls,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
        if not credential:
            return {"status": "error", "reason": "No valid credential found."}

        result = check_google_calendar_availability(
            access_token=credential.token,
            time_min=start_time.isoformat() + "Z",
            time_max=end_time.isoformat() + "Z",
        )

        if "error" in result:
            return {
                "status": "error",
                "reason": "Google Calendar FreeBusy API error",
                "details": result,
            }

        busy_slots = result.get("calendars", {}) \
                        .get("primary", {}) \
                        .get("busy", [])

        if busy_slots:
            return {
                "status": "busy",
                "events": busy_slots,
            }

        return {"status": "free", "events": []}

    # --------------------------------------------------
    # Schedule IF FREE
    # --------------------------------------------------
    @classmethod
    def schedule_if_free(
        cls,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        summary: str,
        description: str = "",
        attendees: Optional[List[str]] = None,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:

        availability = cls.check_availability(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            from_email=from_email,
        )

        if availability["status"] == "error":
            return {
                "status": "error",
                "reason": availability.get("reason"),
                "details": availability.get("details"),
            }

        if availability["status"] == "busy":
            return {
                "status": "busy",
                "reason": "Time slot is already occupied",
                "conflicting_events": availability.get("events", []),
            }

        return cls.schedule_meeting(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            summary=summary,
            description=description,
            attendees=attendees,
            from_email=from_email,
        )

    # --------------------------------------------------
    # Read Recent Emails
    # --------------------------------------------------
    @classmethod
    def read_recent_emails(
        cls,
        user_id: str,
        n: int = 5,
        full_body: bool = False,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch the top `n` recent emails from the user's Gmail inbox.

        Returns a dict with:
            - status: 'success' or 'error'
            - emails: List of emails with subject, sender, snippet, date, and optionally full body
            - reason: explanation if error
        """
        try:
            credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
            if not credential:
                return {"status": "error", "reason": "No valid credential found."}

            emails = read_top_n_emails(
                access_token=credential.token,
                n=n,
                full_body=full_body
            )

            return {"status": "success", "emails": emails}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # List Drive Files
    # --------------------------------------------------
    @classmethod
    def list_drive_files(
        cls,
        user_id: str,
        folder_id: str,
        from_email: Optional[str] = None,
    ):
        credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
        if not credential:
            return {"status": "error", "reason": "No valid credential found."}

        files = list_drive_files(
            access_token=credential.token,
            folder_id=folder_id,
        )

        return {"status": "success", "files": files}

    # --------------------------------------------------
    # Create Drive Folder
    # --------------------------------------------------
    @classmethod
    def create_drive_folder(
        cls,
        user_id: str,
        name: str,
        parent_folder_id: Optional[str] = None,
        from_email: Optional[str] = None,
    ):
        credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
        if not credential:
            return {"status": "error", "reason": "No valid credential found."}

        result = create_drive_folder(
            access_token=credential.token,
            name=name,
            parent_folder_id=parent_folder_id,
        )

        if "error" in result:
            return {"status": "error", "details": result}

        return {"status": "success", "folder": result}

    # --------------------------------------------------
    # Move Drive File
    # --------------------------------------------------
    @classmethod
    def move_drive_file(
        cls,
        user_id: str,
        file_id: str,
        target_folder_id: str,
        from_email: Optional[str] = None,
    ):
        credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
        if not credential:
            return {"status": "error", "reason": "No valid credential found."}

        file_meta = get_drive_file(
            access_token=credential.token,
            file_id=file_id,
        )

        if "error" in file_meta:
            return {"status": "error", "details": file_meta}

        parents_list = file_meta.get("parents", [])
        remove_parents = ",".join(parents_list) if parents_list else None

        result = move_drive_file(
            access_token=credential.token,
            file_id=file_id,
            add_parents=target_folder_id,
            remove_parents=remove_parents,
        )

        if "error" in result:
            return {"status": "error", "details": result}

        return {"status": "success", "file": result}

    # --------------------------------------------------
    # Find Drive Folder by Name
    # --------------------------------------------------
    @classmethod
    def find_drive_folder_by_name(
        cls,
        user_id: str,
        name: str,
        parent_folder_id: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Find a Google Drive folder by name.
        Optionally restrict search to a parent folder.

        Returns:
            {
                status: "success" | "error" | "not_found",
                folder: {id, name} | None
            }
        """
        credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
        if not credential:
            return {"status": "error", "reason": "No valid credential found."}

        folder = find_drive_folder_by_name_raw(
            access_token=credential.token,
            name=name,
            parent_folder_id=parent_folder_id,
        )

        if not folder:
            return {"status": "not_found", "folder": None}

        return {"status": "success", "folder": folder}

    # --------------------------------------------------
    # Resolve Drive Folder Path
    # --------------------------------------------------
    @classmethod
    def resolve_drive_folder_path(
        cls,
        user_id: str,
        path: str,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a Drive folder path (e.g. 'Root/Invoices/2024')
        into a folder ID.

        Returns:
            {
                status: "success" | "error" | "not_found",
                folder_id: str | None
            }
        """
        credential = cls.ensure_valid_token(user_id=user_id, email=from_email)
        if not credential:
            return {"status": "error", "reason": "No valid credential found."}

        parts = [p for p in path.split("/") if p]

        if parts and parts[0].lower() == "root":
            parts = parts[1:]

        current_folder_id = "root"

        for part in parts:
            folder = find_drive_folder_by_name_raw(
                access_token=credential.token,
                name=part,
                parent_folder_id=current_folder_id,
            )

            if not folder:
                return {
                    "status": "not_found",
                    "reason": f"Folder '{part}' not found",
                    "folder_id": None,
                }

            current_folder_id = folder["id"]

        return {"status": "success", "folder_id": current_folder_id}
