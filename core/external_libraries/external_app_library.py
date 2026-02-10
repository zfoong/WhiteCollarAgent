from abc import ABC, abstractmethod
from typing import Union, Optional, TYPE_CHECKING

from core.external_libraries.credential_store import CredentialsStore
from core.external_libraries.remote_credential_store import RemoteCredentialStore

if TYPE_CHECKING:
    from core.credential_client import CredentialClient


# ---- Interface ----
class ExternalAppLibrary(ABC):
    """
    Base class for external integration libraries.

    Supports both local (CredentialsStore) and remote (RemoteCredentialStore)
    credential storage. New integrations should use RemoteCredentialStore
    for backend-managed credentials.
    """

    # Class-level credential client reference (shared by all integrations)
    _credential_client: Optional["CredentialClient"] = None

    @classmethod
    def set_credential_client(cls, client: "CredentialClient") -> None:
        """
        Set the shared credential client for all integrations.
        This should be called once during agent initialization.
        """
        cls._credential_client = client

    @classmethod
    def get_credential_client(cls) -> Optional["CredentialClient"]:
        """Get the shared credential client."""
        return cls._credential_client

    @classmethod
    @abstractmethod
    def initialize(cls):
        """Initialize the integration. Called during agent startup."""
        ...

    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """Get the human-readable name of this integration."""
        ...

    @classmethod
    @abstractmethod
    def get_credential_store(cls) -> Union[CredentialsStore, RemoteCredentialStore]:
        """
        Get the credential store for this integration.

        Can return either CredentialsStore (legacy local storage) or
        RemoteCredentialStore (backend-managed credentials).
        """
        ...

    @classmethod
    @abstractmethod
    def validate_connection(cls, user_id: str, **kwargs) -> bool:
        """
        Validate that a connection exists for the user.

        Note: For async validation, override validate_connection_async instead.
        This method is kept for backward compatibility.
        """
        ...

    @classmethod
    async def validate_connection_async(cls, user_id: str, **kwargs) -> bool:
        """
        Async version of validate_connection.

        Override this method for integrations using RemoteCredentialStore.
        Default implementation calls the sync version.
        """
        return cls.validate_connection(user_id, **kwargs)
