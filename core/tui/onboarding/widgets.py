# -*- coding: utf-8 -*-
"""
Textual widgets for the onboarding wizard.
"""

from typing import TYPE_CHECKING, Any, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label, Button, Input

from rich.text import Text

if TYPE_CHECKING:
    from core.tui.onboarding.hard_onboarding import TUIHardOnboarding


ONBOARDING_CSS = """
/* Onboarding wizard screen */
OnboardingWizardScreen {
    align: center middle;
    background: #000000;
}

#onboarding-container {
    width: 80;
    max-width: 95%;
    height: auto;
    max-height: 90%;
    background: #000000;
    padding: 2 3;
    border: solid #2a2a2a;
}

#onboarding-header {
    height: auto;
    margin-bottom: 2;
}

#onboarding-title {
    text-align: center;
    text-style: bold;
    color: #ff4f18;
    margin-bottom: 1;
}

#onboarding-progress {
    text-align: center;
    color: #666666;
}

#step-container {
    height: auto;
    margin-bottom: 2;
}

#step-title {
    text-style: bold;
    color: #ffffff;
    margin-bottom: 1;
}

#step-description {
    color: #a0a0a0;
    margin-bottom: 1;
}

#step-content {
    height: auto;
    margin: 1 0;
}

/* Option list for selections - use class selector for dynamic IDs */
.option-list {
    width: 100%;
    height: auto;
    max-height: 12;
    background: transparent;
    border: none;
}

.option-list > ListItem {
    padding: 0 0;
}

.option-list > ListItem.--highlight .option-label {
    background: #ff4f18;
    color: #ffffff;
    text-style: bold;
}

.option-label {
    color: #a0a0a0;
}

.option-desc {
    color: #666666;
    margin-left: 2;
}

/* Text input - use class selector for dynamic IDs */
.step-input {
    width: 100%;
    border: solid #2a2a2a;
    background: #0a0a0a;
    color: #e5e5e5;
    margin: 1 0;
}

.step-input:focus {
    border: solid #ff4f18;
}

/* Multi-select list - use class selector for dynamic IDs */
.multi-select-list {
    height: auto;
    max-height: 15;
    margin: 1 0;
    border: solid #2a2a2a;
    background: #0a0a0a;
    padding: 1;
}

.multi-select-row {
    height: 1;
    margin-bottom: 1;
}

.multi-select-toggle {
    width: 3;
    min-width: 3;
    height: 1;
    background: #333333;
    color: #666666;
    border: none;
    margin-right: 1;
}

.multi-select-toggle.-selected {
    color: #00cc00;
}

.multi-select-toggle:hover {
    background: #ff4f18;
    color: #ffffff;
}

.multi-select-label {
    width: 1fr;
    color: #a0a0a0;
}

/* Error message */
#step-error {
    color: #ff4444;
    margin-top: 1;
}

/* Navigation buttons */
#nav-buttons {
    height: auto;
    margin-top: 2;
}

.nav-btn {
    width: auto;
    min-width: 12;
    height: 3;
    background: #333333;
    color: #a0a0a0;
    border: solid #2a2a2a;
    margin-right: 1;
}

.nav-btn:hover {
    background: #ff4f18;
    color: #ffffff;
}

.nav-btn.-primary {
    background: #ff4f18;
    color: #ffffff;
}

.nav-btn.-primary:hover {
    background: #ff7040;
}

.nav-btn:disabled {
    background: #1a1a1a;
    color: #444444;
}

/* Skip hint */
#skip-hint {
    color: #666666;
    text-style: italic;
    margin-top: 1;
}
"""


