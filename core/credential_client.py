"""
Local credential client for TUI mode.

In CraftOS, CredentialClient fetches credentials from the backend via HTTP.
Here it reads from the local CredentialsStore JSON files instead.
"""
from dataclasses import asdict
from typing import Dict, Any, Optional

from core.logger import logger


# integration_type -> (credential_class_path, persistence_file, service_id_field)
_STORE_MAP = {
    "google_workspace": ("core.external_libraries.google_workspace.credentials", "GoogleWorkspaceCredential", "google_workspace_credentials.json", "email"),
    "slack": ("core.external_libraries.slack.credentials", "SlackCredential", "slack_credentials.json", "workspace_id"),
    "notion": ("core.external_libraries.notion.credentials", "NotionCredential", "notion_credentials.json", "workspace_id"),
    "linkedin": ("core.external_libraries.linkedin.credentials", "LinkedInCredential", "linkedin_credentials.json", "linkedin_id"),
    "zoom": ("core.external_libraries.zoom.credentials", "ZoomCredential", "zoom_credentials.json", "zoom_user_id"),
    "telegram_bot": ("core.external_libraries.telegram.credentials", "TelegramCredential", "telegram_credentials.json", "bot_id"),
    "telegram_mtproto": ("core.external_libraries.telegram.credentials", "TelegramCredential", "telegram_credentials.json", "phone_number"),
    "whatsapp": ("core.external_libraries.whatsapp.credentials", "WhatsAppCredential", "whatsapp_credentials.json", "phone_number_id"),
    "whatsapp_web": ("core.external_libraries.whatsapp.credentials", "WhatsAppCredential", "whatsapp_credentials.json", "phone_number_id"),
    "discord_bot": ("core.external_libraries.discord.credentials", "DiscordBotCredential", "discord_bot_credentials.json", "bot_id"),
    "discord_user": ("core.external_libraries.discord.credentials", "DiscordUserCredential", "discord_user_credentials.json", "discord_user_id"),
    "recall": ("core.external_libraries.recall.credentials", "RecallCredential", "recall_credentials.json", "api_key"),
}


class CredentialClient:
    """Reads credentials from local JSON files instead of backend HTTP."""

    def __init__(self, network_interface=None):
        pass  # No network needed

    async def request_credential(
        self,
        integration_type: str,
        user_id: str,
        service_account_id: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        """Read credential from local CredentialsStore."""
        mapping = _STORE_MAP.get(integration_type)
        if not mapping:
            return None

        module_path, class_name, persistence_file, id_field = mapping

        try:
            import importlib
            mod = importlib.import_module(module_path)
            cred_cls = getattr(mod, class_name)

            from core.external_libraries.credential_store import CredentialsStore
            store = CredentialsStore(cred_cls, persistence_file)

            filters = {}
            if service_account_id:
                filters[id_field] = service_account_id

            creds = store.get(user_id, **filters)
            if creds:
                return asdict(creds[0])
        except Exception as e:
            logger.error(f"[CredentialClient] Failed to read local credential: {e}")

        return None

    async def check_credential_access(
        self,
        integration_type: str,
        user_id: str,
        service_account_id: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Check if a credential exists locally."""
        result = await self.request_credential(integration_type, user_id, service_account_id)
        if result:
            return {"status": "success", "has_access": True}
        return {"status": "success", "has_access": False, "reason": "not_found"}

    async def check_tool_access(self, tool_name: str, timeout: float = 10.0) -> bool:
        """All tools are accessible in local mode."""
        return True

    def handle_response(self, packet: Dict[str, Any]) -> bool:
        """No-op in local mode."""
        return False


_credential_client: Optional[CredentialClient] = CredentialClient()


def get_credential_client() -> Optional[CredentialClient]:
    """Get the global credential client instance."""
    return _credential_client


def set_credential_client(client: CredentialClient) -> None:
    """Set the global credential client instance."""
    global _credential_client
    _credential_client = client
