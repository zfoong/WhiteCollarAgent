from core.action.action_framework.registry import action

@action(
    name="delete folder",
    description="Deletes a folder/directory and all its contents.",
    mode="CLI",
    input_schema={
        "path": {
            "type": "string",
            "example": "/home/user/old_folder",
            "description": "The folder path to delete"
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "Indicates the result of the delete operation"
        },
        "deleted": {
            "type": "string",
            "example": "/home/user/old_folder",
            "description": "The folder path that was deleted"
        }
    },
    requirement=["shutil"],
    test_payload={
            "path": "/home/user/old_folder",
            "simulated_mode": True
    }
)
def delete_folder(input_data: dict) -> dict:
    import os, json
    import shutil

    simulated_mode = input_data.get('simulated_mode', False)
    
    path = input_data['path']
    
    if simulated_mode:
        # Return mock result for testing
        return {'status': 'success', 'deleted': path}
    
    try:
        shutil.rmtree(path)
        return {'status': 'success', 'deleted': path}
    except Exception as e:
        return {'status': 'error', 'deleted': '', 'message': str(e)}