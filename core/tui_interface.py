"""Textual-based terminal user interface for interacting with the agent."""
from __future__ import annotations

import asyncio
import os
import time
from asyncio import Queue, QueueEmpty
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional, Tuple

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import var
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.widgets import Input, Static
from textual.widgets import RichLog as _BaseLog
from textual.widgets import ListView, ListItem, Label

from core.logger import logger
from core.models.model_registry import MODEL_REGISTRY
from core.models.types import InterfaceType
from core.models.provider_config import PROVIDER_CONFIG


def _save_settings_to_env(provider: str, api_key: str) -> bool:
    """Save provider and API key to .env file.

    Args:
        provider: The LLM provider name
        api_key: The API key for the provider

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        env_path = Path(".env")
        env_lines: list[str] = []

        # Read existing .env file if it exists
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        # Get the API key environment variable name for this provider
        key_lookup = {
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "byteplus": "BYTEPLUS_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        api_key_env = key_lookup.get(provider)

        # Update or add the LLM_PROVIDER and API key
        updated_provider = False
        updated_api_key = False

        new_lines = []
        for line in env_lines:
            stripped = line.strip()
            if stripped.startswith("LLM_PROVIDER="):
                new_lines.append(f"LLM_PROVIDER={provider}\n")
                updated_provider = True
            elif api_key_env and stripped.startswith(f"{api_key_env}="):
                if api_key:
                    new_lines.append(f"{api_key_env}={api_key}\n")
                    updated_api_key = True
                # Skip empty API key lines (don't write them)
            else:
                new_lines.append(line if line.endswith("\n") else line + "\n")

        # Add new entries if not updated
        if not updated_provider:
            new_lines.append(f"LLM_PROVIDER={provider}\n")

        if api_key_env and api_key and not updated_api_key:
            new_lines.append(f"{api_key_env}={api_key}\n")

        # Write back to .env file
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f"[SETTINGS] Saved provider={provider} to .env file")
        return True

    except Exception as e:
        logger.error(f"[SETTINGS] Failed to save to .env file: {e}")
        return False


def _get_api_key_env_name(provider: str) -> Optional[str]:
    """Get the environment variable name for a provider's API key."""
    if provider not in PROVIDER_CONFIG:
        return None
    return PROVIDER_CONFIG[provider].api_key_env

if False:  # pragma: no cover
    from core.agent_base import AgentBase  # type: ignore


