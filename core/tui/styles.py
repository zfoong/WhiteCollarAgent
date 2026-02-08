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

#right-panel {
    width: 1fr;
    height: 100%;
    layout: vertical;
}

#vm-footage-panel {
    height: 1fr;
    min-height: 8;
    border: solid #2a2a2a;
    border-title-align: left;
    border-title-color: #ff4f18;
    background: #0a0a0a;
    margin: 0 1;
}

#vm-footage-panel.-hidden {
    display: none;
    height: 0;
    min-height: 0;
}

#action-panel {
    height: 1fr;
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
    border: none;
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
    max-width: 100%;
    height: 100%;
    border: none;
    background: #000000;
    padding: 2 3 3 3;
    content-align: center top;
    overflow: auto;
    layout: vertical;
}

/* Settings tab bar */
#settings-tab-bar {
    height: auto;
    margin-bottom: 1;
}

/* Tab button styling */
.settings-tab {
    width: auto;
    min-width: 12;
    height: 1;
    background: #1a1a1a;
    color: #666666;
    border: none;
    margin-right: 1;
}

.settings-tab:hover {
    background: #2a2a2a;
    color: #a0a0a0;
}

.settings-tab.-active {
    background: #ff4f18;
    color: #ffffff;
}

/* Settings sections */
#section-models, #section-mcp, #section-skills {
    height: auto;
    padding: 1 0;
}

#section-models.-hidden, #section-mcp.-hidden, #section-skills.-hidden {
    display: none;
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



/* MCP Server list */
#mcp-server-list {
    height: auto;
    max-height: 15;
    margin: 1 0;
    border: solid #2a2a2a;
    background: #0a0a0a;
    padding: 1;
}

.mcp-server-row {
    height: 1;
    margin-bottom: 1;
}

.mcp-server-name {
    width: 20;
    color: #ff4f18;
}

.mcp-server-desc {
    width: 1fr;
    color: #666666;
}

.mcp-config-btn {
    width: 3;
    min-width: 3;
    height: 1;
    background: #333333;
    color: #00cc00;
    border: none;
    margin-right: 1;
}

.mcp-config-btn:hover {
    background: #00cc00;
    color: #000000;
}

.mcp-remove-btn {
    width: 3;
    min-width: 3;
    height: 1;
    background: #333333;
    color: #ff4f18;
    border: none;
}

.mcp-remove-btn:hover {
    background: #ff4f18;
    color: #ffffff;
}

.mcp-empty {
    color: #666666;
    text-style: italic;
}

#mcp-servers-title, #mcp-add-title {
    color: #ffffff;
    text-style: bold;
    margin-top: 1;
}

#mcp-template-list {
    width: 100%;
    height: auto;
    max-height: 8;
    margin: 1 0;
    background: transparent;
    border: none;
}

#mcp-template-list > ListItem {
    padding: 0 0;
}

#mcp-hint {
    color: #666666;
    text-style: italic;
    margin-top: 1;
}

/* MCP Environment Editor Modal - positioned as overlay */
#mcp-env-editor {
    width: 60;
    max-width: 90%;
    border: solid #ff4f18;
    background: #0a0a0a;
    padding: 2 3;
}

#mcp-env-title {
    color: #ffffff;
    text-style: bold;
    margin-bottom: 1;
}

#mcp-env-fields {
    height: auto;
    margin: 1 0;
}

.mcp-env-label {
    color: #ff4f18;
    margin-top: 1;
}

.mcp-env-input {
    width: 100%;
    border: solid #2a2a2a;
    background: #000000;
    color: #e5e5e5;
}

.mcp-env-input:focus {
    border: solid #ff4f18;
}

#mcp-env-actions {
    height: auto;
    margin-top: 1;
}

.mcp-env-btn {
    width: auto;
    min-width: 10;
    height: 3;
    background: #333333;
    color: #a0a0a0;
    border: solid #2a2a2a;
    margin-right: 1;
}

.mcp-env-btn:hover {
    background: #ff4f18;
    color: #ffffff;
}

/* Overlay layer for modals */
#mcp-env-overlay, #skill-detail-overlay {
    layer: overlay;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    align: center middle;
}

/* Skills section */
#skills-list {
    height: auto;
    max-height: 15;
    margin: 1 0;
    border: solid #2a2a2a;
    background: #0a0a0a;
    padding: 1;
}

.skill-row {
    height: 1;
    margin-bottom: 1;
}

.skill-desc {
    width: 1fr;
    color: #666666;
    padding-left: 1;
}

.skill-toggle-btn {
    width: 3;
    min-width: 3;
    height: 1;
    background: #333333;
    color: #00cc00;
    border: none;
}

.skill-toggle-btn:hover {
    background: #00cc00;
    color: #000000;
}

.skill-toggle-btn.-disabled {
    color: #ff4f18;
}

.skill-toggle-btn.-disabled:hover {
    background: #ff4f18;
    color: #ffffff;
}

.skill-view-btn {
    width: auto;
    min-width: 18;
    height: 1;
    background: #1a1a1a;
    color: #ff4f18;
    border: none;
    text-align: left;
}

.skill-view-btn:hover {
    background: #ff4f18;
    color: #ffffff;
}

.skill-empty {
    color: #666666;
    text-style: italic;
}

#skills-title {
    color: #ffffff;
    text-style: bold;
    margin-top: 1;
}

#skills-hint {
    color: #666666;
    text-style: italic;
    margin-top: 1;
}

/* Skill Detail Viewer */
#skill-detail-viewer {
    width: 80;
    max-width: 95%;
    height: auto;
    max-height: 85%;
    border: solid #ff4f18;
    background: #0a0a0a;
    padding: 2 3;
    layout: vertical;
}

#skill-detail-header {
    height: auto;
}

#skill-detail-title-row {
    height: 1;
    margin-bottom: 1;
}

#skill-detail-title {
    color: #ff4f18;
    text-style: bold;
    width: 1fr;
}

#skill-detail-status-btn {
    width: auto;
    min-width: 12;
    height: 1;
    background: #1a1a1a;
    border: none;
}

#skill-detail-status-btn.-enabled {
    color: #00cc00;
}

#skill-detail-status-btn.-disabled {
    color: #ff4f18;
}

#skill-detail-desc {
    color: #a0a0a0;
    margin-bottom: 1;
}

#skill-detail-action-sets {
    color: #666666;
    margin-bottom: 1;
}

#skill-detail-content {
    height: 1fr;
    min-height: 10;
    max-height: 25;
    margin: 1 0;
    border: solid #2a2a2a;
    background: #000000;
    padding: 1;
    overflow-y: auto;
}

#skill-detail-content Static {
    color: #e5e5e5;
}

#skill-detail-actions {
    height: auto;
    margin-top: 1;
    dock: bottom;
}

.skill-detail-btn {
    width: auto;
    min-width: 8;
    height: 1;
    background: #333333;
    color: #a0a0a0;
    border: none;
    margin-right: 1;
}

.skill-detail-btn:hover {
    background: #ff4f18;
    color: #ffffff;
}

.skill-detail-btn.-copy {
    color: #0088ff;
}

.skill-detail-btn.-copy:hover {
    background: #0088ff;
    color: #ffffff;
}
"""
