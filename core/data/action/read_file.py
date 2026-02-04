from core.action.action_framework.registry import action

@action(
    name="read_file",
    description="Read the entire content of a text file. For large files (over 50KB), consider using stream_read instead.",
    mode="CLI",
    action_sets=["file_operations"],
    input_schema={
        "file_path": {
            "type": "string",
            "example": "/workspace/document.txt",
            "description": "Absolute path to the text file to read."
        },
        "encoding": {
            "type": "string",
            "example": "utf-8",
            "description": "File encoding. Defaults to 'utf-8'."
        },
        "max_chars": {
            "type": "integer",
            "example": 50000,
            "description": "Maximum characters to return. Defaults to 50000."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' or 'error'."
        },
        "content": {
            "type": "string",
            "description": "File content."
        },
        "truncated": {
            "type": "boolean",
            "description": "True if content was truncated due to max_chars limit."
        },
        "message": {
            "type": "string",
            "description": "Error message if status is 'error'."
        }
    },
    test_payload={
        "file_path": "/workspace/test.txt",
        "simulated_mode": True
    }
)
def read_file(input_data: dict) -> dict:
    import os

    simulated_mode = input_data.get('simulated_mode', False)

    if simulated_mode:
        return {
            'status': 'success',
            'content': 'Test file content',
            'truncated': False
        }

    file_path = input_data.get('file_path', '')
    encoding = input_data.get('encoding', 'utf-8')
    max_chars = int(input_data.get('max_chars', 50000))

    if not file_path:
        return {'status': 'error', 'content': '', 'truncated': False, 'message': 'file_path is required.'}

    if not os.path.isfile(file_path):
        return {'status': 'error', 'content': '', 'truncated': False, 'message': f'File not found: {file_path}'}

    try:
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read(max_chars + 1)

        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]

        return {
            'status': 'success',
            'content': content,
            'truncated': truncated
        }
    except Exception as e:
        return {'status': 'error', 'content': '', 'truncated': False, 'message': str(e)}
