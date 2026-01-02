from core.action.action_framework.registry import action

@action(
    name="window focus",
    description="Brings an existing application window to the foreground (switches focus) by matching its title.",
    input_schema={
        "title": {
            "type": "string",
            "example": "Notepad",
            "description": "Substring (case-insensitive) of the window title to match (required)."
        },
        "exact": {
            "type": "boolean",
            "example": False,
            "description": "If true, match the title exactly; otherwise use substring matching (default: false)."
        },
        "index": {
            "type": "integer",
            "example": 0,
            "description": "If multiple windows match, select by zero-based index (default: 0)."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if focus changed, 'error' otherwise."
        },
        "matched_title": {
            "type": "string",
            "example": "Untitled - Notepad",
            "description": "The exact title of the window that was focused (present on success)."
        },
        "message": {
            "type": "string",
            "example": "No matching window found.",
            "description": "Optional error message."
        }
    },
    requirement=["pygetwindow"],
    test_payload={
        "title": "Notepad",
        "exact": False,
        "index": 0,
        "simulated_mode": False
    }
)
def window_focus(input_data: dict) -> dict:
    import json, sys, subprocess, importlib
    pkg = 'pygetwindow'
    try:
        importlib.import_module(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

    import pygetwindow as gw

    title = str(input_data.get('title', '')).strip()
    exact = bool(input_data.get('exact', False))
    index = int(input_data.get('index', 0))

    if not title:
        return {'status': 'error', 'matched_title': '', 'message': 'title is required.'}
        sys.exit()

    try:
        windows = gw.getWindowsWithTitle(title) if not exact else [w for w in gw.getAllWindows() if w.title == title]
        if not windows:
            return {'status': 'error', 'matched_title': '', 'message': 'No matching window found.'}
            sys.exit()
        if index < 0 or index >= len(windows):
            return {'status': 'error', 'matched_title': '', 'message': 'index out of range.'}
            sys.exit()
        win = windows[index]
        win.activate()
        return {'status': 'success', 'matched_title': win.title, 'message': ''}
    except Exception as e:
        return {'status': 'error', 'matched_title': '', 'message': str(e)}