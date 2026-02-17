"""Main Textual application for the TUI interface."""
from __future__ import annotations

import os
import time
from asyncio import QueueEmpty
from typing import TYPE_CHECKING

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import var
from textual.widgets import Input, Static, ListView, ListItem, Label, Button

from rich.text import Text

from core.models.model_registry import MODEL_REGISTRY
from core.models.types import InterfaceType

from core.tui.styles import TUI_CSS
from core.tui.settings import save_settings_to_env, get_api_key_env_name
from core.tui.widgets import ConversationLog, PasteableInput, VMFootageWidget
from core.tui.mcp_settings import (
    list_mcp_servers,
    add_mcp_server_from_template,
    remove_mcp_server,
    enable_mcp_server,
    disable_mcp_server,
    get_available_templates,
    update_mcp_server_env,
    get_server_env_vars,
    MCP_SERVER_TEMPLATES,
)
from core.tui.skill_settings import (
    list_skills,
    get_skill_info,
    toggle_skill,
    get_skill_raw_content,
)
from core.onboarding.manager import onboarding_manager
from core.logger import logger

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
    gui_mode_active = var(False)

    _STATUS_PREFIX = " "
    _STATUS_GAP = 4
    _STATUS_INITIAL_PAUSE = 6

    # Icons for task/action status
    ICON_COMPLETED = "+"
    ICON_ERROR = "x"
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
        # Track if soft onboarding has been triggered this session
        self._soft_onboarding_triggered: bool = False
        # Flag to block provider change events during settings initialization
        self._settings_init_complete: bool = True

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
                Static(self._header_text(), id="menu-header"),
                Vertical(
                    Static("CraftBot V1.2.0. Your Personal AI Assistant that works 24/7 in your machine.", id="provider-hint"),
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
                Vertical(
                    Container(
                        VMFootageWidget(id="vm-footage"),
                        id="vm-footage-panel",
                        classes="-hidden",
                    ),
                    Container(
                        ConversationLog(id="action-log"),
                        id="action-panel",
                    ),
                    id="right-panel",
                ),
                id="top-region",
            ),
            Vertical(
                Static(
                    Text(self.status_text, no_wrap=True, overflow="crop"),
                    id="status-bar",
                ),
                PasteableInput(placeholder="Type a message and press Enter…", id="chat-input"),
                id="bottom-region",
            ),
            id="chat-layer",
        )

    # ────────────────────────────── menu helpers ─────────────────────────────

    def _header_text(self) -> Text:
        """Generate combined icon and logo as a single Text object for proper centering."""
        orange = "#ff4f18"
        white = "#ffffff"

        b = "█"  # block character
        s = " "  # space

        # Icon: 9 chars wide, 6 rows
        icon_w = 9
        icon_lines = [
            (s * 2 + b * 2 + s * 5, [(2, 4, orange)]),  # Antenna
            (s * 2 + b * 2 + s * 5, [(2, 4, orange)]),  # Antenna
            (b * icon_w, [(0, icon_w, white)]),  # Face top
            (b * icon_w, [(0, 3, white), (3, 5, orange), (5, 6, white), (6, 8, orange), (8, icon_w, white)]),  # Eyes
            (b * icon_w, [(0, 3, white), (3, 5, orange), (5, 6, white), (6, 8, orange), (8, icon_w, white)]),  # Eyes
            (b * icon_w, [(0, icon_w, white)]),  # Face bottom
        ]

        # Logo: 67 chars wide, 6 rows
        logo_lines = [
            " ██████╗██████╗  █████╗ ███████╗████████╗██████╗  ██████╗ ████████╗",
            "██╔════╝██╔══██╗██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔═══██╗╚══██╔══╝",
            "██║     ██████╔╝███████║█████╗     ██║   ██████╔╝██║   ██║   ██║   ",
            "██║     ██╔══██╗██╔══██║██╔══╝     ██║   ██╔══██╗██║   ██║   ██║   ",
            "╚██████╗██║  ██║██║  ██║██║        ██║   ██████╔╝╚██████╔╝   ██║   ",
            " ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝        ╚═╝   ╚═════╝  ╚═════╝    ╚═╝   ",
        ]

        # Combine icon and logo side by side with 3 space gap
        gap = "   "
        combined_lines = []
        craft_len = 41  # CRAFT portion length in logo

        for i in range(6):
            icon_str = icon_lines[i][0]
            logo_str = logo_lines[i]
            combined_lines.append(icon_str + gap + logo_str)

        full_text = "\n".join(combined_lines)
        text = Text(full_text, justify="center")

        # Apply styles
        offset = 0
        for i in range(6):
            icon_str, icon_spans = icon_lines[i]
            logo_str = logo_lines[i]
            line_len = len(icon_str) + len(gap) + len(logo_str)

            # Style icon parts
            for start, end, color in icon_spans:
                text.stylize(color, offset + start, offset + end)

            # Style logo parts (offset by icon width + gap)
            logo_offset = len(icon_str) + len(gap)
            text.stylize(white, offset + logo_offset, offset + logo_offset + craft_len)
            text.stylize(orange, offset + logo_offset + craft_len, offset + logo_offset + len(logo_str))

            offset += line_len + 1  # +1 for newline

        return text

    def _open_settings(self) -> None:
        if self.query("#settings-card"):
            return

        # Hide the main menu panel while settings are open
        self.show_settings = True

        # Block provider change events during initialization
        self._settings_init_complete = False

        # Reset settings provider tracking to current provider
        self._settings_provider = self._provider

        # Get model name for current provider
        model_name = self._get_model_for_provider(self._provider)

        # Build MCP server list items
        mcp_server_items = self._build_mcp_server_list_items()

        # Build Skills list items
        skill_items = self._build_skill_list_items()

        # Build tab buttons
        tab_buttons = Horizontal(
            Button("Models", id="tab-btn-models", classes="settings-tab -active"),
            Button("MCP Servers", id="tab-btn-mcp", classes="settings-tab"),
            Button("Skills", id="tab-btn-skills", classes="settings-tab"),
            id="settings-tab-bar",
        )

        # Build Models section content
        models_section = Container(
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
            id="section-models",
        )

        # Build MCP section content
        mcp_section = Container(
            Static("Configured MCP Servers", id="mcp-servers-title"),
            VerticalScroll(
                *mcp_server_items,
                id="mcp-server-list",
            ),
            Static("Add MCP Server", id="mcp-add-title"),
            ListView(
                *[ListItem(Label(f"  {name}", classes="menu-item"), id=f"mcp-add-{name}")
                  for name in list(MCP_SERVER_TEMPLATES.keys())[:6]],  # Show first 6 templates
                id="mcp-template-list",
            ),
            Static("Use /mcp command for more options", id="mcp-hint"),
            id="section-mcp",
            classes="-hidden",  # Hidden by default
        )

        # Build Skills section content
        skills_section = Container(
            Static("Discovered Skills", id="skills-title"),
            VerticalScroll(
                *skill_items,
                id="skills-list",
            ),
            Static("Click skill name to view details, toggle to enable/disable", id="skills-hint"),
            id="section-skills",
            classes="-hidden",  # Hidden by default
        )

        settings = Container(
            Static("Settings", id="settings-title"),
            tab_buttons,
            models_section,
            mcp_section,
            skills_section,
            ListView(
                ListItem(Label("save", classes="menu-item"), id="settings-save"),
                ListItem(Label("cancel", classes="menu-item"), id="settings-cancel"),
                id="settings-actions-list",
            ),
            id="settings-card",
        )

        self.query_one("#menu-layer").mount(settings)
        self.call_after_refresh(self._init_settings_provider_selection)

    def _build_mcp_server_list_items(self) -> list:
        """Build list items for MCP servers."""
        servers = list_mcp_servers()
        items = []

        if not servers:
            items.append(Static("No MCP servers configured", classes="mcp-empty"))
        else:
            for server in servers:
                status = "[+]" if server["enabled"] else "[-]"
                name = server["name"]

                # Check for unconfigured env vars
                env_vars = server.get("env", {})
                empty_vars = [k for k, v in env_vars.items() if not v]

                # Build display name with warning if needed
                if empty_vars:
                    display_name = f"{status} {name} (!)"
                else:
                    display_name = f"{status} {name}"

                desc = server["description"][:25] + "..." if len(server["description"]) > 25 else server["description"]

                # Only show config button if server has env vars
                if env_vars:
                    items.append(
                        Horizontal(
                            Static(display_name, classes="mcp-server-name"),
                            Static(desc, classes="mcp-server-desc"),
                            Button("*", id=f"mcp-config-{name}", classes="mcp-config-btn"),
                            Button("x", id=f"mcp-remove-{name}", classes="mcp-remove-btn"),
                            classes="mcp-server-row",
                        )
                    )
                else:
                    items.append(
                        Horizontal(
                            Static(display_name, classes="mcp-server-name"),
                            Static(desc, classes="mcp-server-desc"),
                            Button("x", id=f"mcp-remove-{name}", classes="mcp-remove-btn"),
                            classes="mcp-server-row",
                        )
                    )

        return items

    def _refresh_mcp_server_list(self) -> None:
        """Refresh the MCP server list in settings."""
        if not self.query("#mcp-server-list"):
            return

        server_list = self.query_one("#mcp-server-list", VerticalScroll)
        server_list.remove_children()

        items = self._build_mcp_server_list_items()
        for item in items:
            server_list.mount(item)

    def _build_skill_list_items(self) -> list:
        """Build list items for discovered skills."""
        skills = list_skills()
        items = []

        if not skills:
            items.append(Static("No skills discovered", classes="skill-empty"))
        else:
            for skill in skills:
                status = "[+]" if skill["enabled"] else "[-]"
                name = skill["name"]

                # Truncate description if too long
                desc = skill["description"][:30] + "..." if len(skill["description"]) > 30 else skill["description"]

                # Build toggle button class based on status
                toggle_class = "skill-toggle-btn" if skill["enabled"] else "skill-toggle-btn -disabled"

                items.append(
                    Horizontal(
                        Button(name, id=f"skill-view-{name}", classes="skill-view-btn"),
                        Static(desc, classes="skill-desc"),
                        Button("o" if skill["enabled"] else "x", id=f"skill-toggle-{name}", classes=toggle_class),
                        classes="skill-row",
                    )
                )

        return items

    def _refresh_skill_list(self) -> None:
        """Refresh the skill list in settings."""
        if not self.query("#skills-list"):
            return

        skill_list = self.query_one("#skills-list", VerticalScroll)
        skill_list.remove_children()

        items = self._build_skill_list_items()
        for item in items:
            skill_list.mount(item)

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

        new_api_key = api_key_input.value

        # Check if API key is required for the selected provider
        api_key_required = provider_value not in ("remote",)  # Ollama doesn't need API key

        if api_key_required and not new_api_key:
            # Require API key input - don't fall back to env vars
            provider_name = self._PROVIDER_API_KEY_NAMES.get(provider_value, provider_value)
            self.notify(
                f"API key required for {provider_name}. Please enter an API key or press Cancel.",
                severity="error",
                timeout=4,
            )
            return

        self._provider = provider_value
        self._api_key = new_api_key

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
            self.notify("Settings saved (using existing API key)", severity="information", timeout=2)

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

        # Check if soft onboarding is needed (first time entering chat after hard onboarding)
        if onboarding_manager.needs_soft_onboarding and not self._soft_onboarding_triggered:
            self._soft_onboarding_triggered = True
            logger.info("[ONBOARDING] Soft onboarding needed, scheduling interview task")
            self.call_after_refresh(self._trigger_soft_onboarding)

    async def _launch_hard_onboarding(self) -> None:
        """Launch the hard onboarding wizard screen."""
        from core.tui.onboarding.hard_onboarding import TUIHardOnboarding
        from core.tui.onboarding.widgets import OnboardingWizardScreen

        handler = TUIHardOnboarding(self)
        screen = OnboardingWizardScreen(handler)
        await self.push_screen(screen)

    async def _trigger_soft_onboarding(self) -> None:
        """Trigger the soft onboarding conversational interview."""
        from core.onboarding.soft.task_creator import create_soft_onboarding_task
        from core.trigger import Trigger

        if not self._interface or not self._interface._agent:
            logger.warning("[ONBOARDING] Cannot trigger soft onboarding: no agent reference")
            return

        # Create the interview task
        task_id = create_soft_onboarding_task(self._interface._agent.task_manager)

        # Fire a trigger to start the task
        trigger = Trigger(
            fire_at=time.time(),
            priority=1,
            next_action_description="Begin user profile interview",
            session_id=task_id,
            payload={"onboarding": True},
        )
        await self._interface._agent.triggers.put(trigger)
        logger.info(f"[ONBOARDING] Triggered soft onboarding task: {task_id}")

    async def on_mount(self) -> None:  # pragma: no cover - UI lifecycle
        self.query_one("#chat-panel").border_title = "Chat"
        self.query_one("#action-panel").border_title = "Action"
        self.query_one("#vm-footage-panel").border_title = "VM Footage"

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

        # Check if hard onboarding is needed
        if onboarding_manager.needs_hard_onboarding:
            logger.info("[ONBOARDING] Hard onboarding needed, launching wizard")
            self.call_after_refresh(self._launch_hard_onboarding)

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

    def watch_gui_mode_active(self, active: bool) -> None:
        """Handle GUI mode layout changes."""
        self._toggle_vm_footage_panel(active)

    def _toggle_vm_footage_panel(self, show: bool) -> None:
        """Show/hide the VM footage panel based on GUI mode."""
        footage_panel = self.query("#vm-footage-panel")
        if footage_panel:
            footage_panel.first().set_class(not show, "-hidden")
            if show:
                footage_panel.first().border_title = "VM Footage"

    def _sync_layers(self) -> None:
        menu_layer = self.query_one("#menu-layer")
        chat_layer = self.query_one("#chat-layer")
        menu_layer.set_class(self.show_menu is False, "-hidden")
        chat_layer.set_class(self.show_menu is True, "-hidden")

        if not self.show_menu:
            chat_input = self.query_one("#chat-input", PasteableInput)
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

        # Process footage updates
        while True:
            try:
                footage_update = self._interface.footage_updates.get_nowait()
            except QueueEmpty:
                break

            # Activate GUI mode if not already active
            if not self.gui_mode_active:
                self.gui_mode_active = True

            # Update footage widget
            footage_widget = self.query_one("#vm-footage", VMFootageWidget)
            footage_widget.update_footage(footage_update.image_bytes)

        # Check if GUI mode ended
        if self._interface.gui_mode_ended():
            self.gui_mode_active = False
            footage_widget = self.query_one("#vm-footage", VMFootageWidget)
            footage_widget.clear_footage()

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
        try:
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
        finally:
            # Always enable provider change events after initialization
            self._settings_init_complete = True

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
        # Skip during initialization to prevent auto-highlight from changing state
        if not self._settings_init_complete:
            return

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

        if list_id == "mcp-template-list":
            # Handle MCP template selection
            item_id = event.item.id
            if item_id and item_id.startswith("mcp-add-"):
                template_name = item_id[8:]  # Remove "mcp-add-" prefix
                success, message = add_mcp_server_from_template(template_name)
                if success:
                    self.notify(message, severity="information", timeout=3)
                    self._refresh_mcp_server_list()
                else:
                    self.notify(message, severity="error", timeout=3)
            return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id

        # Handle settings tab switching
        if button_id == "tab-btn-models":
            self._switch_settings_section("models")
            return
        elif button_id == "tab-btn-mcp":
            self._switch_settings_section("mcp")
            return
        elif button_id == "tab-btn-skills":
            self._switch_settings_section("skills")
            return

        # Handle MCP server remove buttons
        if button_id and button_id.startswith("mcp-remove-"):
            server_name = button_id[11:]  # Remove "mcp-remove-" prefix
            success, message = remove_mcp_server(server_name)
            if success:
                self.notify(message, severity="information", timeout=2)
                self._refresh_mcp_server_list()
            else:
                self.notify(message, severity="error", timeout=3)

        # Handle MCP server config buttons
        if button_id and button_id.startswith("mcp-config-"):
            server_name = button_id[11:]  # Remove "mcp-config-" prefix
            self._open_mcp_env_editor(server_name)

        # Handle MCP env editor buttons
        if button_id == "mcp-env-save":
            self._save_mcp_env()
        elif button_id == "mcp-env-cancel":
            self._close_mcp_env_editor()

        # Handle Skill toggle buttons
        if button_id and button_id.startswith("skill-toggle-"):
            skill_name = button_id[13:]  # Remove "skill-toggle-" prefix
            success, message = toggle_skill(skill_name)
            if success:
                self.notify(message, severity="information", timeout=2)
                self._refresh_skill_list()
            else:
                self.notify(message, severity="error", timeout=3)

        # Handle Skill view buttons
        if button_id and button_id.startswith("skill-view-"):
            skill_name = button_id[11:]  # Remove "skill-view-" prefix
            self._open_skill_detail_viewer(skill_name)

        # Handle Skill detail buttons
        if button_id == "skill-detail-close":
            self._close_skill_detail_viewer()
        elif button_id == "skill-detail-copy":
            self._copy_skill_content()
        elif button_id == "skill-detail-status-btn":
            self._toggle_skill_from_detail_viewer()

    def _switch_settings_section(self, section: str) -> None:
        """Switch between Models, MCP, and Skills sections in settings."""
        # Update button styles
        models_btn = self.query_one("#tab-btn-models", Button)
        mcp_btn = self.query_one("#tab-btn-mcp", Button)
        skills_btn = self.query_one("#tab-btn-skills", Button)

        # Reset all buttons
        models_btn.remove_class("-active")
        mcp_btn.remove_class("-active")
        skills_btn.remove_class("-active")

        # Activate the selected tab
        if section == "models":
            models_btn.add_class("-active")
        elif section == "mcp":
            mcp_btn.add_class("-active")
        elif section == "skills":
            skills_btn.add_class("-active")

        # Show/hide sections
        models_section = self.query_one("#section-models", Container)
        mcp_section = self.query_one("#section-mcp", Container)
        skills_section = self.query_one("#section-skills", Container)

        # Hide all sections first
        models_section.add_class("-hidden")
        mcp_section.add_class("-hidden")
        skills_section.add_class("-hidden")

        # Show the selected section
        if section == "models":
            models_section.remove_class("-hidden")
        elif section == "mcp":
            mcp_section.remove_class("-hidden")
        elif section == "skills":
            skills_section.remove_class("-hidden")

    def _open_mcp_env_editor(self, server_name: str) -> None:
        """Open a modal to edit environment variables for an MCP server."""
        env_vars = get_server_env_vars(server_name)

        if not env_vars:
            self.notify(f"No environment variables for '{server_name}'", severity="information", timeout=2)
            return

        # Remove any existing env editor overlay
        for overlay in self.query("#mcp-env-overlay"):
            overlay.remove()

        # Build input fields for each env var
        env_inputs = []
        for key, value in env_vars.items():
            env_inputs.append(Static(key, classes="mcp-env-label"))
            env_inputs.append(
                PasteableInput(
                    placeholder=f"Enter {key}",
                    value=value,
                    password=False,
                    id=f"mcp-env-{key}",
                    classes="mcp-env-input",
                )
            )

        # Create an overlay container with the editor inside
        overlay = Container(
            Container(
                Static(f"Configure {server_name}", id="mcp-env-title"),
                Vertical(*env_inputs, id="mcp-env-fields"),
                Horizontal(
                    Button("Save", id="mcp-env-save", classes="mcp-env-btn"),
                    Button("Cancel", id="mcp-env-cancel", classes="mcp-env-btn"),
                    id="mcp-env-actions",
                ),
                id="mcp-env-editor",
            ),
            id="mcp-env-overlay",
        )

        # Store the server name for saving
        self._mcp_env_editing_server = server_name

        self.mount(overlay)

    def _save_mcp_env(self) -> None:
        """Save the edited environment variables."""
        if not hasattr(self, "_mcp_env_editing_server"):
            return

        server_name = self._mcp_env_editing_server
        env_vars = get_server_env_vars(server_name)

        for key in env_vars.keys():
            input_id = f"#mcp-env-{key}"
            if self.query(input_id):
                input_widget = self.query_one(input_id, PasteableInput)
                new_value = input_widget.value
                if new_value != env_vars[key]:
                    update_mcp_server_env(server_name, key, new_value)

        self.notify(f"Saved environment variables for '{server_name}'", severity="information", timeout=2)
        self._close_mcp_env_editor()
        self._refresh_mcp_server_list()

    def _close_mcp_env_editor(self) -> None:
        """Close the env editor modal."""
        for overlay in self.query("#mcp-env-overlay"):
            overlay.remove()
        if hasattr(self, "_mcp_env_editing_server"):
            del self._mcp_env_editing_server

    def _open_skill_detail_viewer(self, skill_name: str) -> None:
        """Open a modal to view skill details and full SKILL.md content."""
        skill_info = get_skill_info(skill_name)
        if not skill_info:
            self.notify(f"Skill '{skill_name}' not found", severity="error", timeout=2)
            return

        # Remove any existing skill detail overlay
        for overlay in self.query("#skill-detail-overlay"):
            overlay.remove()

        # Get the raw SKILL.md content
        raw_content = get_skill_raw_content(skill_name)
        if not raw_content:
            raw_content = skill_info.get("instructions", "No instructions available")

        # Store raw content for copy functionality and skill name for toggling
        self._skill_detail_raw_content = raw_content
        self._skill_detail_current_name = skill_name

        # Build status button with colored dot
        is_enabled = skill_info["enabled"]
        status_dot = "●"  # Unicode bullet
        status_text = f"{status_dot} Enabled" if is_enabled else f"{status_dot} Disabled"

        # Build action sets display
        action_sets = ", ".join(skill_info.get("action_sets", [])) or "None"
        action_sets_text = f"Action Sets: {action_sets}"

        # Create the overlay with title row layout
        overlay = Container(
            Container(
                # Header section (fixed)
                Container(
                    # Title row: skill name on left, status button on right
                    Horizontal(
                        Static(f"Skill: {skill_name}", id="skill-detail-title"),
                        Button(status_text, id="skill-detail-status-btn"),
                        id="skill-detail-title-row",
                    ),
                    Static(skill_info["description"], id="skill-detail-desc"),
                    Static(action_sets_text, id="skill-detail-action-sets"),
                    id="skill-detail-header",
                ),
                # Scrollable content
                VerticalScroll(
                    Static(raw_content),
                    id="skill-detail-content",
                ),
                # Action buttons (fixed at bottom)
                Horizontal(
                    Button("Copy", id="skill-detail-copy", classes="skill-detail-btn -copy"),
                    Button("Close", id="skill-detail-close", classes="skill-detail-btn"),
                    id="skill-detail-actions",
                ),
                id="skill-detail-viewer",
            ),
            id="skill-detail-overlay",
        )

        self.mount(overlay)

        # Apply inline color to status button (CSS classes don't reliably override Button defaults)
        if self.query("#skill-detail-status-btn"):
            status_btn = self.query_one("#skill-detail-status-btn", Button)
            status_btn.styles.color = "#00cc00" if is_enabled else "#ff4f18"

    def _close_skill_detail_viewer(self) -> None:
        """Close the skill detail viewer modal."""
        for overlay in self.query("#skill-detail-overlay"):
            overlay.remove()
        if hasattr(self, "_skill_detail_raw_content"):
            del self._skill_detail_raw_content
        if hasattr(self, "_skill_detail_current_name"):
            del self._skill_detail_current_name

    def _toggle_skill_from_detail_viewer(self) -> None:
        """Toggle the skill status from within the detail viewer."""
        if not hasattr(self, "_skill_detail_current_name"):
            return

        skill_name = self._skill_detail_current_name
        success, message = toggle_skill(skill_name)

        if success:
            self.notify(message, severity="information", timeout=2)
            # Refresh the skill list in settings
            self._refresh_skill_list()
            # Close then reopen to show updated status (avoid duplicate ID)
            for overlay in self.query("#skill-detail-overlay"):
                overlay.remove()
            # Use call_after_refresh to ensure DOM is updated before reopening
            self.call_after_refresh(lambda: self._open_skill_detail_viewer(skill_name))
        else:
            self.notify(message, severity="error", timeout=3)

    def _copy_skill_content(self) -> None:
        """Copy the skill SKILL.md content to clipboard."""
        if not hasattr(self, "_skill_detail_raw_content"):
            self.notify("No content to copy", severity="error", timeout=2)
            return

        try:
            import pyperclip
            pyperclip.copy(self._skill_detail_raw_content)
            self.notify("Copied to clipboard!", severity="information", timeout=2)
        except ImportError:
            # Fallback: try using the system clipboard via subprocess
            try:
                import subprocess
                import sys
                if sys.platform == "win32":
                    subprocess.run(["clip"], input=self._skill_detail_raw_content.encode("utf-8"), check=True)
                    self.notify("Copied to clipboard!", severity="information", timeout=2)
                elif sys.platform == "darwin":
                    subprocess.run(["pbcopy"], input=self._skill_detail_raw_content.encode("utf-8"), check=True)
                    self.notify("Copied to clipboard!", severity="information", timeout=2)
                else:
                    # Linux - try xclip or xsel
                    try:
                        subprocess.run(["xclip", "-selection", "clipboard"], input=self._skill_detail_raw_content.encode("utf-8"), check=True)
                        self.notify("Copied to clipboard!", severity="information", timeout=2)
                    except FileNotFoundError:
                        subprocess.run(["xsel", "--clipboard", "--input"], input=self._skill_detail_raw_content.encode("utf-8"), check=True)
                        self.notify("Copied to clipboard!", severity="information", timeout=2)
            except Exception as e:
                self.notify(f"Could not copy: {e}", severity="error", timeout=3)
