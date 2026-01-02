from core.action.action_framework.registry import action

@action(
    name="window minimize",
    description="Minimizes an application window. If a title is provided, the first matching window is minimized; otherwise the currently active window is minimized.",
    input_schema={
        "title": {
            "type": "string",
            "example": "Google Chrome",
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
    mode="GUI",
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if the window was minimized, 'error' otherwise."
        },
        "matched_title": {
            "type": "string",
            "example": "Google Chrome",
            "description": "Title of the window that was minimized (present on success)."
        },
        "message": {
            "type": "string",
            "example": "No matching window found.",
            "description": "Optional error message."
        }
    },
    requirement=["pygetwindow"],
    test_payload={
        "title": "Google Chrome",
        "exact": False,
        "index": 0,
        "simulated_mode": False
    }
)
def window_minimize(input_data: dict) -> dict:
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
                return {'status': 'error', 'matched_title': '', 'message': 'No active window to minimize.'}
                sys.exit()
        win.minimize()
        return {'status': 'success', 'matched_title': win.title, 'message': ''}
    except Exception as e:
        return {'status': 'error', 'matched_title': '', 'message': str(e)}