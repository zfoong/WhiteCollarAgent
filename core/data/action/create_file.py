from core.action.action_framework.registry import action

@action(
    name="create_file",
    description="This action creates a new text file at the specified path. It handles potential errors such as invalid file paths or permission issues. The file will be created with the given filename and content. If the file already exists, it will be overwritten.",
    mode="CLI",
    action_sets=["file_operations"],
    input_schema={
        "file_path": {
            "type": "string",
            "example": "/home/user/documents/my_file.txt",
            "description": "Full path where the new text file will be created."
        },
        "file_content": {
            "type": "string",
            "example": "This is the content of the file.",
            "description": "The text content that will be written into the file."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "Indicates whether the file creation was successful or not."
        },
        "path": {
            "type": "string",
            "example": "/home/user/documents/my_file.txt",
            "description": "The full path to the newly created file."
        },
        "message": {
            "type": "string",
            "example": "Invalid file path.",
            "description": "Error message if the file creation failed. Only present if status is 'error'."
        }
    },
    test_payload={
            "file_path": "/home/user/documents/my_file.txt",
            "file_content": "This is the content of the file.",
            "simulated_mode": True
    }
)
def create_text_file(input_data: dict) -> dict:
    import os
    import json

    file_path = input_data['file_path']
    file_content = input_data['file_content']
    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        return {'status': 'success', 'path': file_path}

    try:
        with open(file_path, 'w') as f:
            f.write(file_content)
        result = {'status': 'success', 'path': file_path}
    except FileNotFoundError:
        result = {'status': 'error', 'path': '', 'message': 'Invalid file path.'}
    except PermissionError:
        result = {'status': 'error', 'path': '', 'message': 'Permission denied.'}
    except Exception as e:
        result = {'status': 'error', 'path': '', 'message': str(e)}

    return result