class _ContextMenu(OptionList):
    """Simple context menu for copy operations."""

    DEFAULT_CSS = """
    _ContextMenu {
        width: 20;
        height: auto;
        border: ascii #ff4f18;
        background: #0a0a0a;
        layer: overlay;
    }

    _ContextMenu > .option-list--option {
        color: #e5e5e5;
        padding: 0 1;
    }

    _ContextMenu > .option-list--option-highlighted {
        background: #ff4f18;
        color: #ffffff;
    }
    """

    def __init__(self, text_to_copy: str, x: int, y: int) -> None:
        super().__init__(Option("Copy text", id="copy"))
        self.text_to_copy = text_to_copy
        self.styles.offset = (x, y)
        # Set border to use ASCII characters
        self.border_title = None
        self.styles.border = ("ascii", "#ff4f18")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle menu selection."""
        if event.option_id == "copy":
            try:
                # Try using pyperclip first for better compatibility
                import pyperclip
                pyperclip.copy(self.text_to_copy)
                self.app.notify("Text copied!", severity="information", timeout=2)
            except ImportError:
                # Fallback to Textual's method if pyperclip not available
                try:
                    self.app.copy_to_clipboard(self.text_to_copy)
                    self.app.notify("Text copied!", severity="information", timeout=2)
                except Exception as e:
                    self.app.notify(f"Copy failed: {str(e)}", severity="error", timeout=3)
        self.remove()

    def on_blur(self) -> None:
        """Close menu when focus is lost."""
        self.remove()

    def on_key(self, event: events.Key) -> None:
        """Handle escape key to close the menu."""
        if event.key == "escape":
            self.remove()
            event.stop()


class _PasteableInput(Input):
    """Input widget with enhanced paste support using pyperclip."""

    BINDINGS = [
        ("ctrl+v", "paste_from_clipboard", "Paste"),
        ("shift+insert", "paste_from_clipboard", "Paste"),
    ]

    def action_paste_from_clipboard(self) -> None:
        """Paste text from clipboard using pyperclip for better compatibility."""
        try:
            import pyperclip
            text = pyperclip.paste()
            if text:
                # Insert text at cursor position
                self.insert_text_at_cursor(text)
        except ImportError:
            # Fallback to default paste action
            self.action_paste()
        except Exception:
            # Fallback to default paste action on any error
            self.action_paste()


class _ConversationLog(_BaseLog):
    """RichLog wrapper with robust wrapping + reflow on resize."""

    can_focus = True

    def __init__(self, *args, **kwargs) -> None:
        # RichLog params: wrap off by default, min_width=78; override both
        kwargs.setdefault("markup", True)
        kwargs.setdefault("highlight", False)
        kwargs.setdefault("wrap", True)  # enable word-wrapping (RichLog)
        kwargs.setdefault("min_width", 1)  # let width track the pane size
        super().__init__(*args, **kwargs)

        # Keep a copy of everything written so it can be reflowed on resize
        self._history: list[RenderableType] = []
        # Track entry keys to their history index for updates
        self._entry_keys: dict[str, int] = {}
        # Store plain text for each entry for copy functionality
        self._text_content: list[str] = []
        # Track line ranges for each message entry (start_line, end_line)
        self._line_ranges: list[Tuple[int, int]] = []

    def append_text(self, content) -> None:
        # Normalize to Rich Text, enable folding of long tokens
        text: Text = content if isinstance(content, Text) else Text(str(content))
        text.no_wrap = False
        text.overflow = "fold"  # split unbreakable runs (URLs / IDs)
        self.append_renderable(text)

    def append_markup(self, markup: str) -> None:
        self.append_text(Text.from_markup(markup))

    def append_renderable(self, renderable: RenderableType, entry_key: Optional[str] = None) -> None:
        # Write using expand/shrink so width follows the widget on resize
        index = len(self._history)
        self._history.append(renderable)
        if entry_key:
            self._entry_keys[entry_key] = index

        # Extract and store plain text content
        text_content = self._extract_text(renderable)
        self._text_content.append(text_content)

        # Track the line range before writing
        start_line = len(self.lines)

        self.write(renderable, expand=True, shrink=True)

        # Track the line range after writing
        end_line = len(self.lines) - 1
        self._line_ranges.append((start_line, end_line))

    def update_renderable(self, entry_key: str, renderable: RenderableType) -> None:
        """Update an existing entry by key."""
        if entry_key not in self._entry_keys:
            return
        index = self._entry_keys[entry_key]
        if 0 <= index < len(self._history):
            self._history[index] = renderable
            # Re-render the entire history
            self._reflow_history()

    def clear(self) -> None:
        """Clear the log and the preserved history."""

        self._history.clear()
        self._entry_keys.clear()
        self._text_content.clear()
        self._line_ranges.clear()
        super().clear()

    def _reflow_history(self) -> None:
        """Re-render stored entries so Rich recalculates wrapping."""

        if not self._history:
            return

        history = list(self._history)
        super().clear()

        # Rebuild line ranges as we reflow
        self._line_ranges.clear()
        for renderable in history:
            start_line = len(self.lines)
            self.write(renderable, expand=True, shrink=True)
            end_line = len(self.lines) - 1
            self._line_ranges.append((start_line, end_line))

    def _extract_text(self, renderable: RenderableType) -> str:
        """Extract plain text from a renderable object, excluding labels."""
        if isinstance(renderable, Text):
            return renderable.plain
        elif isinstance(renderable, str):
            return renderable
        elif isinstance(renderable, Table):
            # Extract only the message content (second column), skip the label (first column)
            try:
                # Access the table columns - we want the second column (index 1)
                if len(renderable.columns) >= 2:
                    message_column = renderable.columns[1]
                    # Extract text from all cells in the message column
                    text_parts = []
                    if hasattr(message_column, '_cells'):
                        for cell in message_column._cells:
                            if isinstance(cell, Text):
                                text_parts.append(cell.plain)
                            elif isinstance(cell, str):
                                text_parts.append(cell)
                            else:
                                text_parts.append(str(cell))
                    return " ".join(text_parts)
                else:
                    # Fallback if table structure is unexpected
                    from io import StringIO
                    from rich.console import Console
                    string_io = StringIO()
                    console = Console(file=string_io, force_terminal=False, force_jupyter=False, width=200)
                    console.print(renderable)
                    return string_io.getvalue().strip()
            except (AttributeError, IndexError, TypeError):
                # Fallback: use Rich Console to render to plain text
                from io import StringIO
                from rich.console import Console
                string_io = StringIO()
                console = Console(file=string_io, force_terminal=False, force_jupyter=False, width=200)
                console.print(renderable)
                return string_io.getvalue().strip()
        else:
            # Fallback: try to convert to string
            return str(renderable)

    def _get_message_at_line(self, line_number: int) -> Optional[int]:
        """Get the message index for a given line number."""
        if not self._line_ranges:
            return None

        # Find which message contains this line number
        for msg_index, (start_line, end_line) in enumerate(self._line_ranges):
            if start_line <= line_number <= end_line:
                return msg_index

        return None

    def on_click(self, event: events.Click) -> None:
        """Handle click events to show copy menu for the clicked cell."""
        # Remove any existing context menu
        for menu in self.app.query("_ContextMenu"):
            menu.remove()

        # Calculate the actual line number accounting for scroll offset
        # event.y is relative to the widget, we need to add scroll offset
        clicked_y = event.y + self.scroll_offset.y

        # Find which message was clicked using line ranges
        clicked_index = self._get_message_at_line(clicked_y)

        if clicked_index is not None and 0 <= clicked_index < len(self._text_content):
            text_to_copy = self._text_content[clicked_index]
        else:
            # No valid message found at this position
            return

        if text_to_copy.strip():
            # Create context menu at click position
            menu = _ContextMenu(text_to_copy, event.screen_x, event.screen_y)
            self.app.screen.mount(menu)
            menu.focus()

    def on_resize(self, event: events.Resize) -> None:  # pragma: no cover - UI layout
        """Force a reflow when the widget width changes.

        Without this, RichLog may retain the old line breaks, causing text to
        overflow or leave unused space until new content is added.
        """

        super().on_resize(event)
        self._reflow_history()
        self.refresh(layout=True, repaint=True)


TimelineEntry = Tuple[str, str, str]


@dataclass
class _ActionEntry:
    """Container for agent action updates."""

    kind: str
    message: str
    style: str = "action"
    is_completed: bool = False
    parent_task: Optional[str] = None  # Task name if this action belongs to a task


@dataclass
class _ActionUpdate:
    """Container for action update operations."""
    operation: str  # "add" or "update"
    entry: Optional[_ActionEntry] = None
    entry_key: Optional[str] = None


class _CraftApp(App):
    """Textual application rendering the Craft Agent TUI."""

    CSS = """
    Screen {
        layout: vertical;
        background: #000000;
        color: #e5e5e5;
    }

    /* Shared chrome */
    #top-region {
        height: 1fr;
        min-width: 0;
    }

    #chat-panel, #action-panel {
        height: 100%;
        border: solid #2a2a2a;
        border-title-align: left;
        border-title-color: #a0a0a0;
        background: #000000;
        margin: 0 1;
        min-width: 0;  /* allow panels to shrink with the terminal */
    }

    #chat-log, #action-log {
        text-wrap: wrap;
        text-overflow: fold;
        overflow-x: hidden;
        min-width: 0;  /* enable reflow instead of clamped min-content width */
        background: #000000;
    }

    #chat-panel {
        width: 2fr;
    }

    #action-panel {
        width: 1fr;
    }

    TextLog {
        height: 1fr;
        padding: 0 1;
        overflow-x: hidden;
        background: #000000;
    }

    #bottom-region {
        height: auto;
        border-top: solid #1a1a1a;
        padding: 0;
        background: #000000;
    }

    #status-bar {
        height: 1;
        min-height: 1;
        text-wrap: nowrap;
        overflow: hidden;
        text-style: bold;
        color: #a0a0a0;
        background: #000000;
        padding: 0 1;
    }

    #chat-input {
        border: solid #2a2a2a;
        background: #0a0a0a;
        color: #e5e5e5;
        margin: 0 1;
    }

    #chat-input:focus {
        border: solid #ff4f18;
    }

    /* Menu layer */
    #menu-layer {
        align: center middle;
        content-align: center middle;
        background: #000000;
    }

    #menu-panel {
        width: 90;
        max-width: 100%;
        max-height: 95%;
        border: solid #2a2a2a;
        background: #000000;
        padding: 3 5;
        content-align: center middle;
        overflow: auto;
    }

    #menu-panel.-hidden {
        display: none;
    }

    #menu-logo {
        text-style: bold;
        margin-bottom: 1;
        content-align: center middle;
    }

    #menu-copy {
        color: #a0a0a0;
        margin-bottom: 1;
    }

    #provider-hint {
        color: #a0a0a0;
        text-style: bold;
    }

    #menu-hint {
        color: #666666;
    }

    #menu-hint.-warning {
        color: #ff8c00;
    }

    #menu-hint.-ready {
        color: #00cc00;
    }

    /* Command-prompt style options */
    #menu-options {
        width: 24;
        height: auto;
        margin-top: 1;
        content-align: center middle;
        background: transparent;
        border: none;
    }

    #menu-options > ListItem {
        padding: 0 0;
    }

    /* Default item text */
    .menu-item {
        color: #a0a0a0;
    }

    /* Highlight for list selections */
    #menu-options > ListItem.--highlight .menu-item,
    #provider-options > ListItem.--highlight .menu-item,
    #settings-actions-list > ListItem.--highlight .menu-item {
        background: #ff4f18;
        color: #ffffff;
        text-style: bold;
    }

    /* Provider options list in settings */
    #provider-options {
        width: 28;
        height: auto;
        margin: 1 0;
        background: transparent;
        border: none;
    }

    #provider-options > ListItem {
        padding: 0 0;
    }

    /* Settings card */
    #settings-card {
        width: 70;
        max-width: 100%;
        max-height: 90%;
        border: solid #2a2a2a;
        background: #000000;
        padding: 2 3 3 3;
        content-align: center top;
        overflow: auto;
    }

    #settings-card Static {
        color: #a0a0a0;
    }

    #settings-title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
    }

    #settings-card Input {
        width: 100%;
        border: solid #2a2a2a;
        background: #0a0a0a;
        color: #e5e5e5;
    }

    #settings-card Input:focus {
        border: solid #ff4f18;
    }

    #model-display {
        color: #ff4f18;
        text-style: bold;
        margin-top: 1;
    }

    #api-key-label {
        margin-top: 1;
    }

    /* Settings actions styled like a prompt list */
    #settings-actions-list {
        width: 24;
        height: auto;
        margin-top: 1;
        content-align: center middle;
        background: transparent;
        border: none;
    }

    #settings-actions-list > ListItem {
        padding: 0 0;
    }

    #chat-layer.-hidden,
    #menu-layer.-hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    status_text = var("Status: Idle")
    show_menu = var(True)
    show_settings = var(False)

    _STATUS_PREFIX = " "
    _STATUS_GAP = 4
    _STATUS_INITIAL_PAUSE = 6

    # Icons for task/action status
    _ICON_COMPLETED = "+"
    _ICON_LOADING_FRAMES = ["●", "○"]  # Animated loading icons

    _MENU_ITEMS = [
        ("menu-start", "start"),
        ("menu-settings", "setting"),
        ("menu-exit", "exit"),
    ]

    _SETTINGS_PROVIDER_TEXTS = [
        "OpenAI",
        "Google Gemini",
        "BytePlus",
        "Anthropic",
        "Ollama (remote)",
    ]

    _SETTINGS_PROVIDER_VALUES = [
        "openai",
        "gemini",
        "byteplus",
        "anthropic",
        "remote",
    ]

    _SETTINGS_ACTION_TEXTS = [
        "save",
        "cancel",
    ]

    _PROVIDER_API_KEY_NAMES = {
        "openai": "OpenAI",
        "gemini": "Google Gemini",
        "byteplus": "BytePlus",
        "anthropic": "Anthropic",
        "remote": "Ollama (remote)",
    }

    def _get_api_key_label(self) -> str:
        """Get the label for the API key input based on current provider."""
        provider_name = self._PROVIDER_API_KEY_NAMES.get(self._provider, self._provider)
        return f"API Key for {provider_name}"

    def _get_model_for_provider(self, provider: str) -> str:
        """Get the LLM model name for a provider from the model registry."""
        if provider in MODEL_REGISTRY:
            return MODEL_REGISTRY[provider].get(InterfaceType.LLM, "Unknown")
        return "Unknown"

    def __init__(self, interface: "TUIInterface", provider: str, api_key: str) -> None:
        super().__init__()
        self._interface = interface
        self._status_message: str = "Idle"
        self._status_offset: int = 0
        self._status_pause: int = self._STATUS_INITIAL_PAUSE
        self._last_rendered_status: str = ""
        self._provider = provider
        self._api_key = api_key
        # Track saved API keys per provider (to know whether to reset on provider change)
        self._saved_api_keys: dict[str, str] = {provider: api_key} if api_key else {}
        # Track the provider selected in settings before saving
        self._settings_provider: str = provider

    def _is_api_key_configured(self) -> bool:
        """Check if an API key is configured for the current provider."""
        # Remote (Ollama) doesn't need API key
        if self._provider == "remote":
            return True

        # Check local setting first
        if self._api_key:
            return True

        # Check environment variable
        api_key_env = _get_api_key_env_name(self._provider)
        if api_key_env and os.getenv(api_key_env):
            return True

        return False

    def _get_menu_hint(self) -> str:
        """Generate the menu hint text based on API key configuration status."""
        if self._is_api_key_configured():
            return "API key configured. Press Enter on 'start' to begin."
        else:
            return "No API key found. Please configure in Settings before starting."

    def compose(self) -> ComposeResult:  # pragma: no cover - declarative layout
        yield Container(
            Container(
                Static(self._logo_text(), id="menu-logo"),
                Vertical(
                    Static(f"Model Provider: {self._provider}", id="provider-hint"),
                    Static(
                        self._get_menu_hint(),
                        id="menu-hint",
                    ),
                    id="menu-copy",
                ),
                ListView(
                    ListItem(Label("start", classes="menu-item"), id="menu-start"),
                    ListItem(Label("setting", classes="menu-item"), id="menu-settings"),
                    ListItem(Label("exit", classes="menu-item"), id="menu-exit"),
                    id="menu-options",
                ),
                id="menu-panel",
            ),
            id="menu-layer",
        )

        yield Container(
            Horizontal(
                Container(
                    _ConversationLog(id="chat-log"),
                    id="chat-panel",
                ),
                Container(
                    _ConversationLog(id="action-log"),
                    id="action-panel",
                ),
                id="top-region",
            ),
            Vertical(
                Static(
                    Text(self.status_text, no_wrap=True, overflow="crop"),
                    id="status-bar",
                ),
                Input(placeholder="Type a message and press Enter…", id="chat-input"),
                id="bottom-region",
            ),
            id="chat-layer",
        )

    # ────────────────────────────── menu helpers ─────────────────────────────

    def _logo_text(self) -> Text:
        logo_lines = [
            "░█░█░█░█░▀█▀░▀█▀░█▀▀░░░█▀▀░█▀█░█░░░█░░░█▀█░█▀▄░░░█▀█░█▀▀░█▀▀░█▀█░▀█▀",
            "░█▄█░█▀█░░█░░░█░░█▀▀░░░█░░░█░█░█░░░█░░░█▀█░█▀▄░░░█▀█░█░█░█▀▀░█░█░░█░",
            "░▀░▀░▀░▀░▀▀▀░░▀░░▀▀▀░░░▀▀▀░▀▀▀░▀▀▀░▀▀▀░▀░▀░▀░▀░░░▀░▀░▀▀▀░▀▀▀░▀░▀░░▀░",
        ]
        text = Text("\n".join(logo_lines), justify="center")
        agent_len = len(logo_lines[0][-19:])
        highlight_style = "#FF4F18"
        offset = 0
        for line in logo_lines:
            start_col = len(line) - agent_len
            text.stylize(highlight_style, offset + start_col, offset + start_col + agent_len)
            offset += len(line) + 1
        return text

    def _open_settings(self) -> None:
        if self.query("#settings-card"):
            return

        # Hide the main menu panel while settings are open
        self.show_settings = True

        # Reset settings provider tracking to current provider
        self._settings_provider = self._provider

        # Get model name for current provider
        model_name = self._get_model_for_provider(self._provider)

        settings = Container(
            Static("Settings", id="settings-title"),
            Static("LLM Provider"),
            ListView(
                ListItem(Label("OpenAI", classes="menu-item")),
                ListItem(Label("Google Gemini", classes="menu-item")),
                ListItem(Label("BytePlus", classes="menu-item")),
                ListItem(Label("Anthropic", classes="menu-item")),
                ListItem(Label("Ollama (remote)", classes="menu-item")),
                id="provider-options",
            ),
            Static(f"Model: {model_name}", id="model-display"),
            Static(self._get_api_key_label(), id="api-key-label"),
            _PasteableInput(
                placeholder="Enter API key (Ctrl+V to paste)",
                password=False,
                id="api-key-input",
                value=self._api_key,
            ),
            ListView(
                ListItem(Label("save", classes="menu-item"), id="settings-save"),
                ListItem(Label("cancel", classes="menu-item"), id="settings-cancel"),
                id="settings-actions-list",
            ),
            id="settings-card",
        )

        self.query_one("#menu-layer").mount(settings)
        self.call_after_refresh(self._init_settings_provider_selection)

    def _close_settings(self) -> None:
        for card in self.query("#settings-card"):
            card.remove()

        self.show_settings = False

        # Update the menu hint to reflect current API key status
        self._update_menu_hint()

        # Return focus to the main menu list
        if self.show_menu and self.query("#menu-options"):
            menu = self.query_one("#menu-options", ListView)
            if menu.index is None:
                menu.index = 0
            menu.focus()
            self._refresh_menu_prefixes()

    def _update_menu_hint(self) -> None:
        """Update the menu hint text and styling based on API key status."""
        if not self.query("#menu-hint"):
            return

        hint = self.query_one("#menu-hint", Static)
        hint.update(self._get_menu_hint())

        # Update styling based on API key status
        is_configured = self._is_api_key_configured()
        hint.set_class(not is_configured, "-warning")
        hint.set_class(is_configured, "-ready")

    def _save_settings(self) -> None:
        api_key_input = self.query_one("#api-key-input", _PasteableInput)

        provider_value = self._provider
        if self.query("#provider-options"):
            providers = self.query_one("#provider-options", ListView)
            idx = providers.index if providers.index is not None else 0
            if 0 <= idx < len(self._SETTINGS_PROVIDER_VALUES):
                provider_value = self._SETTINGS_PROVIDER_VALUES[idx]

        self._provider = provider_value
        self._api_key = api_key_input.value

        # Save the API key for this provider (so it persists when switching providers)
        if self._api_key:
            self._saved_api_keys[self._provider] = self._api_key

        # Persist settings to .env file and update environment variables
        if self._api_key:
            _save_settings_to_env(self._provider, self._api_key)

            # Also update current process environment variables
            api_key_env = _get_api_key_env_name(self._provider)
            if api_key_env:
                os.environ[api_key_env] = self._api_key
            os.environ["LLM_PROVIDER"] = self._provider

            self.notify("Settings saved!", severity="information", timeout=2)
        else:
            self.notify("API key is empty - settings not saved to file", severity="warning", timeout=3)

        self.query_one("#provider-hint", Static).update(
            f"Model Provider: {self._provider}"
        )
        self._close_settings()

    def _start_chat(self) -> None:
        # Check if API key is required and configured
        api_key_required = self._provider not in ("remote",)  # Ollama doesn't need API key

        if api_key_required:
            # Check environment variable first, then local setting
            api_key_env = _get_api_key_env_name(self._provider)
            env_api_key = os.getenv(api_key_env, "") if api_key_env else ""
            effective_api_key = self._api_key or env_api_key

            if not effective_api_key:
                self.notify(
                    f"API key required! Please configure your {self._PROVIDER_API_KEY_NAMES.get(self._provider, self._provider)} API key in Settings.",
                    severity="error",
                    timeout=5,
                )
                return

        # Check if we need to reinitialize BEFORE updating the provider:
        # 1. LLM not initialized yet, OR
        # 2. Provider has changed from what's currently configured
        current_provider = self._interface._agent.llm.provider
        needs_reinit = (
            not self._interface._agent.is_llm_initialized or
            current_provider != self._provider
        )

        # Configure provider (updates environment variables)
        self._interface.configure_provider(self._provider, self._api_key)

        if needs_reinit:
            success = self._interface._agent.reinitialize_llm(self._provider)
            if not success:
                self.notify(
                    f"Failed to initialize LLM. Please check your API key in Settings.",
                    severity="error",
                    timeout=5,
                )
                return

        self._close_settings()
        self.show_menu = False
        self._interface.notify_provider(self._provider)

    async def on_mount(self) -> None:  # pragma: no cover - UI lifecycle
        self.query_one("#chat-panel").border_title = "Chat"
        self.query_one("#action-panel").border_title = "Action"

        # Runtime safeguard: enforce wrapping on the logs even if CSS/props vary by version
        chat_log = self.query_one("#chat-log", _ConversationLog)
        action_log = self.query_one("#action-log", _ConversationLog)

        chat_log.styles.text_wrap = "wrap"
        action_log.styles.text_wrap = "wrap"
        chat_log.styles.text_overflow = "fold"
        action_log.styles.text_overflow = "fold"

        self.set_interval(0.1, self._flush_pending_updates)
        self.set_interval(0.2, self._tick_status_marquee)
        self.set_interval(0.5, self._tick_loading_animation)  # Loading icon animation
        self._sync_layers()

        # Initialize menu selection visuals and API key status
        if self.show_menu:
            menu = self.query_one("#menu-options", ListView)
            menu.index = 0
            menu.focus()
            self._refresh_menu_prefixes()
            self._update_menu_hint()

    def clear_logs(self) -> None:
        """Clear chat and action logs from the display."""

        chat_log = self.query_one("#chat-log", _ConversationLog)
        action_log = self.query_one("#action-log", _ConversationLog)
        chat_log.clear()
        action_log.clear()

    def watch_show_menu(self, show: bool) -> None:
        self._sync_layers()

    def watch_show_settings(self, show: bool) -> None:
        # Hide / show the main menu panel when settings are toggled
        if self.query("#menu-panel"):
            menu_panel = self.query_one("#menu-panel")
            menu_panel.set_class(show, "-hidden")

    def _sync_layers(self) -> None:
        menu_layer = self.query_one("#menu-layer")
        chat_layer = self.query_one("#chat-layer")
        menu_layer.set_class(self.show_menu is False, "-hidden")
        chat_layer.set_class(self.show_menu is True, "-hidden")

        if not self.show_menu:
            chat_input = self.query_one("#chat-input", Input)
            chat_input.focus()
            return

        # If settings are open, focus provider list first
        if self.show_settings and self.query("#provider-options"):
            providers = self.query_one("#provider-options", ListView)
            if providers.index is None:
                providers.index = 0
            providers.focus()
            self._refresh_provider_prefixes()
            self._refresh_settings_actions_prefixes()
            return

        # Menu visible: focus the list and refresh prefixes
        if self.query("#menu-options"):
            menu = self.query_one("#menu-options", ListView)
            if menu.index is None:
                menu.index = 0
            menu.focus()
            self._refresh_menu_prefixes()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        event.input.value = ""
        await self._interface.submit_user_message(message)

    async def action_quit(self) -> None:  # pragma: no cover - user-triggered
        await self._interface.request_shutdown()
        await super().action_quit()

    def _flush_pending_updates(self) -> None:
        chat_log = self.query_one("#chat-log", _ConversationLog)
        action_log = self.query_one("#action-log", _ConversationLog)
        while True:
            try:
                label, message, style = self._interface.chat_updates.get_nowait()
            except QueueEmpty:
                break
            entry = self._interface.format_chat_entry(label, message, style)
            chat_log.append_renderable(entry)

        while True:
            try:
                action_update = self._interface.action_updates.get_nowait()
            except QueueEmpty:
                break

            if action_update.operation == "add":
                entry = self._interface.format_action_entry(action_update.entry)
                action_log.append_renderable(entry, entry_key=action_update.entry_key)
            elif action_update.operation == "update":
                # Get the updated entry from the tracked entries
                if action_update.entry_key in self._interface._task_action_entries:
                    updated_entry = self._interface._task_action_entries[action_update.entry_key]
                    renderable = self._interface.format_action_entry(updated_entry)
                    action_log.update_renderable(action_update.entry_key, renderable)

        while True:
            try:
                status = self._interface.status_updates.get_nowait()
            except QueueEmpty:
                break
            self._set_status(status)

    async def on_shutdown_request(self, event: events.ShutdownRequest) -> None:
        await self._interface.request_shutdown()

    def _set_status(self, status: str) -> None:
        self._status_message = status
        self._status_offset = 0
        self._status_pause = self._STATUS_INITIAL_PAUSE
        self._render_status()

    def _tick_status_marquee(self) -> None:
        status_bar = self.query_one("#status-bar", Static)
        width = status_bar.size.width or self.size.width or (
            len(self._STATUS_PREFIX) + len(self._status_message)
        )
        available = max(0, width - len(self._STATUS_PREFIX))

        if available <= 0 or len(self._status_message) <= available:
            self._status_offset = 0
            self._status_pause = self._STATUS_INITIAL_PAUSE
        else:
            if self._status_pause > 0:
                self._status_pause -= 1
            else:
                scroll_span = len(self._status_message) + self._STATUS_GAP
                self._status_offset = (self._status_offset + 1) % scroll_span
                if self._status_offset == 0:
                    self._status_pause = self._STATUS_INITIAL_PAUSE

        self._render_status()

    def _tick_loading_animation(self) -> None:
        """Update loading animation frame and refresh action panel."""
        self._interface._loading_frame_index = (self._interface._loading_frame_index + 1) % len(self._ICON_LOADING_FRAMES)

        # Re-render all incomplete action entries with the new animation frame
        action_log = self.query_one("#action-log", _ConversationLog)

        # Check if there are any incomplete entries to animate
        has_incomplete = any(
            not entry.is_completed
            for entry in self._interface._task_action_entries.values()
        )

        if has_incomplete:
            # Update all incomplete entries
            for entry_key, entry in self._interface._task_action_entries.items():
                if not entry.is_completed:
                    renderable = self._interface.format_action_entry(entry)
                    action_log.update_renderable(entry_key, renderable)

        # Update status bar if agent is working (to animate the loading icon)
        if self._interface._agent_state == "working":
            new_status = self._interface._generate_status_message()
            if new_status != self._status_message:
                self._status_message = new_status
                self._render_status()

        # Check if we need to reset task_completed state to idle
        if (self._interface._agent_state == "task_completed" and
            self._interface._task_completed_time is not None):
            elapsed = time.time() - self._interface._task_completed_time
            if elapsed >= self._interface._reset_to_idle_delay:
                self._interface._agent_state = "idle"
                self._interface._task_completed_time = None
                # Update status message
                new_status = self._interface._generate_status_message()
                if new_status != self._interface._status_message:
                    self._interface._status_message = new_status
                    self._interface.status_updates.put_nowait(new_status)

    def _render_status(self) -> None:
        status_bar = self.query_one("#status-bar", Static)
        width = status_bar.size.width or self.size.width or (
            len(self._STATUS_PREFIX) + len(self._status_message)
        )
        available = max(0, width - len(self._STATUS_PREFIX))
        visible = self._visible_status_content(available)
        full_text = f"{self._STATUS_PREFIX}{visible}"

        if full_text == self._last_rendered_status:
            return

        self.status_text = full_text
        status_bar.update(Text(full_text, no_wrap=True, overflow="crop"))
        self._last_rendered_status = full_text

    def _visible_status_content(self, available: int) -> str:
        if available <= 0:
            return ""
        message = self._status_message
        if len(message) <= available:
            return message

        scroll_span = len(message) + self._STATUS_GAP
        start = self._status_offset % scroll_span
        extended = message + " " * self._STATUS_GAP

        segment_chars = []
        for idx in range(available):
            segment_chars.append(extended[(start + idx) % scroll_span])
        return "".join(segment_chars)

    # ────────────────────────────── prompt-style prefix helpers ─────────────────────────────

    def _refresh_menu_prefixes(self) -> None:
        if not self.query("#menu-options"):
            return

        menu = self.query_one("#menu-options", ListView)
        if menu.index is None:
            menu.index = 0

        for idx, (item_id, text) in enumerate(self._MENU_ITEMS):
            item = self.query_one(f"#{item_id}", ListItem)
            label = item.query_one(Label)
            prefix = "> " if idx == menu.index else "  "
            label.update(f"{prefix}{text}")

    def _refresh_provider_prefixes(self) -> None:
        if not self.query("#provider-options"):
            return

        providers = self.query_one("#provider-options", ListView)
        items = list(providers.children)
        if not items:
            return

        if providers.index is None:
            providers.index = 0
        providers.index = max(0, min(providers.index, len(items) - 1))

        for idx, item in enumerate(items):
            label = item.query_one(Label) if item.query(Label) else None
            if label is None:
                continue
            text = (
                self._SETTINGS_PROVIDER_TEXTS[idx]
                if idx < len(self._SETTINGS_PROVIDER_TEXTS)
                else "provider"
            )
            prefix = "> " if idx == providers.index else "  "
            label.update(f"{prefix}{text}")

    def _refresh_settings_actions_prefixes(self) -> None:
        if not self.query("#settings-actions-list"):
            return

        actions = self.query_one("#settings-actions-list", ListView)
        items = list(actions.children)
        if not items:
            return

        if actions.index is None:
            actions.index = 0
        actions.index = max(0, min(actions.index, len(items) - 1))

        for idx, item in enumerate(items):
            label = item.query_one(Label) if item.query(Label) else None
            if label is None:
                continue
            text = self._SETTINGS_ACTION_TEXTS[idx] if idx < len(self._SETTINGS_ACTION_TEXTS) else "action"
            prefix = "> " if idx == actions.index else "  "
            label.update(f"{prefix}{text}")

    def _init_settings_provider_selection(self) -> None:
        if not self.query("#provider-options"):
            return

        providers = self.query_one("#provider-options", ListView)
        items = list(providers.children)
        if not items:
            return

        initial_index = 0
        for i, value in enumerate(self._SETTINGS_PROVIDER_VALUES):
            if value == self._provider:
                initial_index = i
                break

        initial_index = min(initial_index, len(items) - 1)
        providers.index = initial_index

        # Initialize action list selection
        if self.query("#settings-actions-list"):
            actions = self.query_one("#settings-actions-list", ListView)
            if actions.index is None:
                actions.index = 0

        # Apply prefixes after refresh
        self._refresh_provider_prefixes()
        self._refresh_settings_actions_prefixes()

        # Focus provider list by default
        providers.focus()

    # ────────────────────────────── list events ─────────────────────────────

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "menu-options":
            self._refresh_menu_prefixes()
        elif event.list_view.id == "provider-options":
            self._refresh_provider_prefixes()
            self._on_provider_selection_changed()
        elif event.list_view.id == "settings-actions-list":
            self._refresh_settings_actions_prefixes()

    def _on_provider_selection_changed(self) -> None:
        """Handle provider selection change in settings."""
        if not self.query("#provider-options"):
            return

        providers = self.query_one("#provider-options", ListView)
        idx = providers.index if providers.index is not None else 0
        if idx >= len(self._SETTINGS_PROVIDER_VALUES):
            return

        new_provider = self._SETTINGS_PROVIDER_VALUES[idx]
        if new_provider == self._settings_provider:
            return

        # Provider changed
        self._settings_provider = new_provider

        # Update API key label
        if self.query("#api-key-label"):
            provider_name = self._PROVIDER_API_KEY_NAMES.get(new_provider, new_provider)
            self.query_one("#api-key-label", Static).update(f"API Key for {provider_name}")

        # Update model display
        if self.query("#model-display"):
            model_name = self._get_model_for_provider(new_provider)
            self.query_one("#model-display", Static).update(f"Model: {model_name}")

        # Reset API key input if there's no saved key for this provider
        if self.query("#api-key-input"):
            api_key_input = self.query_one("#api-key-input", _PasteableInput)
            saved_key = self._saved_api_keys.get(new_provider, "")
            api_key_input.value = saved_key

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_id = event.list_view.id

        if list_id == "menu-options":
            item_id = event.item.id
            if item_id == "menu-start":
                self._start_chat()
            elif item_id == "menu-settings":
                self._open_settings()
            elif item_id == "menu-exit":
                self.exit()
            return

        if list_id == "settings-actions-list":
            # In settings, treat this list like buttons.
            # Index 0 = save, 1 = cancel
            actions = event.list_view
            idx = actions.index if actions.index is not None else 0
            if idx == 0:
                self._save_settings()
            else:
                self._close_settings()
            return


