"""Main TUI interface class for agent interaction."""
from __future__ import annotations

import asyncio
import os
import time
from asyncio import Queue
from typing import Awaitable, Callable, Optional, Tuple, TYPE_CHECKING

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from core.logger import logger
from core.state.agent_state import STATE
from core.gui.handler import GUIHandler
from core.tui.app import CraftApp
from core.tui.data import TimelineEntry, ActionEntry, ActionUpdate, FootageUpdate
from core.tui.mcp_settings import (
    list_mcp_servers,
    add_mcp_server_from_template,
    remove_mcp_server,
    enable_mcp_server,
    disable_mcp_server,
    get_available_templates,
    get_template_env_vars,
    update_mcp_server_env,
)
from core.tui.skill_settings import (
    list_skills,
    get_skill_info,
    enable_skill,
    disable_skill,
    reload_skills,
    get_skill_search_directories,
)
from core.credentials.handlers import INTEGRATION_HANDLERS

if TYPE_CHECKING:
    from core.agent_base import AgentBase


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
        self._seen_events: set[Tuple[str, str, str]] = set()
        self._status_message: str = "Agent is idle"
        self._app: CraftApp | None = None
        self._event_task: asyncio.Task[None] | None = None

        self._command_handlers: dict[str, Callable[[], Awaitable[None]]] = {}

        self.chat_updates: Queue[TimelineEntry] = Queue()
        self.action_updates: Queue[ActionUpdate] = Queue()
        self.status_updates: Queue[str] = Queue()
        self.footage_updates: Queue[FootageUpdate] = Queue()
        self._gui_mode_ended_flag: bool = False
        self._last_gui_mode: bool = False

        # Track current task and action states
        self._current_task_name: Optional[str] = None
        self._task_action_entries: dict[str, ActionEntry] = {}  # task/action name -> entry
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

    # =====================================
    # Footage Methods
    # =====================================

    async def push_footage(self, image_bytes: bytes, container_id: str = "") -> None:
        """Push a new screenshot to the footage display."""
        update = FootageUpdate(
            image_bytes=image_bytes,
            timestamp=time.time(),
            container_id=container_id,
        )
        await self.footage_updates.put(update)

    def signal_gui_mode_end(self) -> None:
        """Signal that GUI mode has ended."""
        self._gui_mode_ended_flag = True

    def gui_mode_ended(self) -> bool:
        """Check if GUI mode has ended since last check."""
        if self._gui_mode_ended_flag:
            self._gui_mode_ended_flag = False
            return True
        return False

    async def _maybe_handle_command(self, message: str) -> bool:
        parts = message.split()
        command = parts[0].lower()

        # Handle /mcp command with subcommands
        if command == "/mcp":
            await self._handle_mcp_command(parts[1:])
            return True

        # Handle /skill command with subcommands
        if command == "/skill":
            await self._handle_skill_command(parts[1:])
            return True

        # Handle /cred command
        if command == "/cred":
            await self._handle_cred_command(parts[1:])
            return True

        # Handle per-integration commands (/google, /slack, /telegram, etc.)
        integration_name = command.lstrip("/")
        if integration_name in INTEGRATION_HANDLERS:
            await self._handle_integration_command(integration_name, parts[1:])
            return True

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

        # Set footage callback on agent for GUI mode screen display
        self._agent._tui_footage_callback = self.push_footage
        # Also set on existing GUIModule if already created
        if GUIHandler.gui_module:
            GUIHandler.gui_module.set_tui_footage_callback(self.push_footage)

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

        self._app = CraftApp(self, self._default_provider, self._default_api_key)

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

        # Note: User message will be displayed via event stream when record_user_message is called
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

    async def _handle_mcp_command(self, args: list[str]) -> None:
        """Handle /mcp command with subcommands."""
        if not args:
            # Show help for /mcp command
            help_text = self._build_mcp_help_text()
            await self.chat_updates.put(("System", help_text, "system"))
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            await self._mcp_list()
        elif subcommand == "add":
            if len(args) < 2:
                templates = get_available_templates()
                template_names = ", ".join(t["name"] for t in templates)
                await self.chat_updates.put(
                    ("System", f"Usage: /mcp add <template>\nAvailable templates: {template_names}", "system")
                )
            else:
                await self._mcp_add(args[1])
        elif subcommand == "remove":
            if len(args) < 2:
                await self.chat_updates.put(("System", "Usage: /mcp remove <server_name>", "system"))
            else:
                await self._mcp_remove(args[1])
        elif subcommand == "enable":
            if len(args) < 2:
                await self.chat_updates.put(("System", "Usage: /mcp enable <server_name>", "system"))
            else:
                await self._mcp_enable(args[1])
        elif subcommand == "disable":
            if len(args) < 2:
                await self.chat_updates.put(("System", "Usage: /mcp disable <server_name>", "system"))
            else:
                await self._mcp_disable(args[1])
        elif subcommand == "templates":
            await self._mcp_templates()
        elif subcommand == "env":
            if len(args) < 4:
                await self.chat_updates.put(
                    ("System", "Usage: /mcp env <server_name> <env_key> <value>", "system")
                )
            else:
                # Join remaining args to allow values with spaces
                await self._mcp_set_env(args[1], args[2], " ".join(args[3:]))
        else:
            await self.chat_updates.put(
                ("System", f"Unknown /mcp subcommand: {subcommand}. Type /mcp for help.", "system")
            )

    async def _mcp_list(self) -> None:
        """List configured MCP servers."""
        servers = list_mcp_servers()
        if not servers:
            await self.chat_updates.put(("System", "No MCP servers configured.", "system"))
            return

        lines = ["Configured MCP Servers:", ""]
        for server in servers:
            status = "[+]" if server["enabled"] else "[-]"
            lines.append(f"  {status} {server['name']}: {server['description']}")
            lines.append(f"      Action set: {server['action_set']}")
        await self.chat_updates.put(("System", "\n".join(lines), "system"))

    async def _mcp_add(self, template_name: str) -> None:
        """Add an MCP server from a template."""
        success, message = add_mcp_server_from_template(template_name)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

        if success:
            # Check for required env vars and show hint
            env_vars = get_template_env_vars(template_name)
            empty_vars = [k for k, v in env_vars.items() if not v]
            if empty_vars:
                hint = "\nTo configure environment variables, use:"
                for var in empty_vars:
                    hint += f"\n  /mcp env {template_name} {var} <value>"
                await self.chat_updates.put(("System", hint, "system"))

    async def _mcp_remove(self, server_name: str) -> None:
        """Remove an MCP server."""
        success, message = remove_mcp_server(server_name)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    async def _mcp_enable(self, server_name: str) -> None:
        """Enable an MCP server."""
        success, message = enable_mcp_server(server_name)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    async def _mcp_disable(self, server_name: str) -> None:
        """Disable an MCP server."""
        success, message = disable_mcp_server(server_name)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    async def _mcp_templates(self) -> None:
        """Show available MCP server templates."""
        templates = get_available_templates()
        lines = ["Available MCP Server Templates:", ""]
        for template in templates:
            lines.append(f"  {template['name']}: {template['description']}")
        lines.append("")
        lines.append("Use '/mcp add <template>' to add a server.")
        await self.chat_updates.put(("System", "\n".join(lines), "system"))

    async def _mcp_set_env(self, server_name: str, env_key: str, env_value: str) -> None:
        """Set an environment variable for an MCP server."""
        success, message = update_mcp_server_env(server_name, env_key, env_value)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    def _build_mcp_help_text(self) -> str:
        """Build help text for /mcp command."""
        return """MCP Server Management Commands:

  /mcp list                      - List configured MCP servers
  /mcp add <template>            - Add a server from a template
  /mcp remove <name>             - Remove a server
  /mcp enable <name>             - Enable a server
  /mcp disable <name>            - Disable a server
  /mcp templates                 - Show available templates
  /mcp env <name> <key> <value>  - Set environment variable

Note: Changes require restart to take effect."""

    # =====================================
    # Skill Commands
    # =====================================

    async def _handle_skill_command(self, args: list[str]) -> None:
        """Handle /skill command with subcommands."""
        if not args:
            # Show help for /skill command
            help_text = self._build_skill_help_text()
            await self.chat_updates.put(("System", help_text, "system"))
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            await self._skill_list()
        elif subcommand == "info":
            if len(args) < 2:
                await self.chat_updates.put(("System", "Usage: /skill info <name>", "system"))
            else:
                await self._skill_info(args[1])
        elif subcommand == "enable":
            if len(args) < 2:
                await self.chat_updates.put(("System", "Usage: /skill enable <name>", "system"))
            else:
                await self._skill_enable(args[1])
        elif subcommand == "disable":
            if len(args) < 2:
                await self.chat_updates.put(("System", "Usage: /skill disable <name>", "system"))
            else:
                await self._skill_disable(args[1])
        elif subcommand == "reload":
            await self._skill_reload()
        elif subcommand == "dirs":
            await self._skill_dirs()
        else:
            await self.chat_updates.put(
                ("System", f"Unknown /skill subcommand: {subcommand}. Type /skill for help.", "system")
            )

    async def _skill_list(self) -> None:
        """List all discovered skills."""
        skills = list_skills()
        if not skills:
            dirs = get_skill_search_directories()
            dirs_text = ", ".join(dirs) if dirs else "none configured"
            await self.chat_updates.put(
                ("System", f"No skills discovered.\nSearch directories: {dirs_text}", "system")
            )
            return

        lines = ["Discovered Skills:", ""]
        for skill in skills:
            status = "[+]" if skill["enabled"] else "[-]"
            lines.append(f"  {status} {skill['name']}: {skill['description']}")
            if skill["action_sets"]:
                lines.append(f"      Action sets: {', '.join(skill['action_sets'])}")
        await self.chat_updates.put(("System", "\n".join(lines), "system"))

    async def _skill_info(self, name: str) -> None:
        """Show detailed information about a skill."""
        info = get_skill_info(name)
        if not info:
            await self.chat_updates.put(("System", f"Skill '{name}' not found.", "system"))
            return

        lines = [
            f"Skill: {info['name']}",
            f"Description: {info['description']}",
            f"Enabled: {'Yes' if info['enabled'] else 'No'}",
            f"User Invocable: {'Yes' if info['user_invocable'] else 'No'}",
        ]
        if info.get("argument_hint"):
            lines.append(f"Argument Hint: {info['argument_hint']}")
        if info.get("action_sets"):
            lines.append(f"Action Sets: {', '.join(info['action_sets'])}")
        if info.get("allowed_tools"):
            lines.append(f"Allowed Tools: {', '.join(info['allowed_tools'])}")
        lines.append(f"Source: {info['source']}")
        lines.append("")
        lines.append("Instructions Preview:")
        # Show first 500 chars of instructions
        instructions = info.get("instructions", "")
        if len(instructions) > 500:
            lines.append(f"  {instructions[:500]}...")
        else:
            lines.append(f"  {instructions}")

        await self.chat_updates.put(("System", "\n".join(lines), "system"))

    async def _skill_enable(self, name: str) -> None:
        """Enable a skill."""
        success, message = enable_skill(name)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    async def _skill_disable(self, name: str) -> None:
        """Disable a skill."""
        success, message = disable_skill(name)
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    async def _skill_reload(self) -> None:
        """Reload skills from disk."""
        success, message = reload_skills()
        severity = "system" if success else "error"
        await self.chat_updates.put(("System", message, severity))

    async def _skill_dirs(self) -> None:
        """Show skill search directories."""
        dirs = get_skill_search_directories()
        if not dirs:
            await self.chat_updates.put(("System", "No skill directories configured.", "system"))
            return

        lines = ["Skill Search Directories:", ""]
        for d in dirs:
            lines.append(f"  {d}")
        await self.chat_updates.put(("System", "\n".join(lines), "system"))

    def _build_skill_help_text(self) -> str:
        """Build help text for /skill command."""
        return """Skill Management Commands:

  /skill list             - List all discovered skills
  /skill info <name>      - Show skill details and instructions
  /skill enable <name>    - Enable a skill
  /skill disable <name>   - Disable a skill
  /skill reload           - Reload skills from disk
  /skill dirs             - Show skill search directories

Skills are discovered from:
  - ~/.whitecollar/skills/<name>/SKILL.md (global)
  - .whitecollar/skills/<name>/SKILL.md (project)

Skills are automatically selected during task creation based on the task description."""

    # ── Credential / Integration Commands ──

    async def _handle_cred_command(self, args: list[str]) -> None:
        if not args:
            await self.chat_updates.put(("System", "Usage: /cred <list|status|integrations>", "system"))
            return
        sub = args[0].lower()
        if sub == "list":
            from core.tui.credential_commands import list_all_credentials
            _, msg = list_all_credentials()
            await self.chat_updates.put(("System", msg, "system"))
        elif sub == "status":
            lines = ["Integration Status:", ""]
            for name, handler in INTEGRATION_HANDLERS.items():
                try:
                    _, s = await handler.status()
                    lines.append(f"  {s.split(chr(10))[0]}")
                except Exception as e:
                    lines.append(f"  {name}: Error ({e})")
            await self.chat_updates.put(("System", "\n".join(lines), "system"))
        elif sub == "integrations":
            from core.tui.credential_commands import list_integrations
            _, msg = list_integrations()
            await self.chat_updates.put(("System", msg, "system"))
        else:
            await self.chat_updates.put(("System", f"Unknown /cred subcommand: {sub}", "error"))

    async def _handle_integration_command(self, name: str, args: list[str]) -> None:
        handler = INTEGRATION_HANDLERS[name]
        if not args:
            subs = handler.subcommands
            await self.chat_updates.put(("System", f"Usage: /{name} <{'|'.join(subs)}>", "system"))
            return
        sub = args[0].lower()
        ok, msg = await handler.handle(sub, args[1:])
        await self.chat_updates.put(("System", msg, "system" if ok else "error"))

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
            "/mcp": "Manage MCP servers (list, add, remove, enable, disable).",
            "/skill": "Manage skills (list, info, enable, disable, reload).",
            "/cred": "Manage credentials (list, status, integrations).",
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
        """Continuously consume triggers and hand them to the agent.

        The agent.react() call is run in a dedicated thread with its own event loop
        to completely isolate the agent's processing from the TUI event loop.
        This ensures animations and user input remain responsive during agent processing.
        """
        try:
            while self._agent.is_running:
                trigger = await self._agent.triggers.get()
                if trigger.session_id:
                    self._tracked_sessions.add(trigger.session_id)
                # Run react() in a separate thread with its own event loop
                # This completely decouples agent processing from the TUI
                await asyncio.get_event_loop().run_in_executor(
                    None,  # Use default executor (ThreadPoolExecutor)
                    self._run_react_in_thread,
                    trigger,
                )
        except asyncio.CancelledError:  # pragma: no cover
            raise

    def _run_react_in_thread(self, trigger) -> None:
        """Run agent.react() in a dedicated thread with its own event loop.

        This method is called from run_in_executor and creates a fresh event loop
        in the worker thread. This ensures that all async operations within react()
        (including asyncio.to_thread() calls for LLM) are completely isolated from
        the main TUI event loop.
        """
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._agent.react(trigger))
        finally:
            loop.close()

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

                # Check for GUI mode transitions
                current_gui_mode = STATE.gui_mode
                if self._last_gui_mode and not current_gui_mode:
                    # GUI mode just ended
                    self.signal_gui_mode_end()
                self._last_gui_mode = current_gui_mode

                await asyncio.sleep(0.05)

        except asyncio.CancelledError:  # pragma: no cover
            raise

    async def _handle_action_event(self, kind: str, message: str, *, style: str = "action") -> None:
        """Record an action update and refresh the status bar."""
        # Extract action name from display message formats:
        # action_start/GUI action start: "Running {action_name}" -> extract action_name
        # action_end/GUI action end: "{action_name} → completed/failed" -> extract action_name
        if kind in {"action_start", "GUI action start"} and message.startswith("Running "):
            action_name = message[8:]  # Remove "Running " prefix
        elif kind in {"action_end", "GUI action end"} and " → " in message:
            action_name = message.split(" → ")[0]
        else:
            action_name = message

        # Use action name as the consistent key
        entry_key = f"{style}:{action_name}"

        # Handle task start
        if kind == "task_start":
            self._current_task_name = message
            self._agent_state = "working"
            entry = ActionEntry(
                kind=kind,
                message=message,
                style=style,
                is_completed=False,
                parent_task=None
            )
            self._task_action_entries[entry_key] = entry
            await self.action_updates.put(ActionUpdate(operation="add", entry=entry, entry_key=entry_key))

        # Handle task end - update existing entry
        elif kind == "task_end":
            if entry_key in self._task_action_entries:
                self._task_action_entries[entry_key].is_completed = True
                await self.action_updates.put(ActionUpdate(operation="update", entry_key=entry_key))
            self._current_task_name = None
            self._agent_state = "task_completed"
            self._task_completed_time = time.time()

        # Handle action start (both CLI and GUI modes)
        elif kind in {"action_start", "GUI action start"}:
            self._agent_state = "working"
            # Only add to action panel if there's an active task
            # In conversation mode, we track state but don't display actions
            if self._current_task_name:
                entry = ActionEntry(
                    kind=kind,
                    message=action_name,
                    style=style,
                    is_completed=False,
                    parent_task=self._current_task_name
                )
                self._task_action_entries[entry_key] = entry
                await self.action_updates.put(ActionUpdate(operation="add", entry=entry, entry_key=entry_key))

        # Handle action end (both CLI and GUI modes)
        elif kind in {"action_end", "GUI action end"}:
            # Update panel entry if it exists (only exists for task-mode actions)
            if entry_key in self._task_action_entries:
                self._task_action_entries[entry_key].is_completed = True
                if message and " → " in message:
                    status_part = message.split(" → ")[-1]
                    if status_part == "error" or status_part == "failed":
                        self._task_action_entries[entry_key].is_error = True
                await self.action_updates.put(ActionUpdate(operation="update", entry_key=entry_key))

            # In conversation mode, transition to idle when action completes
            if not self._current_task_name and self._agent_state == "working":
                self._agent_state = "idle"

        # Handle waiting_for_user event - set agent state to waiting
        elif kind == "waiting_for_user":
            self._agent_state = "waiting_for_user"

        # Update status based on current agent state
        status = self._generate_status_message()
        if status != self._status_message:
            self._status_message = status
            await self.status_updates.put(status)

    def _generate_status_message(self) -> str:
        """Generate personalized status message based on agent state."""
        loading_icon = CraftApp.ICON_LOADING_FRAMES[self._loading_frame_index % len(CraftApp.ICON_LOADING_FRAMES)]

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

    def format_action_entry(self, entry: ActionEntry) -> RenderableType:
        # Choose icon based on completion and error status
        if entry.is_completed:
            if entry.is_error:
                icon = CraftApp.ICON_ERROR
            else:
                icon = CraftApp.ICON_COMPLETED
        else:
            # Use current frame of loading animation
            icon = CraftApp.ICON_LOADING_FRAMES[self._loading_frame_index % len(CraftApp.ICON_LOADING_FRAMES)]

        # Determine color based on style, completion, and error status
        if entry.style == "task":
            colour = "bold #ff4f18"
        else:  # action (including errors - same color as completed)
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
        # Include both CLI and GUI action events
        if kind in {"action", "action_start", "action_end", "waiting_for_user",
                    "GUI action start", "GUI action end"}:
            return "action"
        if kind in {"screen", "info", "note"}:
            return "info"
        if kind in {"user", "user message"}:
            return "user"
        if kind in {"agent", "agent message"}:
            return "agent"
        return "agent"

    def _label_for_style(self, style: str, kind: str) -> str:
        if style == "agent":
            # Use agent name from onboarding config
            from core.onboarding.manager import onboarding_manager
            return onboarding_manager.state.agent_name or "Agent"
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
