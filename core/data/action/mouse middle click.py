from core.action.action_framework.registry import action

@action(
        name="mouse middle click",
        description="Performs a single middle-button mouse click at the specified screen coordinates (or at the current cursor position if no coordinates are provided).",
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
                        "description": "'success' if the click succeeded, 'error' otherwise."
                },
                "position": {
                        "type": "object",
                        "properties": {
                                "x": {
                                        "type": "integer"
                                },
                                "y": {
                                        "type": "integer"
                                }
                        },
                        "example": {
                                "x": 640,
                                "y": 360
                        },
                        "description": "The screen coordinates where the click was executed."
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
def mouse_middle_click(input_data: dict) -> dict:
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
        pyautogui.click(x=pos_x, y=pos_y, button='middle')
        return {'status': 'success', 'position': {'x': pos_x, 'y': pos_y}, 'message': ''}
    except Exception as e:
        return {'status': 'error', 'position': {}, 'message': str(e)}