class TUIInterface:
    """Asynchronous Textual TUI driver that feeds user prompts to the agent."""

    _STYLE_COLORS = {
        "user": "bold #ffffff",
        "agent": "bold #ff4f18",
        "action": "bold #a0a0a0",
        "task": "bold #ff4f18",
        "error": "bold #ff4f18",
        "info": "bold #666666",
        "system": "bold #a0a0a0",
    }

    _CHAT_LABEL_WIDTH = 7
    _ACTION_LABEL_WIDTH = 5  # Adjusted for icon format [+] or [●]/[○]

    def __init__(
        self, agent: "AgentBase", *, default_provider: str, default_api_key: str
    ) -> None:
        self._agent = agent
        self._running: bool = False
        self._tracked_sessions: set[str] = set()
        self._seen_events: set[Tuple[str, str, str, str]] = set()
        self._status_message: str = "Agent is idle"
        self._app: _CraftApp | None = None
        self._event_task: asyncio.Task[None] | None = None

        self._command_handlers: dict[str, Callable[[], Awaitable[None]]] = {}

        self.chat_updates: Queue[TimelineEntry] = Queue()
        self.action_updates: Queue[_ActionUpdate] = Queue()
        self.status_updates: Queue[str] = Queue()

        # Track current task and action states
        self._current_task_name: Optional[str] = None
        self._task_action_entries: dict[str, _ActionEntry] = {}  # task/action name -> entry
        self._loading_frame_index: int = 0  # Current frame of loading animation

        # Agent state tracking
        self._agent_state: str = "idle"  # idle, working, waiting_for_user, task_completed
        self._task_completed_time: Optional[float] = None  # Track when task completed for auto-reset
        self._reset_to_idle_delay: float = 3.0  # Seconds to show "task completed" before resetting

        self._default_provider = default_provider
        self._default_api_key = default_api_key

        self._register_commands()

    def _register_commands(self) -> None:
        self._command_handlers = {
            "/exit": self._handle_exit_command,
            "/clear": self._handle_clear_command,
            "/reset": self._handle_reset_command,
            "/menu": self._handle_menu_command,
            "/help": self._handle_help_command,
        }

    async def _maybe_handle_command(self, message: str) -> bool:
        command = message.split()[0].lower()

        handler = self._command_handlers.get(command)
        if handler:
            await handler()
            return True

        agent_command = self._agent.get_commands().get(command)
        if agent_command:
            result = await agent_command.handler()
            await self.chat_updates.put(
                (
                    "System",
                    result or f"Command '{command}' executed.",
                    "system",
                )
            )
            return True

        return False

    async def start(self) -> None:
        """Start the Textual TUI session and background consumers."""
        if self._running:
            return

        self._running = True
        logger.debug("Starting Textual TUI interface. Press Ctrl+C to exit.")

        await self.chat_updates.put(
            (
                "System",
                "White Collar Agent TUI ready. Type /help for more info and /exit to quit.",
                "system",
            )
        )
        await self.status_updates.put(self._status_message)

        trigger_consumer = asyncio.create_task(self._consume_triggers())
        self._event_task = asyncio.create_task(self._watch_events())

        self._app = _CraftApp(self, self._default_provider, self._default_api_key)

        try:
            await self._app.run_async()
        finally:
            self._running = False
            self._agent.is_running = False

            trigger_consumer.cancel()
            try:
                await trigger_consumer
            except asyncio.CancelledError:  # pragma: no cover - event loop teardown
                pass

            if self._event_task:
                self._event_task.cancel()
                try:
                    await self._event_task
                except asyncio.CancelledError:  # pragma: no cover - event loop teardown
                    pass

    async def submit_user_message(self, message: str) -> None:
        """Handle chat input captured by the Textual app."""
        if not message:
            return

        if await self._maybe_handle_command(message):
            return

        await self.chat_updates.put(("You", message, "user"))

        # Set state to working when user submits a message
        self._agent_state = "working"
        status = self._generate_status_message()
        self._status_message = status
        await self.status_updates.put(status)

        payload = {
            "text": message,
            "sender": {"id": "cli_user", "type": "user"},
            "gui_mode": False,
        }
        await self._agent._handle_chat_message(payload)

    def configure_provider(self, provider: str, api_key: str) -> None:
        """Configure environment variables for the selected provider.

        Note: This only sets environment variables. To actually switch providers,
        call agent.reinitialize_llm() after this.
        """
        key_lookup = {
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "byteplus": "BYTEPLUS_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        key_name = key_lookup.get(provider)
        if key_name and api_key:
            os.environ[key_name] = api_key
        os.environ["LLM_PROVIDER"] = provider
        # Note: Don't set self._agent.llm.provider here as it creates inconsistent state.
        # The provider will be properly set when reinitialize_llm() is called.

    def notify_provider(self, provider: str) -> None:
        self.chat_updates.put_nowait(
            (
                "System",
                f"Launching agent with provider: {provider}",
                "system",
            )
        )

    async def request_shutdown(self) -> None:
        """Stop the interface and close the Textual application."""
        if not self._running:
            return

        self._running = False
        self._agent.is_running = False

        if self._app and self._app.is_running:
            self._app.exit()

    async def _handle_exit_command(self) -> None:
        await self.chat_updates.put(("System", "Session terminated by user.", "system"))
        self._agent_state = "idle"
        await self.status_updates.put("Agent is idle")
        await self.request_shutdown()

    async def _handle_menu_command(self) -> None:
        # Switch UI back to menu layer if the app is running
        if self._app:
            self._app.show_settings = False
            self._app.show_menu = True

        await self.chat_updates.put(("System", "Returned to menu.", "system"))
        self._agent_state = "idle"
        await self.status_updates.put("Agent is idle")
        
    async def _handle_help_command(self) -> None:
        help_text = self._build_help_text()
        await self.chat_updates.put(("System", help_text, "system"))

    def _build_help_text(self) -> str:
        intro = (
            "I am a computer-use AI agent., I can perform computer-based task autonomously "
            "for you with simple instruction."
        )

        builtin = {
            "/help": "Show this help message.",
            "/menu": "Return to the main menu.",
            "/clear": "Clear chat and action timelines from the display.",
            "/reset": "Reset the agent and clear interface state.",
            "/exit": "Exit the session.",
        }

        lines: list[str] = [intro, "", "Available commands:"]

        # Built-in commands first
        for cmd in sorted(builtin.keys()):
            lines.append(f"  {cmd}  - {builtin[cmd]}")

        # Agent-provided commands (if any)
        agent_cmds = self._agent.get_commands() if self._agent else {}
        extra = [c for c in agent_cmds.keys() if c not in builtin]

        if extra:
            lines.append("")
            lines.append("Agent commands:")
            for cmd in sorted(extra):
                obj = agent_cmds[cmd]
                desc = (
                    getattr(obj, "description", None)
                    or getattr(obj, "help", None)
                    or getattr(obj, "doc", None)
                )
                if not desc and getattr(obj, "handler", None):
                    desc = getattr(obj.handler, "__doc__", None)

                desc = (desc or "Agent command.").strip()
                lines.append(f"  {cmd}  - {desc}")

        return "\n".join(lines)

    def _clear_display_logs(self) -> None:
        if self._app:
            self._app.clear_logs()

    async def _handle_clear_command(self) -> None:
        self._clear_display_logs()
        self.chat_updates = Queue()
        self.action_updates = Queue()
        await self.chat_updates.put(("System", "Cleared chat and action timelines.", "system"))

    async def _handle_reset_command(self) -> None:
        response: str | None = None
        reset_command = self._agent.get_commands().get("/reset")
        if reset_command:
            response = await reset_command.handler()

        await self._reset_interface_state()
        await self.chat_updates.put(("System", response or "Agent reset. Starting fresh.", "system"))

    async def _reset_interface_state(self) -> None:
        self._tracked_sessions.clear()
        self._seen_events.clear()
        self.chat_updates = Queue()
        self.action_updates = Queue()
        self.status_updates = Queue()
        self._agent_state = "idle"
        self._status_message = "Agent is idle"
        self._task_completed_time = None
        self._clear_display_logs()
        await self.status_updates.put(self._status_message)

    async def _consume_triggers(self) -> None:
        """Continuously consume triggers and hand them to the agent."""
        try:
            while self._agent.is_running:
                trigger = await self._agent.triggers.get()
                if trigger.session_id:
                    self._tracked_sessions.add(trigger.session_id)
                await self._agent.react(trigger)
        except asyncio.CancelledError:  # pragma: no cover
            raise

    async def _watch_events(self) -> None:
        """Refresh the conversation timeline with agent actions."""
        try:
            while self._running and self._agent.is_running:
                stream = self._agent.event_stream_manager.get_stream()
                if not stream:
                    await asyncio.sleep(0.05)
                    continue

                for event in stream.as_list():
                    key = (event.iso_ts, event.kind, event.message)
                    if key in self._seen_events:
                        continue
                    self._seen_events.add(key)

                    if event.kind == "screen":
                        continue

                    style = self._style_for_event(event.kind, event.severity)
                    label = self._label_for_style(style, event.kind)
                    display_text = event.display_text()

                    if style in {"action", "task"}:
                        await self._handle_action_event(
                            event.kind,
                            display_text,
                            style=style,
                        )
                        continue

                    if style not in {"agent", "system", "user", "error", "info"}:
                        continue

                    if display_text is not None:
                        await self.chat_updates.put((label, display_text, style))

                    # Set agent state to waiting_for_user when agent sends a response
                    if style == "agent" and display_text:
                        # Check if this is the final agent response (not during a task)
                        if not self._current_task_name and self._agent_state == "working":
                            self._agent_state = "waiting_for_user"
                            status = self._generate_status_message()
                            if status != self._status_message:
                                self._status_message = status
                                await self.status_updates.put(status)

                await asyncio.sleep(0.05)

        except asyncio.CancelledError:  # pragma: no cover
            raise

    async def _handle_action_event(self, kind: str, message: str, *, style: str = "action") -> None:
        """Record an action update and refresh the status bar."""
        # Extract action name from display message formats:
        # action_start: "Running {action_name}" -> extract action_name
        # action_end: "{action_name} → completed/failed" -> extract action_name
        if kind == "action_start" and message.startswith("Running "):
            action_name = message[8:]  # Remove "Running " prefix
        elif kind == "action_end" and " → " in message:
            action_name = message.split(" → ")[0]
        else:
            action_name = message

        # Use action name as the consistent key
        entry_key = f"{style}:{action_name}"

        # Handle task start
        if kind == "task_start":
            self._current_task_name = message
            self._agent_state = "working"
            entry = _ActionEntry(
                kind=kind,
                message=message,
                style=style,
                is_completed=False,
                parent_task=None
            )
            self._task_action_entries[entry_key] = entry
            await self.action_updates.put(_ActionUpdate(operation="add", entry=entry, entry_key=entry_key))

        # Handle task end - update existing entry
        elif kind == "task_end":
            if entry_key in self._task_action_entries:
                self._task_action_entries[entry_key].is_completed = True
                await self.action_updates.put(_ActionUpdate(operation="update", entry_key=entry_key))
            self._current_task_name = None
            self._agent_state = "task_completed"
            self._task_completed_time = time.time()

        # Handle action start
        elif kind == "action_start":
            self._agent_state = "working"
            entry = _ActionEntry(
                kind=kind,
                message=action_name,  # Use just the action name
                style=style,
                is_completed=False,
                parent_task=self._current_task_name
            )
            self._task_action_entries[entry_key] = entry
            await self.action_updates.put(_ActionUpdate(operation="add", entry=entry, entry_key=entry_key))

        # Handle action end - update existing entry
        elif kind == "action_end":
            if entry_key in self._task_action_entries:
                self._task_action_entries[entry_key].is_completed = True
                await self.action_updates.put(_ActionUpdate(operation="update", entry_key=entry_key))

        # Update status based on current agent state
        status = self._generate_status_message()
        if status != self._status_message:
            self._status_message = status
            await self.status_updates.put(status)

    def _generate_status_message(self) -> str:
        """Generate personalized status message based on agent state."""
        loading_icon = _CraftApp._ICON_LOADING_FRAMES[self._loading_frame_index % len(_CraftApp._ICON_LOADING_FRAMES)]

        if self._agent_state == "idle":
            return "Agent is idle"
        elif self._agent_state == "working":
            if self._current_task_name:
                return f"{loading_icon} Working on: {self._current_task_name}"
            else:
                return f"{loading_icon} Agent is working..."
        elif self._agent_state == "waiting_for_user":
            return "⏸ Waiting for your response"
        elif self._agent_state == "task_completed":
            if self._current_task_name:
                return f"✓ Task completed!"
            else:
                return "✓ Task completed!"
        else:
            return "Agent is idle"

    def _format_labelled_entry(
        self,
        label_text: str,
        message: Text | str,
        *,
        colour: str,
        label_width: int,
    ) -> Table:
        table = Table.grid(padding=(0, 1))
        table.expand = True
        table.add_column(
            "label",
            width=label_width,
            min_width=label_width,
            max_width=label_width,
            style=colour,
            no_wrap=True,
            justify="left",
        )
        table.add_column("message", ratio=1)

        label_cell = Text(label_text, style=colour, no_wrap=True)
        message_text = message if isinstance(message, Text) else Text(str(message))
        message_text.no_wrap = False
        message_text.overflow = "fold"

        table.add_row(label_cell, message_text)
        return table

    def format_chat_entry(self, label: str, message: str, style: str) -> RenderableType:
        colour = self._STYLE_COLORS.get(style, self._STYLE_COLORS["info"])
        label_text = f"{label}:"
        return self._format_labelled_entry(
            label_text,
            message,
            colour=colour,
            label_width=self._CHAT_LABEL_WIDTH,
        )

    def format_action_entry(self, entry: _ActionEntry) -> RenderableType:
        # Choose icon based on completion status
        if entry.is_completed:
            icon = _CraftApp._ICON_COMPLETED
        else:
            # Use current frame of loading animation
            icon = _CraftApp._ICON_LOADING_FRAMES[self._loading_frame_index % len(_CraftApp._ICON_LOADING_FRAMES)]

        # Determine color based on style and completion
        if entry.style == "task":
            colour = "bold #ff4f18"
        else:  # action
            colour = "bold #a0a0a0"

        # Format: [icon]
        label_text = f"[{icon}]"

        # Add indentation to message for actions that belong to a task
        if entry.parent_task and entry.style == "action":
            message = f"    {entry.message}"
        else:
            message = entry.message

        return self._format_labelled_entry(
            label_text,
            message,
            colour=colour,
            label_width=self._ACTION_LABEL_WIDTH,
        )

    def _style_for_event(self, kind: str, severity: str) -> str:
        if severity.upper() == "ERROR":
            return "error"
        if kind == "system":
            return "system"
        if kind.startswith("task"):
            return "task"
        if kind in {"action", "action_start", "action_end"}:
            return "action"
        if kind in {"screen", "info", "note"}:
            return "info"
        if kind == "user":
            return "user"
        return "agent"

    @staticmethod
    def _label_for_style(style: str, kind: str) -> str:
        if style == "agent":
            return "Agent"
        if style == "system":
            return "System"
        if style == "user":
            return "You"
        if style == "error":
            return "Error"
        if style == "task":
            return kind.replace("_", " ").title()
        if style == "info":
            return kind.replace("_", " ").title()
        return kind.title()
