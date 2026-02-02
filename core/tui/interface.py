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
from core.tui.app import CraftApp
from core.tui.data import TimelineEntry, ActionEntry, ActionUpdate

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

        # Handle action start
        elif kind == "action_start":
            self._agent_state = "working"
            entry = ActionEntry(
                kind=kind,
                message=action_name,  # Use just the action name
                style=style,
                is_completed=False,
                parent_task=self._current_task_name
            )
            self._task_action_entries[entry_key] = entry
            await self.action_updates.put(ActionUpdate(operation="add", entry=entry, entry_key=entry_key))

        # Handle action end - update existing entry
        elif kind == "action_end":
            if entry_key in self._task_action_entries:
                self._task_action_entries[entry_key].is_completed = True
                await self.action_updates.put(ActionUpdate(operation="update", entry_key=entry_key))

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
        # Choose icon based on completion status
        if entry.is_completed:
            icon = CraftApp.ICON_COMPLETED
        else:
            # Use current frame of loading animation
            icon = CraftApp.ICON_LOADING_FRAMES[self._loading_frame_index % len(CraftApp.ICON_LOADING_FRAMES)]

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
        if kind in {"action", "action_start", "action_end", "waiting_for_user"}:
            return "action"
        if kind in {"screen", "info", "note"}:
            return "info"
        if kind in {"user", "user message"}:
            return "user"
        if kind in {"agent", "agent message"}:
            return "agent"
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
