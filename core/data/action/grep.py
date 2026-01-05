from core.action.action_framework.registry import action

@action(
    name="grep",
    description="Searches a text file for keywords and returns matching chunks with pagination.",
    mode="CLI",
    platforms=["linux"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.txt",
            "description": "Absolute to the input text file to search. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported)."
        },
        "keywords": {
            "type": "array",
            "example": [
                "Mt. Fuji",
                "visibility"
            ],
            "description": "List of plain-text keywords to search for inside the file. All keywords are OR-ed together: a chunk is considered a match if it contains at least one of the keywords (case-insensitive). An empty list is not allowed.",
            "default": []
        },
        "chunk_size": {
            "type": "integer",
            "example": 300,
            "description": "Approximate number of words per chunk. The file content is first tokenized into words, then grouped into chunks of about chunk_size words. Larger values create bigger chunks (more context per hit but more tokens); smaller values create more, smaller chunks.",
            "default": 300
        },
        "overlap": {
            "type": "integer",
            "example": 50,
            "description": "Number of overlapping words between consecutive chunks. For example, with chunk_size=300 and overlap=50, the first chunk is words 1\u2013300, the second chunk is words 251\u2013550, etc.",
            "default": 50
        },
        "chunk_start": {
            "type": "integer",
            "example": 1,
            "description": "1-based start index of the matched chunk range to return (inclusive). If 0 or negative is provided, it is treated as 1.",
            "default": 1
        },
        "chunk_end": {
            "type": "integer",
            "example": 5,
            "description": "1-based end index of the matched chunk range to return (inclusive). If smaller than chunk_start, the two values will be swapped. If larger than the total number of matches, it will be clamped.",
            "default": 5
        }
    },
    output_schema={
        "chunks": {
            "type": "array",
            "example": [
                "[line 275] ...some text chunk...",
                "[line 937] ...another text chunk..."
            ],
            "description": "List of formatted chunks for the requested range."
        },
        "total_matches": {
            "type": "integer",
            "example": 23,
            "description": "Total number of matched chunks available."
        },
        "returned_range": {
            "type": "array",
            "example": [
                1,
                5
            ],
            "description": "The 1-based [start, end] chunk indices that were requested (clamped to available matches)."
        }
    },
    test_payload={
        "input_file": "/path/to/input.txt",
        "keywords": ["Mt. Fuji", "visibility"],
        "chunk_size": 300,
        "overlap": 50,
        "chunk_start": 1,
        "chunk_end": 5,
        "simulated_mode": True
    }
)
def grep_linux(input_data: dict) -> dict:
    import os, json, re, sys, asyncio

    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        return {
            'chunks': ['[line 10] Test chunk with keyword'],
            'total_matches': 1,
            'returned_range': [1, 5]
        }

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        keywords = input_data.get('keywords') or []
        if not keywords:
            raise ValueError('keywords must be a non-empty array.')

        try:
            chunk_size = int(input_data.get('chunk_size', 300))
        except Exception:
            chunk_size = 300
        try:
            overlap = int(input_data.get('overlap', 50))
        except Exception:
            overlap = 50
        try:
            start_idx = int(input_data.get('chunk_start', 1))
        except Exception:
            start_idx = 1
        try:
            end_idx = int(input_data.get('chunk_end', 5))
        except Exception:
            end_idx = 5

        if chunk_size <= 0:
            chunk_size = 300
        if overlap < 0:
            overlap = 0

        if start_idx < 1:
            start_idx = 1
        if end_idx < 1:
            end_idx = 1
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        segments = chunk_text(content, chunk_size=chunk_size, overlap=overlap)

        if not segments:
            result = {'chunks': [], 'total_matches': 0, 'returned_range': [start_idx, end_idx]}
            return result

        pattern = re.compile('(' + '|'.join(re.escape(k) for k in keywords) + ')', re.I)
        matched_segments = [s for s in segments if pattern.search(s['text'])]

        total_matches = len(matched_segments)
        if total_matches == 0:
            result = {'chunks': [], 'total_matches': 0, 'returned_range': [start_idx, end_idx]}
            return result

        start_idx_clamped = max(1, min(start_idx, total_matches))
        end_idx_clamped = max(1, min(end_idx, total_matches))
        if end_idx_clamped < start_idx_clamped:
            start_idx_clamped, end_idx_clamped = end_idx_clamped, start_idx_clamped

        start_zero = start_idx_clamped - 1
        end_zero_excl = end_idx_clamped

        page_segments = matched_segments[start_zero:end_zero_excl]

        def clean_text(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        formatted_chunks = []
        for seg in page_segments:
            text_clean = clean_text(seg['text'])
            if not text_clean:
                continue
            display_text = text_clean
            if seg.get('has_leading_ellipsis'):
                display_text = '...' + display_text
            if seg.get('has_trailing_ellipsis'):
                if not display_text.endswith('...'):
                    display_text = display_text + '...'
            line_no = int(seg.get('start_word_index', 1))
            para = f"[line {line_no}] {display_text}"
            formatted_chunks.append(para)

        result = {
            'status': 'success',
            'chunks': formatted_chunks,
            'total_matches': total_matches,
            'returned_range': [start_idx_clamped, end_idx_clamped]
        }
        return result


    def chunk_text(text, chunk_size=300, overlap=50):
        import re as _re
        words = _re.findall(r'\S+', text or '')
        if not words:
            return []
        if chunk_size <= 0:
            chunk_size = 300
        if overlap < 0:
            overlap = 0
        step = max(1, chunk_size - overlap)
        n = len(words)
        segments = []
        for start in range(0, n, step):
            end = min(start + chunk_size, n)
            chunk_words = words[start:end]
            if not chunk_words:
                break
            chunk_text_val = ' '.join(chunk_words).strip()
            if not chunk_text_val:
                continue
            has_leading = start > 0
            has_trailing = end < n
            segments.append({
                'text': chunk_text_val,
                'start_word_index': start + 1,
                'has_leading_ellipsis': bool(has_leading),
                'has_trailing_ellipsis': bool(has_trailing)
            })
        return segments

    return asyncio.run(main())

@action(
    name="grep",
    description="Searches a text file for keywords and returns matching chunks with pagination.",
    mode="CLI",
    platforms=["windows"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.txt",
            "description": "Absolute to the input text file to search. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported)."
        },
        "keywords": {
            "type": "array",
            "example": [
                "Mt. Fuji",
                "visibility"
            ],
            "description": "List of plain-text keywords to search for inside the file. All keywords are OR-ed together: a chunk is considered a match if it contains at least one of the keywords (case-insensitive). An empty list is not allowed.",
            "default": []
        },
        "chunk_size": {
            "type": "integer",
            "example": 300,
            "description": "Approximate number of words per chunk. The file content is first tokenized into words, then grouped into chunks of about chunk_size words. Larger values create bigger chunks (more context per hit but more tokens); smaller values create more, smaller chunks.",
            "default": 300
        },
        "overlap": {
            "type": "integer",
            "example": 50,
            "description": "Number of overlapping words between consecutive chunks. For example, with chunk_size=300 and overlap=50, the first chunk is words 1\u2013300, the second chunk is words 251\u2013550, etc.",
            "default": 50
        },
        "chunk_start": {
            "type": "integer",
            "example": 1,
            "description": "1-based start index of the matched chunk range to return (inclusive). If 0 or negative is provided, it is treated as 1.",
            "default": 1
        },
        "chunk_end": {
            "type": "integer",
            "example": 5,
            "description": "1-based end index of the matched chunk range to return (inclusive). If smaller than chunk_start, the two values will be swapped. If larger than the total number of matches, it will be clamped.",
            "default": 5
        }
    },
    output_schema={
        "chunks": {
            "type": "array",
            "example": [
                "[line 275] ...some text chunk...",
                "[line 937] ...another text chunk..."
            ],
            "description": "List of formatted chunks for the requested range."
        },
        "total_matches": {
            "type": "integer",
            "example": 23,
            "description": "Total number of matched chunks available."
        },
        "returned_range": {
            "type": "array",
            "example": [
                1,
                5
            ],
            "description": "The 1-based [start, end] chunk indices that were requested (clamped to available matches)."
        }
    },
    test_payload={
        "input_file": "/path/to/input.txt",
        "keywords": ["Mt. Fuji", "visibility"],
        "chunk_size": 300,
        "overlap": 50,
        "chunk_start": 1,
        "chunk_end": 5,
        "simulated_mode": True
    }
)
def grep_windows(input_data: dict) -> dict:
    import os, json, re, sys, asyncio

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        keywords = input_data.get('keywords') or []
        if not keywords:
            raise ValueError('keywords must be a non-empty array.')

        try:
            chunk_size = int(input_data.get('chunk_size', 300))
        except Exception:
            chunk_size = 300
        try:
            overlap = int(input_data.get('overlap', 50))
        except Exception:
            overlap = 50
        try:
            start_idx = int(input_data.get('chunk_start', 1))
        except Exception:
            start_idx = 1
        try:
            end_idx = int(input_data.get('chunk_end', 5))
        except Exception:
            end_idx = 5

        if chunk_size <= 0:
            chunk_size = 300
        if overlap < 0:
            overlap = 0

        if start_idx < 1:
            start_idx = 1
        if end_idx < 1:
            end_idx = 1
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        segments = chunk_text(content, chunk_size=chunk_size, overlap=overlap)

        if not segments:
            result = {'chunks': [], 'total_matches': 0, 'returned_range': [start_idx, end_idx]}
            return result

        pattern = re.compile('(' + '|'.join(re.escape(k) for k in keywords) + ')', re.I)
        matched_segments = [s for s in segments if pattern.search(s['text'])]

        total_matches = len(matched_segments)
        if total_matches == 0:
            result = {'chunks': [], 'total_matches': 0, 'returned_range': [start_idx, end_idx]}
            return result

        start_idx_clamped = max(1, min(start_idx, total_matches))
        end_idx_clamped = max(1, min(end_idx, total_matches))
        if end_idx_clamped < start_idx_clamped:
            start_idx_clamped, end_idx_clamped = end_idx_clamped, start_idx_clamped

        start_zero = start_idx_clamped - 1
        end_zero_excl = end_idx_clamped

        page_segments = matched_segments[start_zero:end_zero_excl]

        def clean_text(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        formatted_chunks = []
        for seg in page_segments:
            text_clean = clean_text(seg['text'])
            if not text_clean:
                continue
            display_text = text_clean
            if seg.get('has_leading_ellipsis'):
                display_text = '...' + display_text
            if seg.get('has_trailing_ellipsis'):
                if not display_text.endswith('...'):
                    display_text = display_text + '...'
            line_no = int(seg.get('start_word_index', 1))
            para = f"[line {line_no}] {display_text}"
            formatted_chunks.append(para)

        result = {
            'status': 'success',        
            'chunks': formatted_chunks,
            'total_matches': total_matches,
            'returned_range': [start_idx_clamped, end_idx_clamped]
        }
        return result


    def chunk_text(text, chunk_size=300, overlap=50):
        import re as _re
        words = _re.findall(r'\S+', text or '')
        if not words:
            return []
        if chunk_size <= 0:
            chunk_size = 300
        if overlap < 0:
            overlap = 0
        step = max(1, chunk_size - overlap)
        n = len(words)
        segments = []
        for start in range(0, n, step):
            end = min(start + chunk_size, n)
            chunk_words = words[start:end]
            if not chunk_words:
                break
            chunk_text_val = ' '.join(chunk_words).strip()
            if not chunk_text_val:
                continue
            has_leading = start > 0
            has_trailing = end < n
            segments.append({
                'text': chunk_text_val,
                'start_word_index': start + 1,
                'has_leading_ellipsis': bool(has_leading),
                'has_trailing_ellipsis': bool(has_trailing)
            })
        return segments

    return asyncio.run(main())

@action(
    name="grep",
    description="Searches a text file for keywords and returns matching chunks with pagination.",
    mode="CLI",
    platforms=["darwin"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.txt",
            "description": "Absolute to the input text file to search. The file must already exist on disk and be readable as UTF-8 text (binary files are not supported)."
        },
        "keywords": {
            "type": "array",
            "example": [
                "Mt. Fuji",
                "visibility"
            ],
            "description": "List of plain-text keywords to search for inside the file. All keywords are OR-ed together: a chunk is considered a match if it contains at least one of the keywords (case-insensitive). An empty list is not allowed.",
            "default": []
        },
        "chunk_size": {
            "type": "integer",
            "example": 300,
            "description": "Approximate number of words per chunk. The file content is first tokenized into words, then grouped into chunks of about chunk_size words. Larger values create bigger chunks (more context per hit but more tokens); smaller values create more, smaller chunks.",
            "default": 300
        },
        "overlap": {
            "type": "integer",
            "example": 50,
            "description": "Number of overlapping words between consecutive chunks. For example, with chunk_size=300 and overlap=50, the first chunk is words 1\u2013300, the second chunk is words 251\u2013550, etc.",
            "default": 50
        },
        "chunk_start": {
            "type": "integer",
            "example": 1,
            "description": "1-based start index of the matched chunk range to return (inclusive). If 0 or negative is provided, it is treated as 1.",
            "default": 1
        },
        "chunk_end": {
            "type": "integer",
            "example": 5,
            "description": "1-based end index of the matched chunk range to return (inclusive). If smaller than chunk_start, the two values will be swapped. If larger than the total number of matches, it will be clamped.",
            "default": 5
        }
    },
    output_schema={
        "chunks": {
            "type": "array",
            "example": [
                "[line 275] ...some text chunk...",
                "[line 937] ...another text chunk..."
            ],
            "description": "List of formatted chunks for the requested range."
        },
        "total_matches": {
            "type": "integer",
            "example": 23,
            "description": "Total number of matched chunks available."
        },
        "returned_range": {
            "type": "array",
            "example": [
                1,
                5
            ],
            "description": "The 1-based [start, end] chunk indices that were requested (clamped to available matches)."
        }
    },
    test_payload={
        "input_file": "/path/to/input.txt",
        "keywords": ["Mt. Fuji", "visibility"],
        "chunk_size": 300,
        "overlap": 50,
        "chunk_start": 1,
        "chunk_end": 5,
        "simulated_mode": True
    }
)
def grep_darwin(input_data: dict) -> dict:
    import os, json, re, sys, asyncio

    async def main():
        input_file = input_data.get('input_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        keywords = input_data.get('keywords') or []
        if not keywords:
            raise ValueError('keywords must be a non-empty array.')

        try:
            chunk_size = int(input_data.get('chunk_size', 300))
        except Exception:
            chunk_size = 300
        try:
            overlap = int(input_data.get('overlap', 50))
        except Exception:
            overlap = 50
        try:
            start_idx = int(input_data.get('chunk_start', 1))
        except Exception:
            start_idx = 1
        try:
            end_idx = int(input_data.get('chunk_end', 5))
        except Exception:
            end_idx = 5

        if chunk_size <= 0:
            chunk_size = 300
        if overlap < 0:
            overlap = 0

        if start_idx < 1:
            start_idx = 1
        if end_idx < 1:
            end_idx = 1
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        segments = chunk_text(content, chunk_size=chunk_size, overlap=overlap)

        if not segments:
            result = {'chunks': [], 'total_matches': 0, 'returned_range': [start_idx, end_idx]}
            return result

        pattern = re.compile('(' + '|'.join(re.escape(k) for k in keywords) + ')', re.I)
        matched_segments = [s for s in segments if pattern.search(s['text'])]

        total_matches = len(matched_segments)
        if total_matches == 0:
            result = {'chunks': [], 'total_matches': 0, 'returned_range': [start_idx, end_idx]}
            return result

        start_idx_clamped = max(1, min(start_idx, total_matches))
        end_idx_clamped = max(1, min(end_idx, total_matches))
        if end_idx_clamped < start_idx_clamped:
            start_idx_clamped, end_idx_clamped = end_idx_clamped, start_idx_clamped

        start_zero = start_idx_clamped - 1
        end_zero_excl = end_idx_clamped

        page_segments = matched_segments[start_zero:end_zero_excl]

        def clean_text(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        formatted_chunks = []
        for seg in page_segments:
            text_clean = clean_text(seg['text'])
            if not text_clean:
                continue
            display_text = text_clean
            if seg.get('has_leading_ellipsis'):
                display_text = '...' + display_text
            if seg.get('has_trailing_ellipsis'):
                if not display_text.endswith('...'):
                    display_text = display_text + '...'
            line_no = int(seg.get('start_word_index', 1))
            para = f"[line {line_no}] {display_text}"
            formatted_chunks.append(para)

        result = {
            'status': 'success',        
            'chunks': formatted_chunks,
            'total_matches': total_matches,
            'returned_range': [start_idx_clamped, end_idx_clamped]
        }
        return result


    def chunk_text(text, chunk_size=300, overlap=50):
        import re as _re
        words = _re.findall(r'\S+', text or '')
        if not words:
            return []
        if chunk_size <= 0:
            chunk_size = 300
        if overlap < 0:
            overlap = 0
        step = max(1, chunk_size - overlap)
        n = len(words)
        segments = []
        for start in range(0, n, step):
            end = min(start + chunk_size, n)
            chunk_words = words[start:end]
            if not chunk_words:
                break
            chunk_text_val = ' '.join(chunk_words).strip()
            if not chunk_text_val:
                continue
            has_leading = start > 0
            has_trailing = end < n
            segments.append({
                'text': chunk_text_val,
                'start_word_index': start + 1,
                'has_leading_ellipsis': bool(has_leading),
                'has_trailing_ellipsis': bool(has_trailing)
            })
        return segments

    return asyncio.run(main())