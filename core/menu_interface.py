"""Launcher menu shown before entering the chat TUI."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Input, Select, Static


LOGO_TEXT = r"""
 __        ___     _     _         ____      _ _           
 \ \      / / |__ (_) __| | ___   / ___|__ _| | | ___ _ __ 
  \ \ /\ / /| '_ \| |/ _` |/ _ \ | |   / _` | | |/ _ \ '__|
   \ V  V / | | | | | (_| |  __/ | |__| (_| | | |  __/ |   
    \_/\_/  |_| |_|_|\__,_|\___|  \____\__,_|_|_|\___|_|   
"""

_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "byteplus": "BYTEPLUS_API_KEY",
}


@dataclass
class MenuResult:
    """Outcome returned from the launcher menu."""

    action: str
    provider: Optional[str] = None
    api_key: Optional[str] = None


class _SettingsScreen(Screen):
    """Simple settings form for provider + API key."""

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, provider: str | None, api_key: str | None) -> None:
        super().__init__()
        self._provider = provider or "byteplus"
        self._api_key = api_key or ""

    def compose(self) -> ComposeResult:  # pragma: no cover - declarative UI
        yield Container(
            Static("Settings", id="settings-title"),
            Static("Choose your LLM provider and API key.", id="settings-subtitle"),
            Select(
                id="provider-select",
                options=[
                    ("BytePlus", "byteplus"),
                    ("OpenAI", "openai"),
                    ("Gemini", "gemini"),
                    ("Remote (Ollama)", "remote"),
                ],
                value=self._provider,
            ),
            Input(
                id="api-key-input",
                placeholder="Enter API key for the selected provider",
                password=True,
                value=self._api_key,
            ),
            Static("Keys are stored for this session only.", id="settings-hint"),
            Horizontal(
                Button("Save", id="save-settings", variant="success"),
                Button("Cancel", id="cancel-settings", variant="warning"),
                id="settings-actions",
            ),
            id="settings-container",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-settings":
            self.app.pop_screen()
            return

        if event.button.id == "save-settings":
            provider_select = self.query_one("#provider-select", Select)
            api_key_input = self.query_one("#api-key-input", Input)

            launcher: _LauncherApp = self.app  # type: ignore[assignment]
            launcher.update_settings(provider_select.value, api_key_input.value)
            self.app.pop_screen()


class _LauncherApp(App[None]):
    """Minimal Textual app that shows the startup menu."""

    CSS = """
    Screen {
        align: center middle;
        background: #0f0f0f;
        color: #f5f5f5;
    }

    #logo {
        content-align: center middle;
        text-style: bold;
        margin: 2 0;
        width: 90%;
    }

    #menu-container {
        width: 60;
        border: solid #333333;
        padding: 2;
        align: center middle;
        background: #141414;
    }

    Button {
        width: 20;
        margin: 1 0;
    }

    #settings-container {
        width: 60;
        border: solid #333333;
        padding: 2;
        background: #141414;
        align: center middle;
        height: auto;
    }

    #settings-title {
        text-style: bold;
        content-align: center middle;
        margin-bottom: 1;
    }

    #settings-subtitle, #settings-hint {
        color: #cccccc;
        margin-bottom: 1;
    }

    #settings-actions {
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self, provider: str | None, api_key: str | None) -> None:
        super().__init__()
        self._provider = provider or "byteplus"
        self._api_key = api_key or ""
        self.menu_result: MenuResult | None = None

    def compose(self) -> ComposeResult:  # pragma: no cover - declarative UI
        yield Vertical(
            Static(LOGO_TEXT, id="logo"),
            Container(
                Button("Start", id="start", variant="success"),
                Button("Setting", id="settings", variant="primary"),
                Button("Exit", id="exit", variant="error"),
                id="menu-container",
            ),
        )

    def update_settings(self, provider: str | None, api_key: str | None) -> None:
        if provider:
            self._provider = provider
        if api_key is not None:
            self._api_key = api_key

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.menu_result = MenuResult("start", self._provider, self._api_key)
            self.exit()
        elif event.button.id == "exit":
            self.menu_result = MenuResult("exit", self._provider, self._api_key)
            self.exit()
        elif event.button.id == "settings":
            self.push_screen(_SettingsScreen(self._provider, self._api_key))


class MenuInterface:
    """Wrapper to show a launcher menu before starting the TUI."""

    def __init__(self) -> None:
        self._provider = os.getenv("LLM_PROVIDER") or "byteplus"
        self._api_key = self._load_api_key(self._provider)

    def _load_api_key(self, provider: str | None) -> str:
        if provider is None:
            return ""
        env_var = _PROVIDER_ENV.get(provider)
        if not env_var:
            return ""
        return os.getenv(env_var, "")

    async def show(self) -> MenuResult:
        app = _LauncherApp(self._provider, self._api_key)
        await app.run_async()
        result = app.menu_result or MenuResult("exit", self._provider, self._api_key)
        self._provider, self._api_key = result.provider, result.api_key
        return result

    def apply_api_key(self, provider: str | None, api_key: str | None) -> None:
        if not provider or not api_key:
            return
        env_var = _PROVIDER_ENV.get(provider)
        if env_var:
            os.environ[env_var] = api_key


async def launch_menu() -> MenuResult:
    """Convenience helper to launch the menu and return the selection."""

    menu = MenuInterface()
    return await menu.show()
