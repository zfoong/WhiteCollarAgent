from core.action.action_framework.registry import action

@action(
    name="stream read",
    description="Reads a text file and returns a paginated slice of lines and segments, similar to `sed -n 'start,endp'` but safe for very long lines.",
    mode="CLI",
    platforms=["linux"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "full_path/to/file.txt",
            "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported)."
        },
        "start_line": {
            "type": "integer",
            "example": 1,
            "description": "1-based start line number (inclusive) for the portion of the file you want to read. If start_line is less than 1, it will be treated as 1. If start_line is larger than the total number of lines in the file, it will be clamped to the last line. Only lines in the range [start_line, end_line] are considered when building segments.",
            "default": 1
        },
        "end_line": {
            "type": "integer",
            "example": 200,
            "description": "1-based end line number (inclusive) for the portion of the file you want to read. If end_line is less than 1, it will be treated as 1. If end_line is larger than the total number of lines, it will be clamped to the last line. If end_line < start_line, the two values are swapped internally so the effective range is always from the smaller to the larger line number. Only lines in the final [start_line, end_line] range are used to build segments.",
            "default": 200
        },
        "max_segment_chars": {
            "type": "integer",
            "example": 2000,
            "description": "Maximum number of characters allowed in each returned segment. Lines are first filtered by [start_line, end_line], then each line in that range is split into one or more segments of at most max_segment_chars characters. If a line is longer than max_segment_chars, it will be broken up into multiple segments for that same line, with leading/trailing ellipses added to indicate continuation. Use a smaller value (e.g. 1000\u20132000) to avoid overwhelming the LLM context when lines are extremely long.",
            "default": 2000
        },
        "segment_range": {
            "type": "string",
            "example": "1,5",
            "description": "1-based inclusive range of segments to return after splitting the selected lines. The tool first reads lines in [start_line, end_line], splits each line into segments of at most max_segment_chars characters, and numbers these segments from 1 to total_segments in order. segment_range must be a string of the form 'start,end'. For example: '1,5' returns the first 5 segments, '6,10' returns the next 5 segments, and so on. If the requested end index is larger than total_segments, it is clamped to total_segments. Use this to paginate through a large file: first call with '1,5', then inspect total_segments from the output and call again with '6,10', '11,15', etc. If you want to effectively disable pagination for small files, you can set a large range such as '1,1000'.",
            "default": "1,5"
        }
    },
    output_schema={
        "segments": {
            "type": "array",
            "example": [
                "[line 1] first part of a long line...",
                "[line 1] ...second part of the same long line...",
                "[line 2] a shorter line"
            ],
            "description": "List of formatted segments for the requested range. Long lines may appear as multiple segments with ellipses."
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
        "input_file": "/tmp/test_file.txt",
        "start_line": 1,
        "end_line": 10,
        "max_segment_chars": 2000,
        "segment_range": "1,5",
        "simulated_mode": True
    }
)
def stream_read_linux(input_data: dict) -> dict:
    import os, json, sys, asyncio, re

    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        return {
            'segments': ['[line 1] Test line 1', '[line 2] Test line 2'],
            'total_lines': 10,
            'total_segments': 5,
            'returned_segment_range': [1, 5],
            'effective_line_range': [1, 10]
        }

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

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
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }
            return result

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        for line_no in range(start_idx, end_idx + 1):
            text = lines[line_no - 1]
            if text is None:
                text = ''
            s = text
            length = len(s)
            if length == 0:
                all_segments.append({'line': line_no, 'text': '', 'leading': False, 'trailing': False})
                continue
            pos = 0
            while pos < length:
                end_pos = min(pos + max_segment_chars, length)
                chunk = s[pos:end_pos]
                leading = pos > 0
                trailing = end_pos < length
                all_segments.append({'line': line_no, 'text': chunk, 'leading': leading, 'trailing': trailing})
                pos = end_pos

        total_segments = len(all_segments)
        if total_segments == 0:
            result = {
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
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
            t = clean(seg['text'])
            if not t:
                display = ''
            else:
                display = t
                if seg.get('leading'):
                    display = '...' + display
                if seg.get('trailing'):
                    if not display.endswith('...'):
                        display = display + '...'
            line_no = seg['line']
            out_segments.append(f"[line {line_no}] {display}")

        result = {
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

        return result

    return asyncio.run(main())

@action(
    name="stream read",
    description="Reads a text file and returns a paginated slice of lines and segments, similar to `sed -n 'start,endp'` but safe for very long lines.",
    mode="CLI",
    platforms=["windows"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "full_path/to/file.txt",
            "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported)."
        },
        "start_line": {
            "type": "integer",
            "example": 1,
            "description": "1-based start line number (inclusive) for the portion of the file you want to read. If start_line is less than 1, it will be treated as 1. If start_line is larger than the total number of lines in the file, it will be clamped to the last line. Only lines in the range [start_line, end_line] are considered when building segments.",
            "default": 1
        },
        "end_line": {
            "type": "integer",
            "example": 200,
            "description": "1-based end line number (inclusive) for the portion of the file you want to read. If end_line is less than 1, it will be treated as 1. If end_line is larger than the total number of lines, it will be clamped to the last line. If end_line < start_line, the two values are swapped internally so the effective range is always from the smaller to the larger line number. Only lines in the final [start_line, end_line] range are used to build segments.",
            "default": 200
        },
        "max_segment_chars": {
            "type": "integer",
            "example": 2000,
            "description": "Maximum number of characters allowed in each returned segment. Lines are first filtered by [start_line, end_line], then each line in that range is split into one or more segments of at most max_segment_chars characters. If a line is longer than max_segment_chars, it will be broken up into multiple segments for that same line, with leading/trailing ellipses added to indicate continuation. Use a smaller value (e.g. 1000\u20132000) to avoid overwhelming the LLM context when lines are extremely long.",
            "default": 2000
        },
        "segment_range": {
            "type": "string",
            "example": "1,5",
            "description": "1-based inclusive range of segments to return after splitting the selected lines. The tool first reads lines in [start_line, end_line], splits each line into segments of at most max_segment_chars characters, and numbers these segments from 1 to total_segments in order. segment_range must be a string of the form 'start,end'. For example: '1,5' returns the first 5 segments, '6,10' returns the next 5 segments, and so on. If the requested end index is larger than total_segments, it is clamped to total_segments. Use this to paginate through a large file: first call with '1,5', then inspect total_segments from the output and call again with '6,10', '11,15', etc. If you want to effectively disable pagination for small files, you can set a large range such as '1,1000'.",
            "default": "1,5"
        }
    },
    output_schema={
        "segments": {
            "type": "array",
            "example": [
                "[line 1] first part of a long line...",
                "[line 1] ...second part of the same long line...",
                "[line 2] a shorter line"
            ],
            "description": "List of formatted segments for the requested range. Long lines may appear as multiple segments with ellipses."
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
        "input_file": "/tmp/test_file.txt",
        "start_line": 1,
        "end_line": 10,
        "max_segment_chars": 2000,
        "segment_range": "1,5",
        "simulated_mode": True
    }
)
def stream_read_windows(input_data: dict) -> dict:
    import os, json, sys, asyncio, re

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

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
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }
            return result

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        for line_no in range(start_idx, end_idx + 1):
            text = lines[line_no - 1]
            if text is None:
                text = ''
            s = text
            length = len(s)
            if length == 0:
                all_segments.append({'line': line_no, 'text': '', 'leading': False, 'trailing': False})
                continue
            pos = 0
            while pos < length:
                end_pos = min(pos + max_segment_chars, length)
                chunk = s[pos:end_pos]
                leading = pos > 0
                trailing = end_pos < length
                all_segments.append({'line': line_no, 'text': chunk, 'leading': leading, 'trailing': trailing})
                pos = end_pos

        total_segments = len(all_segments)
        if total_segments == 0:
            result = {
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
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
            t = clean(seg['text'])
            if not t:
                display = ''
            else:
                display = t
                if seg.get('leading'):
                    display = '...' + display
                if seg.get('trailing'):
                    if not display.endswith('...'):
                        display = display + '...'
            line_no = seg['line']
            out_segments.append(f"[line {line_no}] {display}")

        result = {
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

        return result

    return asyncio.run(main())

@action(
    name="stream read",
    description="Reads a text file and returns a paginated slice of lines and segments, similar to `sed -n 'start,endp'` but safe for very long lines.",
    mode="CLI",
    platforms=["darwin"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "full_path/to/file.txt",
            "description": "Absolute path to the input text file to read. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported)."
        },
        "start_line": {
            "type": "integer",
            "example": 1,
            "description": "1-based start line number (inclusive) for the portion of the file you want to read. If start_line is less than 1, it will be treated as 1. If start_line is larger than the total number of lines in the file, it will be clamped to the last line. Only lines in the range [start_line, end_line] are considered when building segments.",
            "default": 1
        },
        "end_line": {
            "type": "integer",
            "example": 200,
            "description": "1-based end line number (inclusive) for the portion of the file you want to read. If end_line is less than 1, it will be treated as 1. If end_line is larger than the total number of lines, it will be clamped to the last line. If end_line < start_line, the two values are swapped internally so the effective range is always from the smaller to the larger line number. Only lines in the final [start_line, end_line] range are used to build segments.",
            "default": 200
        },
        "max_segment_chars": {
            "type": "integer",
            "example": 2000,
            "description": "Maximum number of characters allowed in each returned segment. Lines are first filtered by [start_line, end_line], then each line in that range is split into one or more segments of at most max_segment_chars characters. If a line is longer than max_segment_chars, it will be broken up into multiple segments for that same line, with leading/trailing ellipses added to indicate continuation. Use a smaller value (e.g. 1000\u20132000) to avoid overwhelming the LLM context when lines are extremely long.",
            "default": 2000
        },
        "segment_range": {
            "type": "string",
            "example": "1,5",
            "description": "1-based inclusive range of segments to return after splitting the selected lines. The tool first reads lines in [start_line, end_line], splits each line into segments of at most max_segment_chars characters, and numbers these segments from 1 to total_segments in order. segment_range must be a string of the form 'start,end'. For example: '1,5' returns the first 5 segments, '6,10' returns the next 5 segments, and so on. If the requested end index is larger than total_segments, it is clamped to total_segments. Use this to paginate through a large file: first call with '1,5', then inspect total_segments from the output and call again with '6,10', '11,15', etc. If you want to effectively disable pagination for small files, you can set a large range such as '1,1000'.",
            "default": "1,5"
        }
    },
    output_schema={
        "segments": {
            "type": "array",
            "example": [
                "[line 1] first part of a long line...",
                "[line 1] ...second part of the same long line...",
                "[line 2] a shorter line"
            ],
            "description": "List of formatted segments for the requested range. Long lines may appear as multiple segments with ellipses."
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
        "input_file": "/tmp/test_file.txt",
        "start_line": 1,
        "end_line": 10,
        "max_segment_chars": 2000,
        "segment_range": "1,5",
        "simulated_mode": True
    }
)
def stream_read_darwin(input_data: dict) -> dict:
    import os, json, sys, asyncio, re

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

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
                'returned_segment_range': [start_seg, end_seg],
                'effective_line_range': [0, 0]
            }
            return result

        start_idx = max(1, min(start_line, total_lines))
        end_idx = max(1, min(end_line, total_lines))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        all_segments = []
        for line_no in range(start_idx, end_idx + 1):
            text = lines[line_no - 1]
            if text is None:
                text = ''
            s = text
            length = len(s)
            if length == 0:
                all_segments.append({'line': line_no, 'text': '', 'leading': False, 'trailing': False})
                continue
            pos = 0
            while pos < length:
                end_pos = min(pos + max_segment_chars, length)
                chunk = s[pos:end_pos]
                leading = pos > 0
                trailing = end_pos < length
                all_segments.append({'line': line_no, 'text': chunk, 'leading': leading, 'trailing': trailing})
                pos = end_pos

        total_segments = len(all_segments)
        if total_segments == 0:
            result = {
                'segments': [],
                'total_lines': total_lines,
                'total_segments': 0,
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
            t = clean(seg['text'])
            if not t:
                display = ''
            else:
                display = t
                if seg.get('leading'):
                    display = '...' + display
                if seg.get('trailing'):
                    if not display.endswith('...'):
                        display = display + '...'
            line_no = seg['line']
            out_segments.append(f"[line {line_no}] {display}")

        result = {
            'segments': out_segments,
            'total_lines': total_lines,
            'total_segments': total_segments,
            'returned_segment_range': [start_seg_clamped, end_seg_clamped],
            'effective_line_range': [start_idx, end_idx]
        }

        return result

    return asyncio.run(main())