from core.action.action_framework.registry import action


@action(
    name="stream_read",
    description="Reads a file and returns its contents with line numbers. Supports offset and limit for paginated reading of large files. You MUST use this action to read a file before using stream_edit to modify it.",
    mode="CLI",
    input_schema={
        "file_path": {
            "type": "string",
            "example": "/path/to/file.txt",
            "description": "Absolute path to the file to read. The file must exist and be readable as text."
        },
        "offset": {
            "type": "integer",
            "example": 0,
            "description": "Line number to start reading from (0-based). Use this for paginated reading of large files. Default is 0 (start from beginning).",
            "default": 0
        },
        "limit": {
            "type": "integer",
            "example": 200,
            "description": "Maximum number of lines to read. Use smaller values (50-200) for large files to avoid overwhelming context. Default is 200.",
            "default": 200
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
            "example": "File read successfully",
            "description": "Status message or error description."
        },
        "content": {
            "type": "string",
            "example": "     1\tdef hello():\n     2\t    print('Hello')\n     3\t",
            "description": "File content with line numbers in 'cat -n' format. Each line is prefixed with its 1-based line number and a tab."
        },
        "total_lines": {
            "type": "integer",
            "example": 150,
            "description": "Total number of lines in the file."
        },
        "lines_returned": {
            "type": "integer",
            "example": 150,
            "description": "Number of lines actually returned in this response."
        },
        "offset": {
            "type": "integer",
            "example": 0,
            "description": "The offset that was used for this read."
        },
        "has_more": {
            "type": "boolean",
            "example": False,
            "description": "True if there are more lines beyond what was returned. Use offset + lines_returned for the next read."
        }
    },
    test_payload={
        "file_path": "/tmp/test_file.txt",
        "offset": 0,
        "limit": 200,
        "simulated_mode": True
    }
)
def stream_read_action(input_data: dict) -> dict:
    import os

    simulated_mode = input_data.get('simulated_mode', False)

    if simulated_mode:
        return {
            'status': 'success',
            'message': 'File read successfully',
            'content': '     1\tLine 1\n     2\tLine 2\n     3\tLine 3\n',
            'total_lines': 3,
            'lines_returned': 3,
            'offset': 0,
            'has_more': False
        }

    try:
        file_path = input_data.get('file_path')
        if not file_path:
            return {
                'status': 'error',
                'message': 'file_path is required',
                'content': '',
                'total_lines': 0,
                'lines_returned': 0,
                'offset': 0,
                'has_more': False
            }

        if not os.path.isfile(file_path):
            return {
                'status': 'error',
                'message': f'File does not exist: {file_path}',
                'content': '',
                'total_lines': 0,
                'lines_returned': 0,
                'offset': 0,
                'has_more': False
            }

        try:
            offset = int(input_data.get('offset', 0))
        except (TypeError, ValueError):
            offset = 0

        try:
            limit = int(input_data.get('limit', 200))
        except (TypeError, ValueError):
            limit = 200

        if offset < 0:
            offset = 0
        if limit <= 0:
            limit = 200

        # Read the file
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # Apply offset and limit
        end_idx = min(offset + limit, total_lines)
        selected_lines = all_lines[offset:end_idx]

        # Format with line numbers (1-based, matching cat -n format)
        formatted_lines = []
        for i, line in enumerate(selected_lines, start=offset + 1):
            # Remove trailing newline for consistent formatting, then add it back
            line_content = line.rstrip('\n\r')
            # Format line number with right-alignment (6 chars) + tab + content
            formatted_lines.append(f"{i:>6}\t{line_content}")

        content = '\n'.join(formatted_lines)
        if formatted_lines:
            content += '\n'

        lines_returned = len(selected_lines)
        has_more = (offset + lines_returned) < total_lines

        return {
            'status': 'success',
            'message': 'File read successfully',
            'content': content,
            'total_lines': total_lines,
            'lines_returned': lines_returned,
            'offset': offset,
            'has_more': has_more
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'content': '',
            'total_lines': 0,
            'lines_returned': 0,
            'offset': 0,
            'has_more': False
        }
