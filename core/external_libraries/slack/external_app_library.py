from typing import Optional, Dict, Any, List, Union
from core.external_libraries.external_app_library import ExternalAppLibrary
from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.remote_credential_store import RemoteCredentialStore
from core.external_libraries.slack.credentials import SlackCredential
from core.external_libraries.slack.helpers.slack_helpers import (
    send_message,
    list_channels,
    list_users,
    get_channel_history,
    get_user_info,
    create_channel,
    invite_to_channel,
    upload_file,
    get_channel_info,
    search_messages,
    open_dm,
)
from core.config import USE_REMOTE_CREDENTIALS


class SlackAppLibrary(ExternalAppLibrary):
    _name = "Slack"
    _version = "2.0.0"  # Version bump for remote credential support
    _credential_store: Optional[Union[CredentialsStore, RemoteCredentialStore]] = None
    _initialized: bool = False
    _use_remote: bool = False

    @classmethod
    def initialize(cls):
        """
        Initialize the Slack library with its credential store.

        Uses RemoteCredentialStore if USE_REMOTE_CREDENTIALS is True,
        otherwise uses the local CredentialsStore for backward compatibility.
        """
        if cls._initialized:
            return

        cls._use_remote = USE_REMOTE_CREDENTIALS

        if cls._use_remote:
            cls._credential_store = RemoteCredentialStore(
                credential_cls=SlackCredential,
                integration_type="slack",
            )
        else:
            cls._credential_store = CredentialsStore(
                credential_cls=SlackCredential,
                persistence_file="slack_credentials.json",
            )
        cls._initialized = True

    @classmethod
    def get_name(cls) -> str:
        return cls._name

    @classmethod
    def get_credential_store(cls) -> Union[CredentialsStore, RemoteCredentialStore]:
        if cls._credential_store is None:
            raise RuntimeError("SlackAppLibrary not initialized. Call initialize() first.")
        return cls._credential_store

    @classmethod
    def validate_connection(cls, user_id: str, workspace_id: Optional[str] = None) -> bool:
        """
        Returns True if a Slack credential exists for the given
        user_id and optional workspace_id, False otherwise.

        Note: For remote credentials, this only checks the local cache.
        Use validate_connection_async for accurate remote checks.
        """
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            # For remote store, use sync method (cache only)
            if workspace_id:
                credentials = cred_store.get_sync(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get_sync(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)
        return len(credentials) > 0

    @classmethod
    async def validate_connection_async(cls, user_id: str, workspace_id: Optional[str] = None) -> bool:
        """
        Async version of validate_connection.
        Returns True if a Slack credential exists for the user.
        """
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            if workspace_id:
                credentials = await cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = await cred_store.get(user_id=user_id)
        else:
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
    ) -> Optional[SlackCredential]:
        """
        Retrieve the Slack credential for the given user_id and optional workspace_id.
        Returns the credential if found, None otherwise.

        Note: For remote credentials, this only checks the local cache.
        Use get_credentials_async for accurate remote fetching.
        """
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            # For remote store, use sync method (cache only)
            if workspace_id:
                credentials = cred_store.get_sync(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get_sync(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    @classmethod
    async def get_credentials_async(
        cls,
        user_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[SlackCredential]:
        """
        Async version of get_credentials.
        Fetches credential from backend if using remote credentials.
        """
        cred_store = cls.get_credential_store()
        if cls._use_remote:
            if workspace_id:
                credentials = await cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = await cred_store.get(user_id=user_id)
        else:
            if workspace_id:
                credentials = cred_store.get(user_id=user_id, workspace_id=workspace_id)
            else:
                credentials = cred_store.get(user_id=user_id)

        if credentials:
            return credentials[0]
        return None

    # --------------------------------------------------
    # Send Message
    # --------------------------------------------------
    @classmethod
    def send_message(
        cls,
        user_id: str,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a Slack channel or DM.

        Args:
            user_id: The user ID
            channel: Channel ID or user ID for DM
            text: Message text
            thread_ts: Optional thread timestamp to reply in thread
            workspace_id: Optional workspace ID to use specific credentials

        Returns:
            Dict with status and message details
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = send_message(
                bot_token=credential.bot_token,
                channel=channel,
                text=text,
                thread_ts=thread_ts,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "message": result}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # List Channels
    # --------------------------------------------------
    @classmethod
    def list_channels(
        cls,
        user_id: str,
        types: str = "public_channel,private_channel",
        limit: int = 100,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List channels in the Slack workspace.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = list_channels(
                bot_token=credential.bot_token,
                types=types,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channels": result.get("channels", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # List Users
    # --------------------------------------------------
    @classmethod
    def list_users(
        cls,
        user_id: str,
        limit: int = 100,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List users in the Slack workspace.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = list_users(
                bot_token=credential.bot_token,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "users": result.get("members", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get User Info
    # --------------------------------------------------
    @classmethod
    def get_user_info(
        cls,
        user_id: str,
        slack_user_id: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get information about a Slack user.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = get_user_info(
                bot_token=credential.bot_token,
                user_id=slack_user_id,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "user": result.get("user")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Channel History
    # --------------------------------------------------
    @classmethod
    def get_channel_history(
        cls,
        user_id: str,
        channel: str,
        limit: int = 100,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get message history from a channel.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = get_channel_history(
                bot_token=credential.bot_token,
                channel=channel,
                limit=limit,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "messages": result.get("messages", [])}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Get Channel Info
    # --------------------------------------------------
    @classmethod
    def get_channel_info(
        cls,
        user_id: str,
        channel: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get information about a channel.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = get_channel_info(
                bot_token=credential.bot_token,
                channel=channel,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Create Channel
    # --------------------------------------------------
    @classmethod
    def create_channel(
        cls,
        user_id: str,
        name: str,
        is_private: bool = False,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new Slack channel.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = create_channel(
                bot_token=credential.bot_token,
                name=name,
                is_private=is_private,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Invite to Channel
    # --------------------------------------------------
    @classmethod
    def invite_to_channel(
        cls,
        user_id: str,
        channel: str,
        users: List[str],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invite users to a channel.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = invite_to_channel(
                bot_token=credential.bot_token,
                channel=channel,
                users=users,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Upload File
    # --------------------------------------------------
    @classmethod
    def upload_file(
        cls,
        user_id: str,
        channels: List[str],
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to Slack.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = upload_file(
                bot_token=credential.bot_token,
                channels=channels,
                content=content,
                file_path=file_path,
                filename=filename,
                title=title,
                initial_comment=initial_comment,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "file": result.get("file")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Search Messages
    # --------------------------------------------------
    @classmethod
    def search_messages(
        cls,
        user_id: str,
        query: str,
        count: int = 20,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for messages in the workspace.
        Note: Requires user token (xoxp-), may not work with bot tokens.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = search_messages(
                bot_token=credential.bot_token,
                query=query,
                count=count,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "messages": result.get("messages", {})}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}

    # --------------------------------------------------
    # Open DM
    # --------------------------------------------------
    @classmethod
    def open_dm(
        cls,
        user_id: str,
        users: List[str],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Open a DM or group DM with users.
        """
        try:
            credential = cls.get_credentials(user_id=user_id, workspace_id=workspace_id)
            if not credential:
                return {"status": "error", "reason": "No valid Slack credential found."}

            result = open_dm(
                bot_token=credential.bot_token,
                users=users,
            )

            if "error" in result:
                return {"status": "error", "details": result}

            return {"status": "success", "channel": result.get("channel")}

        except Exception as e:
            return {"status": "error", "reason": f"Unexpected error: {str(e)}"}
