from core.action.action_framework.registry import action

@action(
    name="summarize file content",
    description="Reads a text file and write the summary to a new text file.",
    mode="CLI",
    platforms=["linux"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.txt",
            "description": "Path to the input text file to summarize."
        },
        "output_file": {
            "type": "string",
            "example": "/path/to/output_summary.txt",
            "description": "Path where the summary will be saved. Defaults to appending '_summary.txt' to input file.",
            "default": ""
        },
        "top_k": {
            "type": "integer",
            "example": 5,
            "description": "Number of clusters to form.",
            "default": 5
        },
        "threshold": {
            "type": "number",
            "example": 0.55,
            "description": "Semantic similarity threshold for filtering sentences.",
            "default": 0.55
        },
        "keywords": {
            "type": "array",
            "example": [
                "AI",
                "machine learning"
            ],
            "description": "Optional keywords to filter sentences.",
            "default": []
        }
    },
    output_schema={
        "summary_file": {
            "type": "string",
            "example": "/path/to/output_summary.txt",
            "description": "Path of the generated summary file."
        }
    },
    test_payload={
        "input_file": "/tmp/test_file.txt",
        "output_file": "/tmp/test_file_summary.txt",
        "top_k": 5,
        "threshold": 0.55,
        "keywords": [
            "AI",
            "machine learning"
        ],
        "simulated_mode": True
    }
)
def summarize_file_content_linux(input_data: dict) -> dict:
    import os, json, re, sys, importlib, subprocess, asyncio, concurrent.futures

    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        output_file = input_data.get('output_file') or '/tmp/test_file_summary.txt'
        return {'summary_file': output_file}

    async def main():
        input_file = input_data.get('input_file')
        output_file = input_data.get('output_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        if not output_file:
            base, ext = os.path.splitext(input_file)
            output_file = f'{base}_summary.txt'

        keywords = input_data.get('keywords') or []
        top_k = int(input_data.get('top_k', 5))
        threshold = float(input_data.get('threshold', 0.55))

        for pkg in ['scikit-learn', 'sentence-transformers', 'aiofiles']:
            try:
                importlib.import_module(pkg.replace('-', '_'))
            except:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

        import aiofiles

        async with aiofiles.open(input_file, 'r', encoding='utf-8') as f:
            content = await f.read()

        segments = chunk_text(content, chunk_size=300, overlap=50)
        if not segments:
            async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
                await f.write('')
            return {'summary_file': output_file}
            return

        if keywords:
            pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keywords) + r')\b', re.I)
            filtered_segments = [s for s in segments if pattern.search(s['text'])]
            if filtered_segments:
                segments = filtered_segments

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            summary_file = await loop.run_in_executor(pool, lambda: process_summary(segments, top_k, threshold, output_file))

        return {'summary_file': summary_file}


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


    def process_summary(segments, top_k, threshold, output_file):
        from sentence_transformers import SentenceTransformer
        import numpy as np
        from sklearn.cluster import KMeans
        import asyncio, aiofiles, re

        if not segments:
            asyncio.run(save_summary('', output_file))
            return output_file

        texts = [s['text'] for s in segments]
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(texts, normalize_embeddings=True)

        centroid = embeddings.mean(axis=0)
        sims = embeddings @ centroid
        filtered_idx = np.where(sims >= threshold)[0]
        if filtered_idx.size > 0:
            filtered_segments = [segments[i] for i in filtered_idx]
            filtered_embeddings = embeddings[filtered_idx]
        else:
            filtered_segments = segments
            filtered_embeddings = embeddings

        n_clusters = min(max(1, top_k), len(filtered_segments))
        km = KMeans(n_clusters=n_clusters, n_init='auto')
        labels = km.fit_predict(filtered_embeddings)
        clusters = []
        for cluster_id in range(km.n_clusters):
            idx = np.where(labels == cluster_id)[0]
            clusters.append([filtered_segments[i] for i in idx])

        summary_segments = []
        for cluster in clusters:
            if not cluster:
                continue
            rep = cluster[len(cluster) // 2]
            summary_segments.append(rep)

        def clean_segment_text(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        seen_texts = set()
        final_paragraphs = []
        for seg in summary_segments:
            text_clean = clean_segment_text(seg['text'])
            if not text_clean or text_clean in seen_texts:
                continue
            seen_texts.add(text_clean)
            display_text = text_clean
            if seg.get('has_leading_ellipsis'):
                display_text = '...' + display_text
            if seg.get('has_trailing_ellipsis'):
                if not display_text.endswith('...'):
                    display_text = display_text + '...'
            line_no = int(seg.get('start_word_index', 1))
            para = f"[line {line_no}] {display_text}"
            final_paragraphs.append(para)

        final_summary = '\n\n'.join(final_paragraphs)

        asyncio.run(save_summary(final_summary, output_file))
        return output_file

    async def save_summary(text, path):
        import aiofiles
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(text)

    return asyncio.run(main())

@action(
    name="summarize file content",
    description="Reads a text file and write the summary to a new text file.",
    mode="CLI",
    platforms=["windows"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.txt",
            "description": "Path to the input text file to summarize."
        },
        "output_file": {
            "type": "string",
            "example": "/path/to/output_summary.txt",
            "description": "Path where the summary will be saved. Defaults to appending '_summary.txt' to input file.",
            "default": ""
        },
        "top_k": {
            "type": "integer",
            "example": 5,
            "description": "Number of clusters to form.",
            "default": 5
        },
        "threshold": {
            "type": "number",
            "example": 0.55,
            "description": "Semantic similarity threshold for filtering sentences.",
            "default": 0.55
        },
        "keywords": {
            "type": "array",
            "example": [
                "AI",
                "machine learning"
            ],
            "description": "Optional keywords to filter sentences.",
            "default": []
        }
    },
    output_schema={
        "summary_file": {
            "type": "string",
            "example": "/path/to/output_summary.txt",
            "description": "Path of the generated summary file."
        }
    },
    test_payload={
        "input_file": "/tmp/test_file.txt",
        "output_file": "/tmp/test_file_summary.txt",
        "top_k": 5,
        "threshold": 0.55,
        "keywords": [
            "AI",
            "machine learning"
        ],
        "simulated_mode": True
    }
)
def summarize_file_content_windows(input_data: dict) -> dict:
    import os, json, re, sys, importlib, subprocess, asyncio, concurrent.futures

    async def main():
        input_file = input_data.get('input_file')
        output_file = input_data.get('output_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        if not output_file:
            base, ext = os.path.splitext(input_file)
            output_file = f'{base}_summary.txt'

        keywords = input_data.get('keywords') or []
        top_k = int(input_data.get('top_k', 5))
        threshold = float(input_data.get('threshold', 0.55))

        for pkg in ['scikit-learn', 'sentence-transformers', 'aiofiles']:
            try:
                importlib.import_module(pkg.replace('-', '_'))
            except:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

        import aiofiles

        async with aiofiles.open(input_file, 'r', encoding='utf-8') as f:
            content = await f.read()

        segments = chunk_text(content, chunk_size=300, overlap=50)
        if not segments:
            async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
                await f.write('')
            return {'summary_file': output_file}
            return

        if keywords:
            pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keywords) + r')\b', re.I)
            filtered_segments = [s for s in segments if pattern.search(s['text'])]
            if filtered_segments:
                segments = filtered_segments

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            summary_file = await loop.run_in_executor(pool, lambda: process_summary(segments, top_k, threshold, output_file))

        return {'summary_file': summary_file}


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


    def process_summary(segments, top_k, threshold, output_file):
        from sentence_transformers import SentenceTransformer
        import numpy as np
        from sklearn.cluster import KMeans
        import asyncio, aiofiles, re

        if not segments:
            asyncio.run(save_summary('', output_file))
            return output_file

        texts = [s['text'] for s in segments]
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(texts, normalize_embeddings=True)

        centroid = embeddings.mean(axis=0)
        sims = embeddings @ centroid
        filtered_idx = np.where(sims >= threshold)[0]
        if filtered_idx.size > 0:
            filtered_segments = [segments[i] for i in filtered_idx]
            filtered_embeddings = embeddings[filtered_idx]
        else:
            filtered_segments = segments
            filtered_embeddings = embeddings

        n_clusters = min(max(1, top_k), len(filtered_segments))
        km = KMeans(n_clusters=n_clusters, n_init='auto')
        labels = km.fit_predict(filtered_embeddings)
        clusters = []
        for cluster_id in range(km.n_clusters):
            idx = np.where(labels == cluster_id)[0]
            clusters.append([filtered_segments[i] for i in idx])

        summary_segments = []
        for cluster in clusters:
            if not cluster:
                continue
            rep = cluster[len(cluster) // 2]
            summary_segments.append(rep)

        def clean_segment_text(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        seen_texts = set()
        final_paragraphs = []
        for seg in summary_segments:
            text_clean = clean_segment_text(seg['text'])
            if not text_clean or text_clean in seen_texts:
                continue
            seen_texts.add(text_clean)
            display_text = text_clean
            if seg.get('has_leading_ellipsis'):
                display_text = '...' + display_text
            if seg.get('has_trailing_ellipsis'):
                if not display_text.endswith('...'):
                    display_text = display_text + '...'
            line_no = int(seg.get('start_word_index', 1))
            para = f"[line {line_no}] {display_text}"
            final_paragraphs.append(para)

        final_summary = '\n\n'.join(final_paragraphs)

        asyncio.run(save_summary(final_summary, output_file))
        return output_file

    async def save_summary(text, path):
        import aiofiles
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(text)

    return asyncio.run(main())

@action(
    name="summarize file content",
    description="Reads a text file and write the summary to a new text file.",
    mode="CLI",
    platforms=["darwin"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.txt",
            "description": "Path to the input text file to summarize."
        },
        "output_file": {
            "type": "string",
            "example": "/path/to/output_summary.txt",
            "description": "Path where the summary will be saved. Defaults to appending '_summary.txt' to input file.",
            "default": ""
        },
        "top_k": {
            "type": "integer",
            "example": 5,
            "description": "Number of clusters to form.",
            "default": 5
        },
        "threshold": {
            "type": "number",
            "example": 0.55,
            "description": "Semantic similarity threshold for filtering sentences.",
            "default": 0.55
        },
        "keywords": {
            "type": "array",
            "example": [
                "AI",
                "machine learning"
            ],
            "description": "Optional keywords to filter sentences.",
            "default": []
        }
    },
    output_schema={
        "summary_file": {
            "type": "string",
            "example": "/path/to/output_summary.txt",
            "description": "Path of the generated summary file."
        }
    },
    test_payload={
        "input_file": "/tmp/test_file.txt",
        "output_file": "/tmp/test_file_summary.txt",
        "top_k": 5,
        "threshold": 0.55,
        "keywords": [
            "AI",
            "machine learning"  
        ],
        "simulated_mode": True
    }
)
def summarize_file_content_darwin(input_data: dict) -> dict:
    import os, json, re, sys, importlib, subprocess, asyncio, concurrent.futures

    async def main():
        input_file = input_data.get('input_file')
        output_file = input_data.get('output_file')
        if not input_file or not os.path.isfile(input_file):
            raise ValueError('Input file must exist.')

        if not output_file:
            base, ext = os.path.splitext(input_file)
            output_file = f'{base}_summary.txt'

        keywords = input_data.get('keywords') or []
        top_k = int(input_data.get('top_k', 5))
        threshold = float(input_data.get('threshold', 0.55))

        for pkg in ['scikit-learn', 'sentence-transformers', 'aiofiles']:
            try:
                importlib.import_module(pkg.replace('-', '_'))
            except:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

        import aiofiles

        async with aiofiles.open(input_file, 'r', encoding='utf-8') as f:
            content = await f.read()

        segments = chunk_text(content, chunk_size=300, overlap=50)
        if not segments:
            async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
                await f.write('')
            return {'summary_file': output_file}
            return

        if keywords:
            pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keywords) + r')\b', re.I)
            filtered_segments = [s for s in segments if pattern.search(s['text'])]
            if filtered_segments:
                segments = filtered_segments

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            summary_file = await loop.run_in_executor(pool, lambda: process_summary(segments, top_k, threshold, output_file))

        return {'summary_file': summary_file}


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


    def process_summary(segments, top_k, threshold, output_file):
        from sentence_transformers import SentenceTransformer
        import numpy as np
        from sklearn.cluster import KMeans
        import asyncio, aiofiles, re

        if not segments:
            asyncio.run(save_summary('', output_file))
            return output_file

        texts = [s['text'] for s in segments]
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(texts, normalize_embeddings=True)

        centroid = embeddings.mean(axis=0)
        sims = embeddings @ centroid
        filtered_idx = np.where(sims >= threshold)[0]
        if filtered_idx.size > 0:
            filtered_segments = [segments[i] for i in filtered_idx]
            filtered_embeddings = embeddings[filtered_idx]
        else:
            filtered_segments = segments
            filtered_embeddings = embeddings

        n_clusters = min(max(1, top_k), len(filtered_segments))
        km = KMeans(n_clusters=n_clusters, n_init='auto')
        labels = km.fit_predict(filtered_embeddings)
        clusters = []
        for cluster_id in range(km.n_clusters):
            idx = np.where(labels == cluster_id)[0]
            clusters.append([filtered_segments[i] for i in idx])

        summary_segments = []
        for cluster in clusters:
            if not cluster:
                continue
            rep = cluster[len(cluster) // 2]
            summary_segments.append(rep)

        def clean_segment_text(s):
            s = s.strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        seen_texts = set()
        final_paragraphs = []
        for seg in summary_segments:
            text_clean = clean_segment_text(seg['text'])
            if not text_clean or text_clean in seen_texts:
                continue
            seen_texts.add(text_clean)
            display_text = text_clean
            if seg.get('has_leading_ellipsis'):
                display_text = '...' + display_text
            if seg.get('has_trailing_ellipsis'):
                if not display_text.endswith('...'):
                    display_text = display_text + '...'
            line_no = int(seg.get('start_word_index', 1))
            para = f"[line {line_no}] {display_text}"
            final_paragraphs.append(para)

        final_summary = '\n\n'.join(final_paragraphs)

        asyncio.run(save_summary(final_summary, output_file))
        return output_file

    async def save_summary(text, path):
        import aiofiles
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(text)

    return asyncio.run(main())