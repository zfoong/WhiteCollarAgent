from core.action.action_framework.registry import action

@action(
    name="window close",
    description="Closes an application window. If a title is provided, the first matching window is closed; otherwise the currently active window is closed.",
    mode="GUI",
    input_schema={
        "title": {
            "type": "string",
            "example": "Microsoft Word",
            "description": "Substring (case-insensitive) of the window title to match. If omitted, the active window is used."
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
            "description": "'success' if the window was closed, 'error' otherwise."
        },
        "matched_title": {
            "type": "string",
            "example": "Document1 \u2013 Word",
            "description": "Title of the window that was closed (present on success)."
        },
        "message": {
            "type": "string",
            "example": "No matching window found.",
            "description": "Optional error message."
        }
    },
    requirement=["pygetwindow"],
    test_payload={
        "title": "Microsoft Word",
        "exact": False,
        "index": 0,
        "simulated_mode": False
    }
)
def window_close(input_data: dict) -> dict:
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

    try:
        if title:
            windows = gw.getWindowsWithTitle(title) if not exact else [w for w in gw.getAllWindows() if w.title == title]
            if not windows:
                return {'status': 'error', 'matched_title': '', 'message': 'No matching window found.'}
                sys.exit()
            if index < 0 or index >= len(windows):
                return {'status': 'error', 'matched_title': '', 'message': 'index out of range.'}
                sys.exit()
            win = windows[index]
        else:
            win = gw.getActiveWindow()
            if win is None:
                return {'status': 'error', 'matched_title': '', 'message': 'No active window to close.'}
                sys.exit()
        win.close()
        return {'status': 'success', 'matched_title': win.title, 'message': ''}
    except Exception as e:
        return {'status': 'error', 'matched_title': '', 'message': str(e)}