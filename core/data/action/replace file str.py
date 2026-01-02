from core.action.action_framework.registry import action

@action(
        name="replace file str",
        description="Replaces all occurrences of a search string (literal or regex) in a text file with a replacement string.",
        mode="CLI",
        input_schema={
                "file_path": {
                        "type": "string",
                        "example": "C:\\\\Users\\\\user\\\\notes.txt",
                        "description": "Absolute path to the text file to modify."
                },
                "search": {
                        "type": "string",
                        "example": "foo",
                        "description": "String or regex pattern to search for."
                },
                "replace": {
                        "type": "string",
                        "example": "bar",
                        "description": "Replacement text."
                },
                "ignore_case": {
                        "type": "boolean",
                        "example": True,
                        "description": "If true, the search is case-insensitive."
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "success",
                        "description": "'success' if replacements were applied, 'error' otherwise."
                },
                "replacements": {
                        "type": "integer",
                        "example": 3,
                        "description": "Number of substitutions performed."
                },
                "message": {
                        "type": "string",
                        "example": "File not found.",
                        "description": "Error message if applicable."
                }
        },
        test_payload={
                "file_path": "C:\\\\Users\\\\user\\\\notes.txt",
                "search": "foo",
                "replace": "bar",
                "ignore_case": True,
                "simulated_mode": True
        }
)
def replace_file_str(input_data: dict) -> dict:
    import json, os, re

    simulated_mode = input_data.get('simulated_mode', False)
    
    file_path = str(input_data.get('file_path', '')).strip()
    search = str(input_data.get('search', '')).strip()
    replace = str(input_data.get('replace', '')).strip()
    ignore_case = bool(input_data.get('ignore_case', False))

    if not file_path or not search:
        return {'status': 'error', 'replacements': 0, 'message': 'file_path and search are required.'}

    if simulated_mode:
        # Return mock result for testing
        return {'status': 'success', 'replacements': 3, 'message': ''}

    if not os.path.isfile(file_path):
        return {'status': 'error', 'replacements': 0, 'message': 'File not found.'}

    try:
        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(search, flags)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        new_content, count = pattern.subn(replace, content)
        if count:
            with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(new_content)
        return {'status': 'success', 'replacements': count, 'message': '' if count else 'No matches found.'}
    except Exception as e:
        return {'status': 'error', 'replacements': 0, 'message': str(e)}