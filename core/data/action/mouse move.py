from core.action.action_framework.registry import action

@action(
        name="mouse move",
        description="Moves the mouse cursor to a specific screen coordinate.",
        mode="GUI",
        input_schema={
                "x": {
                        "type": "integer",
                        "example": 640,
                        "description": "Target X-coordinate in pixels (required)."
                },
                "y": {
                        "type": "integer",
                        "example": 360,
                        "description": "Target Y-coordinate in pixels (required)."
                },
                "duration": {
                        "type": "number",
                        "example": 0.25,
                        "description": "Optional duration in seconds for a smooth move. Defaults to instant."
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "success",
                        "description": "'success' if the cursor moved, 'error' otherwise."
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
                        "description": "The final cursor coordinates."
                },
                "message": {
                        "type": "string",
                        "example": "Missing coordinates.",
                        "description": "Optional error message if the operation failed."
                }
        },
        requirement=["pyautogui"],
        test_payload={
                "x": 640,
                "y": 360,
                "duration": 0.25,
                "simulated_mode": False
        }
)
def mouse_move(input_data: dict) -> dict:
    import json, sys, subprocess, importlib
    pkg = 'pyautogui'
    try:
        importlib.import_module(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])
    import pyautogui
    x = input_data.get('x')
    y = input_data.get('y')
    duration = float(input_data.get('duration', 0))
    if x is None or y is None:
        return {'status': 'error', 'position': {}, 'message': 'Both x and y are required.'}
        exit()
    try:
        pyautogui.moveTo(int(x), int(y), duration=duration)
        return {'status': 'success', 'position': {'x': int(x), 'y': int(y)}, 'message': ''}
    except Exception as e:
        return {'status': 'error', 'position': {}, 'message': str(e)}