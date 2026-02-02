"""Custom widgets for the TUI interface."""
from __future__ import annotations

from typing import Optional, Tuple

from textual import events
from textual.widgets import OptionList
from textual.widgets.option_list import Option
from textual.widgets import Input
from textual.widgets import RichLog as _BaseLog

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text


class ContextMenu(OptionList):
    """Simple context menu for copy operations."""

    DEFAULT_CSS = """
    ContextMenu {
        width: 20;
        height: auto;
        border: ascii #ff4f18;
        background: #0a0a0a;
        layer: overlay;
    }

    ContextMenu > .option-list--option {
        color: #e5e5e5;
        padding: 0 1;
    }

    ContextMenu > .option-list--option-highlighted {
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


class PasteableInput(Input):
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


class ConversationLog(_BaseLog):
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
        for menu in self.app.query("ContextMenu"):
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
            menu = ContextMenu(text_to_copy, event.screen_x, event.screen_y)
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
