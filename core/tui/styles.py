"""CSS styles for the TUI interface."""

TUI_CSS = """
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
