"""Textual-based terminal user interface for interacting with the agent."""
from __future__ import annotations

import asyncio
import os
from asyncio import Queue, QueueEmpty
from dataclasses import dataclass
from typing import Awaitable, Callable, Tuple

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import var

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.widgets import Input, Static
from textual.widgets import RichLog as _BaseLog
from textual.widgets import ListView, ListItem, Label

from core.logger import logger

if False:  # pragma: no cover
    from core.agent_base import AgentBase  # type: ignore


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

    def append_text(self, content) -> None:
        # Normalize to Rich Text, enable folding of long tokens
        text: Text = content if isinstance(content, Text) else Text(str(content))
        text.no_wrap = False
        text.overflow = "fold"  # split unbreakable runs (URLs / IDs)
        self.append_renderable(text)

    def append_markup(self, markup: str) -> None:
        self.append_text(Text.from_markup(markup))

    def append_renderable(self, renderable: RenderableType) -> None:
        # Write using expand/shrink so width follows the widget on resize
        self._history.append(renderable)
        self.write(renderable, expand=True, shrink=True)

    def clear(self) -> None:
        """Clear the log and the preserved history."""

        self._history.clear()
        super().clear()

    def _reflow_history(self) -> None:
        """Re-render stored entries so Rich recalculates wrapping."""

        if not self._history:
            return

        history = list(self._history)
        super().clear()
        for renderable in history:
            self.write(renderable, expand=True, shrink=True)

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


class _CraftApp(App):
    """Textual application rendering the Craft Agent TUI."""

    CSS = """
    Screen {
        layout: vertical;
        background: #111111;
        color: #f5f5f5;
    }

    /* Shared chrome */
    #top-region {
        height: 1fr;
        min-width: 0;
    }

    #chat-panel, #action-panel {
        height: 100%;
        border: solid #444444;
        border-title-align: left;
        margin: 0 1;
        min-width: 0;  /* allow panels to shrink with the terminal */
    }

    #chat-log, #action-log {
        text-wrap: wrap;
        text-overflow: fold;
        overflow-x: hidden;
        min-width: 0;  /* enable reflow instead of clamped min-content width */
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
    }

    #bottom-region {
        height: auto;
        border-top: solid #333333;
        padding: 1;
    }

    #status-bar {
        height: 1;
        min-height: 1;
        text-wrap: nowrap;
        overflow: hidden;
        text-style: bold;
        color: #dddddd;
    }

    #chat-input {
        border: solid #444444;
        background: #1a1a1a;
    }

    /* Menu layer */
    #menu-layer {
        align: center middle;
        content-align: center middle;
    }

    #menu-panel {
        width: 90;
        max-width: 100%;
        max-height: 95%;
        border: solid #444444;
        background: #0f0f0f;
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
        color: #cfcfcf;
    }

    /* Highlight for list selections */
    #menu-options > ListItem.--highlight .menu-item,
    #provider-options > ListItem.--highlight .menu-item,
    #settings-actions-list > ListItem.--highlight .menu-item {
        background: #222222;
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
        border: solid #444444;
        background: #101010;
        padding: 2 3 3 3;
        content-align: center top;
        overflow: auto;
    }

    #settings-card Input {
        width: 100%;
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

    _STATUS_PREFIX = "Status: "
    _STATUS_GAP = 4
    _STATUS_INITIAL_PAUSE = 6

    _MENU_ITEMS = [
        ("menu-start", "start"),
        ("menu-settings", "setting"),
        ("menu-exit", "exit"),
    ]

    _SETTINGS_PROVIDER_TEXTS = [
        "OpenAI",
        "Google Gemini",
        "BytePlus",
        "Ollama (remote)",
    ]

    _SETTINGS_PROVIDER_VALUES = [
        "openai",
        "gemini",
        "byteplus",
        "remote",
    ]

    _SETTINGS_ACTION_TEXTS = [
        "save",
        "cancel",
    ]

    def __init__(self, interface: "TUIInterface", provider: str, api_key: str) -> None:
        super().__init__()
        self._interface = interface
        self._status_message: str = "Idle"
        self._status_offset: int = 0
        self._status_pause: int = self._STATUS_INITIAL_PAUSE
        self._last_rendered_status: str = ""
        self._provider = provider
        self._api_key = api_key

    def compose(self) -> ComposeResult:  # pragma: no cover - declarative layout
        yield Container(
            Container(
                Static(self._logo_text(), id="menu-logo"),
                Vertical(
                    Static(f"Model Provider: {self._provider}", id="provider-hint"),
                    Static(
                        "Configure provider & key under Settings before starting.",
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
        return Text(
            """
