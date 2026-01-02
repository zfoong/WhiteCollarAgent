from core.action.action_framework.registry import action

@action(
    name="stream edit",
    description="Applies a regex-based edit to a slice of lines in a text file, returning paginated original and edited segments. Similar to sed with paging.",
    mode="CLI",
    platforms=["linux"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "full_path/to/file.txt",
            "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported). This action does NOT modify the file on disk; it only returns what the edited text would look like in the specified region."
        },
        "start_line": {
            "type": "integer",
            "example": 1,
            "description": "1-based start line number (inclusive) on which to apply edits. Only lines in the range [start_line, end_line] are considered for regex substitution and segment generation. If start_line is less than 1, it is treated as 1. If start_line is larger than the total number of lines, it is clamped to the last line.",
            "default": 1
        },
        "end_line": {
            "type": "integer",
            "example": 200,
            "description": "1-based end line number (inclusive) on which to apply edits. If end_line is less than 1, it is treated as 1. If end_line is larger than the total number of lines, it is clamped to the last line. If end_line < start_line, the two values are swapped internally so the effective range is always from the smaller to the larger line number. Only lines in this final [start_line, end_line] range are edited and turned into segments.",
            "default": 200
        },
        "pattern": {
            "type": "string",
            "example": "foo",
            "description": "Regular expression pattern (Python re syntax) to search for within each line of the effective [start_line, end_line] range. This is required: if pattern is missing or empty, the action will raise an error. The regex is applied to each line independently, and only lines where the pattern matches at least once are included in the output."
        },
        "replacement": {
            "type": "string",
            "example": "bar",
            "description": "Replacement string used in the regex substitution. The action effectively performs re.sub(pattern, replacement, line_text) for each line in the effective range. If replacement is omitted, it defaults to the empty string, meaning that matched content will be removed. The output includes both the original and edited versions of each affected line so the agent can compare them."
        },
        "max_segment_chars": {
            "type": "integer",
            "example": 2000,
            "description": "Maximum number of characters allowed in each returned segment pair. After editing, each affected line (original and edited) is split into segments of at most max_segment_chars characters. Very long lines will therefore produce multiple segments for the same line, each showing a slice of the original text and the corresponding slice of the edited text. Use smaller values (e.g. 1000\u20134000) to avoid returning overly large segments when working with extremely long lines.",
            "default": 2000
        },
        "segment_range": {
            "type": "string",
            "example": "1,5",
            "description": "1-based inclusive range of segments to return after editing and splitting. After applying the regex to all lines in [start_line, end_line], the action creates segments from each edited line and numbers them from 1 to total_segments in order. segment_range must be a string of the form 'start,end'. For example: '1,5' returns the first 5 segment pairs; '6,10' returns the next 5 segment pairs, and so on. If the requested end index exceeds total_segments, it is clamped. Agents should use this field to paginate through edits, e.g. first call with '1,5', then '6,10', etc., instead of requesting all segments at once in large files.",
            "default": "1,5"
        }
    },
    output_schema={
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
            "example": [
                1,
                5
            ],
            "description": "The 1-based [start, end] segment indices that were returned (after clamping to available segments)."
        },
        "effective_line_range": {
            "type": "array",
            "example": [
                1,
                200
            ],
            "description": "The [start_line, end_line] actually used after clamping to the total number of lines."
        }
    },
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
def stream_edit_linux(input_data: dict) -> dict:
    import os, json, sys, asyncio, re

    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        return {
            'segments': ['[line 1] original: foo\n[line 1] edited  : bar'],
            'total_lines': 10,
            'total_segments': 1,
            'total_edited_lines': 1,
            'returned_segment_range': [1, 5],
            'effective_line_range': [1, 10]
        }

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        pattern = input_data.get('pattern')
        replacement = input_data.get('replacement', '')
        if not pattern:
            raise ValueError('pattern must be provided for stream edit.')

        try:
            start_line = int(input_data.get('start_line', 1))
        except Exception:
            start_line = 1
        try:
            end_line = int(input_data.get('end_line', 200))
        except Exception:
            end_line = start_line

        try:
            max_segment_chars = int(input_data.get('max_segment_chars', 2000))
        except Exception:
            max_segment_chars = 2000

        segment_range_str = input_data.get('segment_range', '1,5')
        try:
            start_seg_str, end_seg_str = [s.strip() for s in str(segment_range_str).split(',', 1)]
            start_seg = int(start_seg_str)
            end_seg = int(end_seg_str)
        except Exception:
            start_seg, end_seg = 1, 5

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
            result = {
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }
        return result

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        edited_line_count = 0

        for line_no in range(start_idx, end_idx + 1):
            original = lines[line_no - 1]
            if original is None:
                original = ''
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
            result = {
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
                'total_edited_lines': edited_line_count,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [start_idx, end_idx]
            }
        return result

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
            if o:
                o_disp = o
                if seg.get('leading'):
                    o_disp = '...' + o_disp
                if seg.get('trailing') and not o_disp.endswith('...'):
                    o_disp = o_disp + '...'
            else:
                o_disp = ''
            if e:
                e_disp = e
                if seg.get('leading'):
                    e_disp = '...' + e_disp
                if seg.get('trailing') and not e_disp.endswith('...'):
                    e_disp = e_disp + '...'
            else:
                e_disp = ''
            line_no = seg['line']
            combined = f"[line {line_no}] original: {o_disp}\n[line {line_no}] edited  : {e_disp}"
            out_segments.append(combined)

        result = {
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'total_edited_lines': edited_line_count,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

        return result

    return asyncio.run(main())

@action(
    name="stream edit",
    description="Applies a regex-based edit to a slice of lines in a text file, returning paginated original and edited segments. Similar to sed with paging.",
    mode="CLI",
    platforms=["windows"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "full_path/to/file.txt",
            "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported). This action does NOT modify the file on disk; it only returns what the edited text would look like in the specified region."
        },
        "start_line": {
            "type": "integer",
            "example": 1,
            "description": "1-based start line number (inclusive) on which to apply edits. Only lines in the range [start_line, end_line] are considered for regex substitution and segment generation. If start_line is less than 1, it is treated as 1. If start_line is larger than the total number of lines, it is clamped to the last line.",
            "default": 1
        },
        "end_line": {
            "type": "integer",
            "example": 200,
            "description": "1-based end line number (inclusive) on which to apply edits. If end_line is less than 1, it is treated as 1. If end_line is larger than the total number of lines, it is clamped to the last line. If end_line < start_line, the two values are swapped internally so the effective range is always from the smaller to the larger line number. Only lines in this final [start_line, end_line] range are edited and turned into segments.",
            "default": 200
        },
        "pattern": {
            "type": "string",
            "example": "foo",
            "description": "Regular expression pattern (Python re syntax) to search for within each line of the effective [start_line, end_line] range. This is required: if pattern is missing or empty, the action will raise an error. The regex is applied to each line independently, and only lines where the pattern matches at least once are included in the output."
        },
        "replacement": {
            "type": "string",
            "example": "bar",
            "description": "Replacement string used in the regex substitution. The action effectively performs re.sub(pattern, replacement, line_text) for each line in the effective range. If replacement is omitted, it defaults to the empty string, meaning that matched content will be removed. The output includes both the original and edited versions of each affected line so the agent can compare them."
        },
        "max_segment_chars": {
            "type": "integer",
            "example": 2000,
            "description": "Maximum number of characters allowed in each returned segment pair. After editing, each affected line (original and edited) is split into segments of at most max_segment_chars characters. Very long lines will therefore produce multiple segments for the same line, each showing a slice of the original text and the corresponding slice of the edited text. Use smaller values (e.g. 1000\u20134000) to avoid returning overly large segments when working with extremely long lines.",
            "default": 2000
        },
        "segment_range": {
            "type": "string",
            "example": "1,5",
            "description": "1-based inclusive range of segments to return after editing and splitting. After applying the regex to all lines in [start_line, end_line], the action creates segments from each edited line and numbers them from 1 to total_segments in order. segment_range must be a string of the form 'start,end'. For example: '1,5' returns the first 5 segment pairs; '6,10' returns the next 5 segment pairs, and so on. If the requested end index exceeds total_segments, it is clamped. Agents should use this field to paginate through edits, e.g. first call with '1,5', then '6,10', etc., instead of requesting all segments at once in large files.",
            "default": "1,5"
        }
    },
    output_schema={
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
            "example": [
                1,
                5
            ],
            "description": "The 1-based [start, end] segment indices that were returned (after clamping to available segments)."
        },
        "effective_line_range": {
            "type": "array",
            "example": [
                1,
                200
            ],
            "description": "The [start_line, end_line] actually used after clamping to the total number of lines."
        }
    },
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
def stream_edit_windows(input_data: dict) -> dict:
    import os, json, sys, asyncio, re

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        pattern = input_data.get('pattern')
        replacement = input_data.get('replacement', '')
        if not pattern:
            raise ValueError('pattern must be provided for stream edit.')

        try:
            start_line = int(input_data.get('start_line', 1))
        except Exception:
            start_line = 1
        try:
            end_line = int(input_data.get('end_line', 200))
        except Exception:
            end_line = start_line

        try:
            max_segment_chars = int(input_data.get('max_segment_chars', 2000))
        except Exception:
            max_segment_chars = 2000

        segment_range_str = input_data.get('segment_range', '1,5')
        try:
            start_seg_str, end_seg_str = [s.strip() for s in str(segment_range_str).split(',', 1)]
            start_seg = int(start_seg_str)
            end_seg = int(end_seg_str)
        except Exception:
            start_seg, end_seg = 1, 5

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
            result = {
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }
        return result

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        edited_line_count = 0

        for line_no in range(start_idx, end_idx + 1):
            original = lines[line_no - 1]
            if original is None:
                original = ''
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
            result = {
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
                'total_edited_lines': edited_line_count,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [start_idx, end_idx]
            }
        return result

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
            if o:
                o_disp = o
                if seg.get('leading'):
                    o_disp = '...' + o_disp
                if seg.get('trailing') and not o_disp.endswith('...'):
                    o_disp = o_disp + '...'
            else:
                o_disp = ''
            if e:
                e_disp = e
                if seg.get('leading'):
                    e_disp = '...' + e_disp
                if seg.get('trailing') and not e_disp.endswith('...'):
                    e_disp = e_disp + '...'
            else:
                e_disp = ''
            line_no = seg['line']
            combined = f"[line {line_no}] original: {o_disp}\n[line {line_no}] edited  : {e_disp}"
            out_segments.append(combined)

        result = {
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'total_edited_lines': edited_line_count,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

        return result

    return asyncio.run(main())

@action(
    name="stream edit",
    description="Applies a regex-based edit to a slice of lines in a text file, returning paginated original and edited segments. Similar to sed with paging.",
    platforms=["darwin"],
    mode="CLI",
    input_schema={
        "input_file": {
            "type": "string",
            "example": "full_path/to/file.txt",
            "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported). This action does NOT modify the file on disk; it only returns what the edited text would look like in the specified region."
        },
        "start_line": {
            "type": "integer",
            "example": 1,
            "description": "1-based start line number (inclusive) on which to apply edits. Only lines in the range [start_line, end_line] are considered for regex substitution and segment generation. If start_line is less than 1, it is treated as 1. If start_line is larger than the total number of lines, it is clamped to the last line.",
            "default": 1
        },
        "end_line": {
            "type": "integer",
            "example": 200,
            "description": "1-based end line number (inclusive) on which to apply edits. If end_line is less than 1, it is treated as 1. If end_line is larger than the total number of lines, it is clamped to the last line. If end_line < start_line, the two values are swapped internally so the effective range is always from the smaller to the larger line number. Only lines in this final [start_line, end_line] range are edited and turned into segments.",
            "default": 200
        },
        "pattern": {
            "type": "string",
            "example": "foo",
            "description": "Regular expression pattern (Python re syntax) to search for within each line of the effective [start_line, end_line] range. This is required: if pattern is missing or empty, the action will raise an error. The regex is applied to each line independently, and only lines where the pattern matches at least once are included in the output."
        },
        "replacement": {
            "type": "string",
            "example": "bar",
            "description": "Replacement string used in the regex substitution. The action effectively performs re.sub(pattern, replacement, line_text) for each line in the effective range. If replacement is omitted, it defaults to the empty string, meaning that matched content will be removed. The output includes both the original and edited versions of each affected line so the agent can compare them."
        },
        "max_segment_chars": {
            "type": "integer",
            "example": 2000,
            "description": "Maximum number of characters allowed in each returned segment pair. After editing, each affected line (original and edited) is split into segments of at most max_segment_chars characters. Very long lines will therefore produce multiple segments for the same line, each showing a slice of the original text and the corresponding slice of the edited text. Use smaller values (e.g. 1000\u20134000) to avoid returning overly large segments when working with extremely long lines.",
            "default": 2000
        },
        "segment_range": {
            "type": "string",
            "example": "1,5",
            "description": "1-based inclusive range of segments to return after editing and splitting. After applying the regex to all lines in [start_line, end_line], the action creates segments from each edited line and numbers them from 1 to total_segments in order. segment_range must be a string of the form 'start,end'. For example: '1,5' returns the first 5 segment pairs; '6,10' returns the next 5 segment pairs, and so on. If the requested end index exceeds total_segments, it is clamped. Agents should use this field to paginate through edits, e.g. first call with '1,5', then '6,10', etc., instead of requesting all segments at once in large files.",
            "default": "1,5"
        }
    },
    output_schema={
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
            "example": [
                1,
                5
            ],
            "description": "The 1-based [start, end] segment indices that were returned (after clamping to available segments)."
        },
        "effective_line_range": {
            "type": "array",
            "example": [
                1,
                200
            ],
            "description": "The [start_line, end_line] actually used after clamping to the total number of lines."
        }
    },
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
def stream_edit_darwin(input_data: dict) -> dict:
    import os, json, sys, asyncio, re

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        pattern = input_data.get('pattern')
        replacement = input_data.get('replacement', '')
        if not pattern:
            raise ValueError('pattern must be provided for stream edit.')

        try:
            start_line = int(input_data.get('start_line', 1))
        except Exception:
            start_line = 1
        try:
            end_line = int(input_data.get('end_line', 200))
        except Exception:
            end_line = start_line

        try:
            max_segment_chars = int(input_data.get('max_segment_chars', 2000))
        except Exception:
            max_segment_chars = 2000

        segment_range_str = input_data.get('segment_range', '1,5')
        try:
            start_seg_str, end_seg_str = [s.strip() for s in str(segment_range_str).split(',', 1)]
            start_seg = int(start_seg_str)
            end_seg = int(end_seg_str)
        except Exception:
            start_seg, end_seg = 1, 5

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
            result = {
                'segments': [],
                'total_lines': 0,
                'total_segments': 0,
                'total_edited_lines': 0,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }
        return result

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        edited_line_count = 0

        for line_no in range(start_idx, end_idx + 1):
            original = lines[line_no - 1]
            if original is None:
                original = ''
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
            result = {
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
                'total_edited_lines': edited_line_count,
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [start_idx, end_idx]
            }
        return result

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
            if o:
                o_disp = o
                if seg.get('leading'):
                    o_disp = '...' + o_disp
                if seg.get('trailing') and not o_disp.endswith('...'):
                    o_disp = o_disp + '...'
            else:
                o_disp = ''
            if e:
                e_disp = e
                if seg.get('leading'):
                    e_disp = '...' + e_disp
                if seg.get('trailing') and not e_disp.endswith('...'):
                    e_disp = e_disp + '...'
            else:
                e_disp = ''
            line_no = seg['line']
            combined = f"[line {line_no}] original: {o_disp}\n[line {line_no}] edited  : {e_disp}"
            out_segments.append(combined)

        result = {
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'total_edited_lines': edited_line_count,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

        return result

    return asyncio.run(main())