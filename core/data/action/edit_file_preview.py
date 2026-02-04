from core.action.action_framework.registry import action

# Common output schema for all platforms
_OUTPUT_SCHEMA = {
    "status": {
        "type": "string",
        "example": "success",
        "description": "'success' or 'error'."
    },
    "message": {
        "type": "string",
        "example": "Preview generated successfully",
        "description": "Status message or error description."
    },
    "segments": {
        "type": "array",
        "example": [
            "[line 10] original: The quick brown fox...\n[line 10] edited  : The fast brown fox...",
            "[line 10] original: ...jumps over the lazy dog\n[line 10] edited  : ...leaps over the lazy dog"
        ],
        "description": "List of formatted segments for the requested range. Each segment shows both original and edited text for that slice of a line."
    },
    "total_lines": {
        "type": "integer",
        "example": 1234,
        "description": "Total number of lines in the file."
    },
    "total_segments": {
        "type": "integer",
        "example": 42,
        "description": "Total number of segments produced from the effective line range given max_segment_chars."
    },
    "total_edited_lines": {
        "type": "integer",
        "example": 7,
        "description": "Number of lines in the effective line range that were actually changed by the edit."
    },
    "returned_segment_range": {
        "type": "array",
        "example": [1, 5],
        "description": "The 1-based [start, end] segment indices that were returned (after clamping to available segments)."
    },
    "effective_line_range": {
        "type": "array",
        "example": [1, 200],
        "description": "The [start_line, end_line] actually used after clamping to the total number of lines."
    }
}

# Common input schema for all platforms
_INPUT_SCHEMA = {
    "input_file": {
        "type": "string",
        "example": "full_path/to/file.txt",
        "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported). This action does NOT modify the file on disk; it only returns what the edited text would look like in the specified region."
    },
    "start_line": {
        "type": "integer",
        "example": 1,
        "description": "1-based start line number (inclusive) on which to apply edits.",
        "default": 1
    },
    "end_line": {
        "type": "integer",
        "example": 200,
        "description": "1-based end line number (inclusive) on which to apply edits.",
        "default": 200
    },
    "pattern": {
        "type": "string",
        "example": "foo",
        "description": "Regular expression pattern (Python re syntax) to search for within each line."
    },
    "replacement": {
        "type": "string",
        "example": "bar",
        "description": "Replacement string used in the regex substitution."
    },
    "max_segment_chars": {
        "type": "integer",
        "example": 2000,
        "description": "Maximum number of characters allowed in each returned segment pair.",
        "default": 2000
    },
    "segment_range": {
        "type": "string",
        "example": "1,5",
        "description": "1-based inclusive range of segments to return after editing and splitting.",
        "default": "1,5"
    }
}


