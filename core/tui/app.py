"""Main Textual application for the TUI interface."""
from __future__ import annotations

import os
import time
from asyncio import QueueEmpty
from typing import TYPE_CHECKING

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import var
from textual.widgets import Input, Static, ListView, ListItem, Label

from rich.text import Text

from core.models.model_registry import MODEL_REGISTRY
from core.models.types import InterfaceType

from core.tui.styles import TUI_CSS
from core.tui.settings import save_settings_to_env, get_api_key_env_name
from core.tui.widgets import ConversationLog, PasteableInput

if TYPE_CHECKING:
    from core.tui.interface import TUIInterface


class CraftApp(App):
    """Textual application rendering the Craft Agent TUI."""

    CSS = TUI_CSS

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
    ICON_COMPLETED = "+"
    ICON_LOADING_FRAMES = ["●", "○"]  # Animated loading icons

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
        api_key_env = get_api_key_env_name(self._provider)
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
                    ConversationLog(id="chat-log"),
                    id="chat-panel",
                ),
                Container(
                    ConversationLog(id="action-log"),
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
            PasteableInput(
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
        api_key_input = self.query_one("#api-key-input", PasteableInput)

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
            save_settings_to_env(self._provider, self._api_key)

            # Also update current process environment variables
            api_key_env = get_api_key_env_name(self._provider)
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
            api_key_env = get_api_key_env_name(self._provider)
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
        chat_log = self.query_one("#chat-log", ConversationLog)
        action_log = self.query_one("#action-log", ConversationLog)

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

        chat_log = self.query_one("#chat-log", ConversationLog)
        action_log = self.query_one("#action-log", ConversationLog)
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
        chat_log = self.query_one("#chat-log", ConversationLog)
        action_log = self.query_one("#action-log", ConversationLog)
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
        self._interface._loading_frame_index = (self._interface._loading_frame_index + 1) % len(self.ICON_LOADING_FRAMES)

        # Re-render all incomplete action entries with the new animation frame
        action_log = self.query_one("#action-log", ConversationLog)

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
            api_key_input = self.query_one("#api-key-input", PasteableInput)
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
