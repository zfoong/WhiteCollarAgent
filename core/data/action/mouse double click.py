from core.action.action_framework.registry import action

@action(
    name="mouse double click",
    description="Performs a left-button double click at the specified screen coordinates (or at the current cursor position if no coordinates are provided).",
    mode="GUI",
    input_schema={
        "x": {
            "type": "integer",
            "example": 640,
            "description": "X-coordinate in pixels. If omitted, the current cursor X is used."
        },
        "y": {
            "type": "integer",
            "example": 360,
            "description": "Y-coordinate in pixels. If omitted, the current cursor Y is used."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if the double click succeeded, 'error' otherwise."
        },
        "message": {
            "type": "string",
            "example": "Coordinate out of bounds.",
            "description": "Optional error message."
        }
    },
    requirement=["pyautogui"],
    test_payload={
        "x": 640,
        "y": 360,
        "simulated_mode": False
    }
)
def mouse_double_click(input_data: dict) -> dict:
    import json, sys, subprocess, importlib
    pkg = 'pyautogui'
    try:
        importlib.import_module(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])
    import pyautogui
    x = input_data.get('x')
    y = input_data.get('y')
    try:
        pos_x, pos_y = (x, y) if x is not None and y is not None else pyautogui.position()
        pyautogui.doubleClick(x=pos_x, y=pos_y, button='left')
        return {'status': 'success', 'message': ''}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}