class OnboardingWizardScreen(Screen):
    """
    Multi-step wizard screen for hard onboarding.

    Guides user through:
    1. LLM Provider selection
    2. API Key input
    3. User name (optional)
    4. Agent name (optional)
    5. MCP server selection (optional)
    6. Skills selection (optional)
    """

    CSS = ONBOARDING_CSS

    def __init__(self, handler: "TUIHardOnboarding"):
        super().__init__()
        self._handler = handler
        self._current_step = 0
        self._multi_select_values: List[str] = []

    def compose(self) -> ComposeResult:
        with Container(id="onboarding-container"):
            with Container(id="onboarding-header"):
                yield Static("Welcome to White Collar Agent", id="onboarding-title")
                yield Static(self._get_progress_text(), id="onboarding-progress")

            with Container(id="step-container"):
                yield Static("", id="step-title")
                yield Static("", id="step-description")
                yield Container(id="step-content")
                yield Static("", id="step-error")

            with Horizontal(id="nav-buttons"):
                yield Button("Back", id="btn-back", classes="nav-btn", disabled=True)
                yield Button("Skip", id="btn-skip", classes="nav-btn")
                yield Button("Next", id="btn-next", classes="nav-btn -primary")

            yield Static("", id="skip-hint")

    def on_mount(self) -> None:
        """Initialize the first step when mounted."""
        self._show_step(0)

    def _get_progress_text(self) -> str:
        """Get progress indicator text."""
        total = self._handler.get_step_count()
        current = self._current_step + 1
        return f"Step {current} of {total}"

    def _show_step(self, index: int) -> None:
        """Display the step at the given index."""
        self._current_step = index
        step = self._handler.get_step(index)

        # Update progress
        self.query_one("#onboarding-progress", Static).update(self._get_progress_text())

        # Update step title and description
        self.query_one("#step-title", Static).update(step.title)
        self.query_one("#step-description", Static).update(step.description)

        # Clear error
        self.query_one("#step-error", Static).update("")

        # Update navigation buttons
        back_btn = self.query_one("#btn-back", Button)
        back_btn.disabled = index == 0

        skip_btn = self.query_one("#btn-skip", Button)
        skip_btn.display = not step.required

        # Update skip hint
        skip_hint = self.query_one("#skip-hint", Static)
        if not step.required:
            skip_hint.update("This step is optional - you can skip it")
        else:
            skip_hint.update("")

        # Build step content
        content = self.query_one("#step-content", Container)
        content.remove_children()

        options = step.get_options()

        if step.name in ("mcp", "skills"):
            # Multi-select list
            self._multi_select_values = step.get_default()
            self._build_multi_select(content, options)
        elif options:
            # Single-select list
            self._build_option_list(content, options, step.get_default())
        else:
            # Text input
            self._build_text_input(content, step.get_default())

    def _build_option_list(self, container: Container, options: list, default: str) -> None:
        """Build a single-select option list."""
        items = []
        highlight_idx = 0
        step = self._handler.get_step(self._current_step)

        for i, opt in enumerate(options):
            label_text = f"  {opt.label}"
            if opt.description:
                label_text += f"  ({opt.description})"

            items.append(ListItem(Label(label_text, classes="option-label"), id=f"opt-{step.name}-{opt.value}"))

            if opt.value == default:
                highlight_idx = i

        list_view = ListView(*items, id=f"option-list-{step.name}", classes="option-list")
        container.mount(list_view)

        # Highlight default after mount
        def set_highlight():
            list_view.index = highlight_idx
        self.call_after_refresh(set_highlight)

    def _build_text_input(self, container: Container, default: str) -> None:
        """Build a text input field."""
        # Check if this is API key step (should be password field)
        step = self._handler.get_step(self._current_step)
        is_password = step.name == "api_key"

        input_widget = Input(
            value=default,
            placeholder="Enter value..." if not is_password else "Enter API key (Ctrl+V to paste)",
            password=False,  # Show API key for clarity during setup
            id=f"step-input-{step.name}",
            classes="step-input"
        )
        container.mount(input_widget)
        self.call_after_refresh(input_widget.focus)

    def _build_multi_select(self, container: Container, options: list) -> None:
        """Build a multi-select list with toggle buttons."""
        step = self._handler.get_step(self._current_step)
        scroll = VerticalScroll(id=f"multi-select-list-{step.name}", classes="multi-select-list")

        for opt in options:
            is_selected = opt.value in self._multi_select_values
            toggle_text = "[+]" if is_selected else "[-]"
            toggle_class = "multi-select-toggle -selected" if is_selected else "multi-select-toggle"

            row = Horizontal(
                Button(toggle_text, id=f"toggle-{opt.value}", classes=toggle_class),
                Static(opt.label, classes="multi-select-label"),
                classes="multi-select-row"
            )
            scroll.compose_add_child(row)

        container.mount(scroll)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-back":
            self._go_back()
        elif button_id == "btn-skip":
            self._skip_step()
        elif button_id == "btn-next":
            self._go_next()
        elif button_id and button_id.startswith("toggle-"):
            value = button_id[7:]  # Remove "toggle-" prefix
            self._toggle_multi_select(value, event.button)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list view selection (for single-select)."""
        # Check if it's an option list (IDs are now like "option-list-provider")
        if event.list_view.id and event.list_view.id.startswith("option-list-"):
            # Don't auto-advance on selection, wait for Next button
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input field."""
        self._go_next()

    def _toggle_multi_select(self, value: str, button: Button) -> None:
        """Toggle a multi-select option."""
        if value in self._multi_select_values:
            self._multi_select_values.remove(value)
            button.label = "[-]"
            button.remove_class("-selected")
        else:
            self._multi_select_values.append(value)
            button.label = "[+]"
            button.add_class("-selected")

    def _get_current_value(self) -> Any:
        """Get the current value from the active step widget."""
        step = self._handler.get_step(self._current_step)

        if step.name in ("mcp", "skills"):
            return self._multi_select_values

        # Check for option list (IDs are now like "option-list-provider")
        option_list = self.query(f"#option-list-{step.name}")
        if option_list:
            list_view = option_list.first()
            if list_view and list_view.highlighted_child:
                # Extract value from id (e.g., "opt-provider-openai" -> "openai")
                item_id = list_view.highlighted_child.id
                prefix = f"opt-{step.name}-"
                if item_id and item_id.startswith(prefix):
                    return item_id[len(prefix):]

        # Check for text input (IDs are now like "step-input-user_name")
        input_widget = self.query(f"#step-input-{step.name}")
        if input_widget:
            return input_widget.first().value

        return step.get_default()

    def _go_back(self) -> None:
        """Go to the previous step."""
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _skip_step(self) -> None:
        """Skip the current optional step."""
        step = self._handler.get_step(self._current_step)
        # Store default/empty value
        self._handler.set_step_data(step.name, step.get_default())
        self._advance()

    def _go_next(self) -> None:
        """Validate and advance to the next step."""
        step = self._handler.get_step(self._current_step)
        value = self._get_current_value()

        # Validate
        is_valid, error = step.validate(value)
        if not is_valid:
            self.query_one("#step-error", Static).update(error or "Invalid input")
            return

        # Store value
        self._handler.set_step_data(step.name, value)

        self._advance()

    def _advance(self) -> None:
        """Advance to the next step or complete."""
        if self._current_step < self._handler.get_step_count() - 1:
            self._show_step(self._current_step + 1)
        else:
            self._complete()

    def _complete(self) -> None:
        """Complete the wizard and return to the app."""
        self._handler.on_complete(cancelled=False)
        self.app.pop_screen()

    def action_cancel(self) -> None:
        """Handle Escape key to cancel wizard."""
        self._handler.on_complete(cancelled=True)
        self.app.pop_screen()
