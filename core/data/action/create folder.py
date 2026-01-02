from core.action.action_framework.registry import action

@action(
    name="create folder",
    description="This action creates a new folder in the operating system at a given path.",
    mode="CLI",
    input_schema={
        "path": {
            "type": "string",
            "example": "/home/user/Documents",
            "description": "Full directory path where the folder will be created"
        },
        "folder_name": {
            "type": "string",
            "example": "MyNewFolder",
            "description": "Name of the new folder"
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "Indicates the result of the folder creation"
        },
        "path": {
            "type": "string",
            "example": "/home/user/Documents/MyNewFolder",
            "description": "The full path to the newly created folder"
        }
    },
    requirement=["Path"],
    test_payload={
        "path": "/home/user/Documents",
        "folder_name": "MyNewFolder",
        "simulated_mode": True
    }
)
def create_folder(input_data: dict) -> dict:
    import json
    from pathlib import Path

    simulated_mode = input_data.get('simulated_mode', False)
    
    base_path = str(input_data.get('path', '')).strip()
    folder_name = str(input_data.get('folder_name', '')).strip()

    if not base_path or not folder_name:
        return {'status': 'error', 'path': '', 'message': 'Both path and folder_name are required.'}

    if simulated_mode:
        # Return mock result for testing
        target_path = f"{base_path}/{folder_name}"
        return {'status': 'success', 'path': target_path}

    try:
        target = (Path(base_path).expanduser() / folder_name)
        target.mkdir(parents=True, exist_ok=True)
        return {'status': 'success', 'path': str(target.resolve())}
    except Exception as e:
        return {'status': 'error', 'path': '', 'message': str(e)}