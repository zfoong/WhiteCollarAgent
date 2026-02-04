from core.action.action_framework.registry import action


@action(
    name="stream_edit",
    description="Performs exact string replacement in a file. You MUST use stream_read first to read the file before editing. The old_string must be unique in the file - if it appears multiple times, use replace_all=True or provide more context to make it unique.",
    mode="CLI",
    input_schema={
        "file_path": {
            "type": "string",
            "example": "/path/to/file.py",
            "description": "Absolute path to the file to edit. The file must exist."
        },
        "old_string": {
            "type": "string",
            "example": "def old_function():",
            "description": "The exact text to find and replace. Must match exactly including whitespace and indentation. The edit will FAIL if old_string is not found or appears multiple times (unless replace_all=True)."
        },
        "new_string": {
            "type": "string",
            "example": "def new_function():",
            "description": "The text to replace old_string with. Can be empty string to delete the old_string."
        },
        "replace_all": {
            "type": "boolean",
            "example": False,
            "description": "If True, replace ALL occurrences of old_string. If False (default), the edit fails if old_string appears more than once.",
            "default": False
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' or 'error'."
        },
        "message": {
            "type": "string",
            "example": "Successfully replaced 1 occurrence(s)",
            "description": "Description of what was done or error message if failed."
        },
        "occurrences_replaced": {
            "type": "integer",
            "example": 1,
            "description": "Number of occurrences that were replaced."
        }
    },
    test_payload={
        "file_path": "/tmp/test_file.txt",
        "old_string": "old text",
        "new_string": "new text",
        "replace_all": False,
        "simulated_mode": True
    }
)
def stream_edit_action(input_data: dict) -> dict:
    import os

    simulated_mode = input_data.get('simulated_mode', False)

    if simulated_mode:
        return {
            'status': 'success',
            'message': 'Successfully replaced 1 occurrence(s)',
            'occurrences_replaced': 1
        }

    try:
        file_path = input_data.get('file_path')
        old_string = input_data.get('old_string')
        new_string = input_data.get('new_string', '')
        replace_all = input_data.get('replace_all', False)

        # Validate inputs
        if not file_path:
            return {
                'status': 'error',
                'message': 'file_path is required',
                'occurrences_replaced': 0
            }

        if old_string is None:
            return {
                'status': 'error',
                'message': 'old_string is required',
                'occurrences_replaced': 0
            }

        if not os.path.isfile(file_path):
            return {
                'status': 'error',
                'message': f'File does not exist: {file_path}',
                'occurrences_replaced': 0
            }

        if old_string == new_string:
            return {
                'status': 'error',
                'message': 'old_string and new_string are identical - no change needed',
                'occurrences_replaced': 0
            }

        # Read the file
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Count occurrences
        count = content.count(old_string)

        if count == 0:
            return {
                'status': 'error',
                'message': 'old_string not found in file. Make sure the text matches exactly including whitespace and indentation.',
                'occurrences_replaced': 0
            }

        if count > 1 and not replace_all:
            return {
                'status': 'error',
                'message': f'old_string appears {count} times in file. Either provide more context to make it unique, or set replace_all=True to replace all occurrences.',
                'occurrences_replaced': 0
            }

        # Perform the replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            # Replace only the first occurrence (we already verified there's exactly 1)
            new_content = content.replace(old_string, new_string, 1)

        # Write the file
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            f.write(new_content)

        return {
            'status': 'success',
            'message': f'Successfully replaced {count} occurrence(s)',
            'occurrences_replaced': count
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'occurrences_replaced': 0
        }
