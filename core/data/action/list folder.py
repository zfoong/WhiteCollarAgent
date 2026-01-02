from core.action.action_framework.registry import action

@action(
        name="list folder",
        description="Lists the contents of a specified folder/directory.",
        mode="CLI",
        input_schema={
                "path": {
                        "type": "string",
                        "example": "/home/user/documents",
                        "description": "The folder path to list"
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "success",
                        "description": "Indicates the result of the list operation"
                },
                "path": {
                        "type": "string",
                        "example": "/home/user/documents",
                        "description": "The folder path that was listed"
                },
                "contents": {
                        "type": "array",
                        "example": [
                                "file1.txt",
                                "subfolder",
                                "image.png"
                        ],
                        "description": "List of files/folders contained in the specified directory"
                }
        },
        test_payload={
                "path": "/home/user/documents",
                "simulated_mode": True
        }
)
def list_folder(input_data: dict) -> dict:
    import os, json

    path = input_data['path']
    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        return {'status': 'success', 'path': path, 'contents': ['file1.txt', 'file2.txt', 'subfolder']}
    
    try:
        contents = os.listdir(path)
        return {'status': 'success', 'path': path, 'contents': contents}
    except Exception as e:
        return {'status': 'error', 'path': '', 'contents': [], 'message': str(e)}