░█░█░█░█░▀█▀░▀█▀░█▀▀░░░█▀▀░█▀█░█░░░█░░░█▀█░█▀▄░░░█▀█░█▀▀░█▀▀░█▀█░▀█▀
░█▄█░█▀█░░█░░░█░░█▀▀░░░█░░░█░█░█░░░█░░░█▀█░█▀▄░░░█▀█░█░█░█▀▀░█░█░░█░
░▀░▀░▀░▀░▀▀▀░░▀░░▀▀▀░░░▀▀▀░▀▀▀░▀▀▀░▀▀▀░▀░▀░▀░▀░░░▀░▀░▀▀▀░▀▀▀░▀░▀░░▀░
            """.rstrip("\n"),
            justify="center",
        )

    def _open_settings(self) -> None:
        if self.query("#settings-card"):
            return

        # Hide the main menu panel while settings are open
        self.show_settings = True

        settings = Container(
            Static("Settings", id="settings-title"),
            Static("LLM Provider"),
            ListView(
                ListItem(Label("OpenAI", classes="menu-item")),
                ListItem(Label("Google Gemini", classes="menu-item")),
                ListItem(Label("BytePlus", classes="menu-item")),
                ListItem(Label("Ollama (remote)", classes="menu-item")),
                id="provider-options",
            ),
            Static("API Key"),
            Input(
                placeholder="Enter API key",
                password=True,
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

        # Return focus to the main menu list
        if self.show_menu and self.query("#menu-options"):
            menu = self.query_one("#menu-options", ListView)
            if menu.index is None:
                menu.index = 0
            menu.focus()
            self._refresh_menu_prefixes()

    def _save_settings(self) -> None:
        api_key_input = self.query_one("#api-key-input", Input)

        provider_value = self._provider
        if self.query("#provider-options"):
            providers = self.query_one("#provider-options", ListView)
            idx = providers.index if providers.index is not None else 0
            if 0 <= idx < len(self._SETTINGS_PROVIDER_VALUES):
                provider_value = self._SETTINGS_PROVIDER_VALUES[idx]

        self._provider = provider_value
        self._api_key = api_key_input.value

        self.query_one("#provider-hint", Static).update(
            f"Model Provider: {self._provider}"
        )
        self._close_settings()

    def _start_chat(self) -> None:
        self._interface.configure_provider(self._provider, self._api_key)
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
        self._sync_layers()

        # Initialize menu selection visuals
        if self.show_menu:
            menu = self.query_one("#menu-options", ListView)
            menu.index = 0
            menu.focus()
            self._refresh_menu_prefixes()

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
                action = self._interface.action_updates.get_nowait()
            except QueueEmpty:
                break
            entry = self._interface.format_action_entry(action)
            action_log.append_renderable(entry)

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
        elif event.list_view.id == "settings-actions-list":
            self._refresh_settings_actions_prefixes()

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
        "user": "bold plum1",
        "agent": "bold gold1",
        "action": "bold deep_sky_blue1",
        "task": "bold dark_orange",
        "error": "bold red",
        "info": "bold grey70",
        "system": "bold medium_orchid",
    }

    _CHAT_LABEL_WIDTH = 7
    _ACTION_LABEL_WIDTH = 7

    def __init__(
        self, agent: "AgentBase", *, default_provider: str, default_api_key: str
    ) -> None:
        self._agent = agent
        self._running: bool = False
        self._tracked_sessions: set[str] = set()
        self._seen_events: set[Tuple[str, str, str, str]] = set()
        self._status_message: str = "Idle"
        self._app: _CraftApp | None = None
        self._event_task: asyncio.Task[None] | None = None

        self._command_handlers: dict[str, Callable[[], Awaitable[None]]] = {}

        self.chat_updates: Queue[TimelineEntry] = Queue()
        self.action_updates: Queue[_ActionEntry] = Queue()
        self.status_updates: Queue[str] = Queue()

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
        await self.status_updates.put("Awaiting agent response…")

        payload = {
            "text": message,
            "sender": {"id": "cli_user", "type": "user"},
            "gui_mode": False,
        }
        await self._agent._handle_chat_message(payload)

    def configure_provider(self, provider: str, api_key: str) -> None:
        key_lookup = {
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "byteplus": "BYTEPLUS_API_KEY",
        }
        key_name = key_lookup.get(provider)
        if key_name and api_key:
            os.environ[key_name] = api_key
        os.environ["LLM_PROVIDER"] = provider
        self._agent.llm.provider = provider

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
        await self.status_updates.put("Idle")
        await self.request_shutdown()
        
    async def _handle_menu_command(self) -> None:
        # Switch UI back to menu layer if the app is running
        if self._app:
            self._app.show_settings = False
            self._app.show_menu = True

        await self.chat_updates.put(("System", "Returned to menu.", "system"))
        await self.status_updates.put("Idle")
        
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
        self._status_message = "Idle"
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
                for session_id in list(self._tracked_sessions):
                    stream = self._agent.event_stream_manager.get_stream(session_id)
                    if not stream:
                        continue
                    for event in stream.as_list():
                        key = (session_id, event.iso_ts, event.kind, event.message)
                        if key in self._seen_events:
                            continue
                        self._seen_events.add(key)

                        if event.kind == "screen":
                            continue

                        style = self._style_for_event(event.kind, event.severity)
                        label = self._label_for_style(style, event.kind)
                        display_text = event.display_text()

                        if style in {"action", "task"}:
                            await self._handle_action_event(event.kind, display_text, style=style)
                            continue

                        if style not in {"agent", "system", "user", "error", "info"}:
                            continue

                        if display_text is not None:
                            await self.chat_updates.put((label, display_text, style))

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:  # pragma: no cover
            raise

    async def _handle_action_event(self, kind: str, message: str, *, style: str = "action") -> None:
        """Record an action update and refresh the status bar."""
        await self.action_updates.put(_ActionEntry(kind=kind, message=message, style=style))
        if style == "action":
            status = self._derive_status(kind, message)
            if status != self._status_message:
                self._status_message = status
                await self.status_updates.put(status)

    def _derive_status(self, kind: str, message: str) -> str:
        normalized = message.strip() or ""
        if kind == "action_start":
            return f"Running: {normalized or 'action in progress'}"
        if kind == "action_end":
            return f"Completed: {normalized or 'last action'}"
        if kind == "action":
            return normalized or "Action in progress"
        return normalized or self._status_message or "Idle"

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
        kind = entry.kind.replace("_", " ").title()
        colour = "bold deep_sky_blue1" if entry.style == "action" else "bold dark_orange"
        label_text = f"{kind}:"
        return self._format_labelled_entry(
            label_text,
            entry.message,
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
