"""Launch menu for White Collar Agent before entering the chat interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import var
from textual.widgets import Button, Input, Select, Static

MenuAction = Literal["start", "exit"]


@dataclass
class MenuResult:
    """Result returned when leaving the menu screen."""

    action: MenuAction
    provider: str
    api_key: str


class SettingsScreen(Container):
    """Simple settings form to choose provider and API key."""

    CSS = """
    SettingsScreen {
        width: 60;
        border: solid #444444;
        padding: 2 3;
        background: #0f0f0f;
    }

    #form-title {
        margin-bottom: 1;
        text-style: bold;
    }

    #provider-label, #apikey-label {
        margin-bottom: 1;
    }

    #provider-select, #apikey-input {
        margin-bottom: 2;
    }

    #actions {
        height: auto;
        content-align: center middle;
        column-gap: 2;
    }
    """

    def __init__(self, provider: str, api_key: str) -> None:
        super().__init__(id="settings")
        self.provider = provider
        self.api_key = api_key

    def compose(self) -> ComposeResult:
        yield Static("Settings", id="form-title")
        yield Static("LLM Provider", id="provider-label")
        yield Select(
            (
                ("OpenAI", "openai"),
                ("Google Gemini", "gemini"),
                ("BytePlus", "byteplus"),
                ("Ollama (remote)", "remote"),
            ),
            id="provider-select",
            value=self.provider,
        )
        yield Static("API Key", id="apikey-label")
        yield Input(
            placeholder="Enter API key",
            password=True,
            id="apikey-input",
            value=self.api_key,
        )
        yield Container(
            Button("Save", id="save"),
            Button("Cancel", id="cancel"),
            id="actions",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.remove()
            return

        if event.button.id == "save":
            select = self.query_one("#provider-select", Select[str])
            api_key_input = self.query_one("#apikey-input", Input)
            provider = select.value or "byteplus"
            api_key = api_key_input.value
            if hasattr(self.app, "save_settings"):
                self.app.save_settings(provider, api_key)
            self.remove()


class MainMenuApp(App[MenuResult | None]):
    """Main menu displayed before launching the chat interface."""

    CSS = """
    Screen {
        align: center middle;
        background: #0b0b0b;
        color: #f5f5f5;
    }

    #menu-panel {
        width: 80;
        border: solid #333333;
        padding: 3 5;
        background: #111111;
        content-align: center middle;
    }

    #logo {
        margin-bottom: 2;
        text-style: bold;
    }

    #buttons {
        height: auto;
        row-gap: 1;
    }

    Button {
        width: 24;
    }
    """

    status_message = var("Use the menu to start the agent.")

    def __init__(self, provider: str, api_key: str) -> None:
        super().__init__()
        self.provider = provider
        self.api_key = api_key

    def compose(self) -> ComposeResult:
        logo_text = Text(
            """
 __        __    _     _         ____      _ _                _             
 \ \      / / __(_) __| | ___   / ___|___ | | | ___ _ __   __| | ___  _ __  
  \ \ /\ / / '_ \ |/ _` |/ _ \ | |   / _ \| | |/ _ \ '_ \ / _` |/ _ \| '_ \ 
   \ V  V /| | | | | (_| |  __/ | |__| (_) | | |  __/ | | | (_| | (_) | | | |
    \_/\_/ |_| |_|_|\__,_|\___|  \____\___/|_|_|\___|_| |_|\__,_|\___/|_| |_|
            """.rstrip("\n"),
            justify="center",
        )

        yield Container(
            Static(logo_text, id="logo"),
            Vertical(
                Button("Start", id="start"),
                Button("Setting", id="settings"),
                Button("Exit", id="exit"),
                id="buttons",
            ),
            id="menu-panel",
        )

    def save_settings(self, provider: str, api_key: str) -> None:
        self.provider = provider
        self.api_key = api_key

    def action_quit(self) -> None:
        self.exit(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.exit(MenuResult(action="start", provider=self.provider, api_key=self.api_key))
        elif event.button.id == "settings":
            if not self.query(SettingsScreen):
                self.mount(SettingsScreen(self.provider, self.api_key))
        elif event.button.id == "exit":
            self.exit(MenuResult(action="exit", provider=self.provider, api_key=self.api_key))


async def launch_menu(default_provider: str, api_key: str) -> Optional[MenuResult]:
    """Launch the menu and return the selected action."""

    app = MainMenuApp(default_provider, api_key)
    return await app.run_async()
