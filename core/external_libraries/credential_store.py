from dataclasses import dataclass, asdict
from typing import Dict, List, TypeVar, Generic, Type
import json
from pathlib import Path
from core.config import AGENT_WORKSPACE_ROOT

# Base credential class
@dataclass
class Credential:
    user_id: str
    UNIQUE_KEYS: tuple = ()

    def to_dict(self) -> Dict:
        """Convert credential to dictionary."""
        return asdict(self)

T = TypeVar('T', bound=Credential)

class CredentialsStore(Generic[T]):
    """
    Generic credential store with local JSON persistence.
    Each store handles a single credential type.
    """
    def __init__(self, credential_cls: Type[T], persistence_file: str):
        self.credential_cls = credential_cls
        self.credentials: Dict[str, List[T]] = {}
        self.persistence_path = Path(AGENT_WORKSPACE_ROOT) / ".credentials" / persistence_file
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self):
        """Load credentials from disk."""
        if not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, "r") as f:
                data = json.load(f)

            for user_id, cred_list in data.items():
                self.credentials[user_id] = [self.credential_cls(**item) for item in cred_list]
        except Exception as e:
            print(f"[CredentialsStore] Failed to load credentials: {e}")

    def save(self):
        """Save credentials to disk."""
        output = {
            user_id: [asdict(c) for c in creds]
            for user_id, creds in self.credentials.items()
        }

        try:
            with open(self.persistence_path, "w") as f:
                json.dump(output, f, indent=2)
        except Exception as e:
            print(f"[CredentialsStore] Failed to save credentials: {e}")

    def add(self, credential: T) -> None:
        """Add or update a credential."""
        creds = self.credentials.setdefault(credential.user_id, [])

        # Replace if unique keys match
        for i, existing in enumerate(creds):
            if all(getattr(existing, k, None) == getattr(credential, k, None)
                   for k in getattr(credential, "UNIQUE_KEYS", ())):
                creds[i] = credential
                self.save()
                return

        creds.append(credential)
        self.save()

    def get(self, user_id: str, **filters) -> List[T]:
        """
        Get credentials for a user.
        - filters: optional key=value pairs to filter
        """
        creds = self.credentials.get(user_id, [])
        for key, value in filters.items():
            creds = [c for c in creds if getattr(c, key, None) == value]
        return creds

    def remove(self, user_id: str, **filters) -> None:
        """
        Remove credentials for a user.
        - filters: optional key=value pairs to match credentials to remove
        """
        if user_id not in self.credentials:
            return

        creds = self.credentials[user_id]
        remaining = [c for c in creds if not all(getattr(c, k, None) == v for k, v in filters.items())]

        if remaining:
            self.credentials[user_id] = remaining
        else:
            self.credentials.pop(user_id)

        self.save()