def _edit_file_preview_impl(input_data: dict) -> dict:
    """Common implementation for edit_file_preview across all platforms."""
    import os
    import re

    simulated_mode = input_data.get('simulated_mode', False)

    if simulated_mode:
        return {
            'status': 'success',
            'message': 'Preview generated successfully',
            'segments': ['[line 1] original: foo\n[line 1] edited  : bar'],
            'total_lines': 10,
            'total_segments': 1,
            'total_edited_lines': 1,
            'returned_segment_range': [1, 5],
            'effective_line_range': [1, 10]
        }

    try:
        input_file = input_data.get('input_file')
        if not input_file:
            return {
                'status': 'error',
                'message': 'input_file is required',
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [0, 0],
                'effective_line_range': [0, 0]
            }

        if not os.path.isfile(input_file):
            return {
                'status': 'error',
                'message': f'Input file does not exist: {input_file}',
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [0, 0],
                'effective_line_range': [0, 0]
            }

        pattern = input_data.get('pattern')
        replacement = input_data.get('replacement', '')
        if not pattern:
            return {
                'status': 'error',
                'message': 'pattern is required',
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [0, 0],
                'effective_line_range': [0, 0]
            }

        try:
            start_line = int(input_data.get('start_line', 1))
        except (TypeError, ValueError):
            start_line = 1
        try:
            end_line = int(input_data.get('end_line', 200))
        except (TypeError, ValueError):
            end_line = start_line

        try:
            max_segment_chars = int(input_data.get('max_segment_chars', 2000))
        except (TypeError, ValueError):
            max_segment_chars = 2000

        segment_range_str = input_data.get('segment_range', '1,5')
        try:
            start_seg_str, end_seg_str = [s.strip() for s in str(segment_range_str).split(',', 1)]
            start_seg = int(start_seg_str)
            end_seg = int(end_seg_str)
        except Exception:
            start_seg, end_seg = 1, 5

        # Normalize ranges
        if start_line < 1:
            start_line = 1
        if end_line < 1:
            end_line = 1
        if end_line < start_line:
            start_line, end_line = end_line, start_line
        if max_segment_chars <= 0:
            max_segment_chars = 2000
        if start_seg < 1:
            start_seg = 1
        if end_seg < 1:
            end_seg = 1
        if end_seg < start_seg:
            start_seg, end_seg = end_seg, start_seg

        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.read().splitlines()

        total_lines = len(lines)

        if total_lines == 0:
            return {
                'status': 'success',
                'message': 'File is empty',
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        edited_line_count = 0

        for line_no in range(start_idx, end_idx + 1):
            original = lines[line_no - 1] or ''
            edited = re.sub(pattern, replacement, original)
            if edited == original:
                continue
            edited_line_count += 1
            max_len = max(len(original), len(edited))
            if max_len == 0:
                continue
            pos = 0
            while pos < max_len:
                end_pos = min(pos + max_segment_chars, max_len)
                orig_chunk = original[pos:end_pos]
                edit_chunk = edited[pos:end_pos]
                leading = pos > 0
                trailing_orig = end_pos < len(original)
                trailing_edit = end_pos < len(edited)
                trailing = trailing_orig or trailing_edit
                all_segments.append({
                    'line': line_no,
                    'orig': orig_chunk,
                    'edit': edit_chunk,
                    'leading': leading,
                    'trailing': trailing
                })
                pos = end_pos

        total_segments = len(all_segments)

        if total_segments == 0:
            return {
                'status': 'success',
                'message': 'No lines matched the pattern',
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
                'total_edited_lines': edited_line_count,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [start_idx, end_idx]
            }

        start_seg_clamped = max(1, min(start_seg, total_segments))
        end_seg_clamped = max(1, min(end_seg, total_segments))
        if end_seg_clamped < start_seg_clamped:
            start_seg_clamped, end_seg_clamped = end_seg_clamped, start_seg_clamped

        selected = all_segments[start_seg_clamped - 1:end_seg_clamped]

        def clean(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        out_segments = []
        for seg in selected:
            o = clean(seg['orig'])
            e = clean(seg['edit'])
            o_disp = ''
            e_disp = ''
            if o:
                o_disp = o
                if seg.get('leading'):
                    o_disp = '...' + o_disp
                if seg.get('trailing') and not o_disp.endswith('...'):
                    o_disp = o_disp + '...'
            if e:
                e_disp = e
                if seg.get('leading'):
                    e_disp = '...' + e_disp
                if seg.get('trailing') and not e_disp.endswith('...'):
                    e_disp = e_disp + '...'
            line_no = seg['line']
            combined = f"[line {line_no}] original: {o_disp}\n[line {line_no}] edited  : {e_disp}"
            out_segments.append(combined)

        return {
            'status': 'success',
            'message': f'Preview generated: {edited_line_count} line(s) would be edited',
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'total_edited_lines': edited_line_count,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'segments': [],
            'total_lines': 0,
            'total_segments': 0,
            'total_edited_lines': 0,
            'returned_segment_range': [0, 0],
            'effective_line_range': [0, 0]
        }


@action(
    name="edit_file_preview",
    description="Applies a regex-based edit to a slice of lines in a text file, returning paginated original and edited segments. Similar to sed with paging. Does NOT modify the file.",
    mode="CLI",
    platforms=["linux"],
    input_schema=_INPUT_SCHEMA,
    output_schema=_OUTPUT_SCHEMA,
    test_payload={
        "input_file": "/path/to/file.txt",
        "start_line": 1,
        "end_line": 200,
        "pattern": "foo",
        "replacement": "bar",
        "max_segment_chars": 2000,
        "segment_range": "1,5",
        "simulated_mode": True
    }
)
def edit_file_preview_linux(input_data: dict) -> dict:
    return _edit_file_preview_impl(input_data)


@action(
    name="edit_file_preview",
    description="Applies a regex-based edit to a slice of lines in a text file, returning paginated original and edited segments. Similar to sed with paging. Does NOT modify the file.",
    mode="CLI",
    platforms=["windows"],
    input_schema=_INPUT_SCHEMA,
    output_schema=_OUTPUT_SCHEMA,
    test_payload={
        "input_file": "/path/to/file.txt",
        "start_line": 1,
        "end_line": 200,
        "pattern": "foo",
        "replacement": "bar",
        "max_segment_chars": 2000,
        "segment_range": "1,5",
        "simulated_mode": True
    }
)
def edit_file_preview_windows(input_data: dict) -> dict:
    return _edit_file_preview_impl(input_data)


@action(
    name="edit_file_preview",
    description="Applies a regex-based edit to a slice of lines in a text file, returning paginated original and edited segments. Similar to sed with paging. Does NOT modify the file.",
    mode="CLI",
    platforms=["darwin"],
    input_schema=_INPUT_SCHEMA,
    output_schema=_OUTPUT_SCHEMA,
    test_payload={
        "input_file": "/path/to/file.txt",
        "start_line": 1,
        "end_line": 200,
        "pattern": "foo",
        "replacement": "bar",
        "max_segment_chars": 2000,
        "segment_range": "1,5",
        "simulated_mode": True
    }
)
def edit_file_preview_darwin(input_data: dict) -> dict:
    return _edit_file_preview_impl(input_data)
