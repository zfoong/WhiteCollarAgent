from core.action.action_framework.registry import action

@action(
    name="batch summarize files",
    description="Summarizes all .txt, .md, and .docx files inside a directory using improved summarization logic with chunking and centroid-based clustering.",
    mode="CLI",
    platforms=["linux", "darwin"],
    input_schema={
        "directory_path": {
            "type": "string",
            "example": "/workspace/docs",
            "description": "Directory containing files to summarize."
        },
        "output_directory": {
            "type": "string",
            "example": "/workspace/summaries",
            "description": "Directory where summaries will be saved. Defaults to same folder."
        },
        "top_k": {
            "type": "integer",
            "example": 5,
            "description": "Number of clusters for summary.",
            "default": 5
        },
        "threshold": {
            "type": "number",
            "example": 0.55,
            "description": "Semantic similarity threshold.",
            "default": 0.55
        },
        "keywords": {
            "type": "array",
            "example": [
                    "AI",
                    "machine learning"
            ],
            "description": "Optional keyword filters.",
            "default": []
        }
    },
    output_schema={
        "summaries": {
            "type": "array",
            "description": "List of {input, summary_file} for each processed file."
        }
    },
    test_payload={
        "directory_path": "/workspace/docs",
        "output_directory": "/workspace/summaries",
        "top_k": 5,
        "threshold": 0.55,
        "keywords": [
            "AI",
            "machine learning"
        ],
        "simulated_mode": True
    }
)
def batch_summarize_files_linux(input_data: dict) -> dict:
    import os, json, re, sys, importlib, subprocess, asyncio, concurrent.futures
    
    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        return {'summaries': [{'input': 'test_file.txt', 'summary_file': 'test_file_summary.txt'}]}

    import numpy as np
    from sklearn.cluster import KMeans
    from sentence_transformers import SentenceTransformer
    import aiofiles

    async def main():
        directory = input_data.get('directory_path')
        out_dir = input_data.get('output_directory') or directory
        top_k = int(input_data.get('top_k', 5))
        threshold = float(input_data.get('threshold', 0.55))
        keywords = input_data.get('keywords') or []

        if not directory or not os.path.isdir(directory):
            raise ValueError('directory_path must be a valid directory')

        os.makedirs(out_dir, exist_ok=True)

        for pkg in ['scikit-learn', 'sentence-transformers', 'aiofiles', 'python-docx']:
            try:
                importlib.import_module(pkg.replace('-', '_'))
            except:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

        from docx import Document

        def load_file(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in ('.txt', '.md'):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            elif ext == '.docx':
                doc = Document(path)
                return '\n'.join(p.text for p in doc.paragraphs)
            return ''

        supported = [os.path.join(directory, f) for f in os.listdir(directory)
                     if os.path.splitext(f)[1].lower() in ('.txt', '.md', '.docx')]

        if not supported:
            output =(json.dumps({'summaries': []}))
            return

        summaries = []

        for path in supported:
            content = load_file(path)
            if not content.strip():
                continue

            sentences = []
            for paragraph in content.split('\n'):
                paragraph = paragraph.strip()
                if not paragraph: continue
                para_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', paragraph) if s.strip()]
                for sent in para_sentences:
                    words = sent.split()
                    chunk_size = 50
                    for i in range(0, len(words), chunk_size):
                        chunk = ' '.join(words[i:i+chunk_size])
                        sentences.append(chunk)

            if not sentences: continue

            if keywords:
                pattern = re.compile(r'\\b(' + '|'.join(re.escape(k) for k in keywords) + r')\\b', re.I)
                filtered = [s for s in sentences if pattern.search(s)]
                if filtered:
                    sentences = filtered

            base = os.path.splitext(os.path.basename(path))[0]
            out_file = os.path.join(out_dir, f"{base}_summary.txt")

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await loop.run_in_executor(pool, lambda: summarize(sentences, top_k, threshold, out_file))

            summaries.append({"input": os.path.basename(path), "summary_file": out_file})

        return {"summaries": summaries}


    def summarize(sentences, top_k, threshold, out_file):
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(sentences, normalize_embeddings=True)

        centroid = embeddings.mean(axis=0)
        sims = embeddings @ centroid
        idx = np.where(sims >= threshold)[0]
        if len(idx) < max(3, top_k):
            idx = list(range(len(sentences)))

        filtered_s = [sentences[i] for i in idx]
        filtered_e = embeddings[idx]

        n_clusters = min(top_k, len(filtered_s))
        km = KMeans(n_clusters=n_clusters, n_init='auto', random_state=42)
        labels = km.fit_predict(filtered_e)

        summary_s = []
        for cluster_id in range(n_clusters):
            cluster_idxs = [i for i, lbl in enumerate(labels) if lbl == cluster_id]
            cluster_emb = filtered_e[cluster_idxs]
            cluster_centroid = cluster_emb.mean(axis=0)
            closest_idx = cluster_idxs[np.argmax(cluster_emb @ cluster_centroid)]
            summary_s.append(filtered_s[closest_idx])

        final = ' '.join(re.sub(r'\\s+', ' ', s.strip()) for s in summary_s if s.strip())
        asyncio.run(write_out(final, out_file))


    async def write_out(text, path):
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(text)


    return asyncio.run(main())

@action(
    name="batch summarize files",
    description="Summarizes all .txt, .md, and .docx files inside a directory using improved summarization logic with chunking and centroid-based clustering.",
    mode="CLI",
    platforms=["windows"],
    input_schema={
        "directory_path": {
            "type": "string",
            "example": "/workspace/docs",
            "description": "Directory containing files to summarize."
        },
        "output_directory": {
            "type": "string",
            "example": "/workspace/summaries",
            "description": "Directory where summaries will be saved. Defaults to same folder."
        },
        "top_k": {
            "type": "integer",
            "example": 5,
            "description": "Number of clusters for summary.",
            "default": 5
        },
        "threshold": {
            "type": "number",
            "example": 0.55,
            "description": "Semantic similarity threshold.",
            "default": 0.55
        },
        "keywords": {
            "type": "array",
            "example": [
                    "AI",
                    "machine learning"
            ],
            "description": "Optional keyword filters.",
            "default": []
        }
    },
    output_schema={
        "summaries": {
            "type": "array",
            "description": "List of {input, summary_file} for each processed file."
        }
    },
    test_payload={
        "directory_path": "/workspace/docs",
        "output_directory": "/workspace/summaries",
        "top_k": 5,
        "threshold": 0.55,
        "keywords": [
            "AI",
            "machine learning"
        ],
        "simulated_mode": True
    }
)
def batch_summarize_files_windows(input_data: dict) -> dict:
    import os, json, re, sys, importlib, subprocess, asyncio, concurrent.futures
    import numpy as np
    from sklearn.cluster import KMeans
    from sentence_transformers import SentenceTransformer
    import aiofiles

    async def main():
        directory = input_data.get('directory_path')
        out_dir = input_data.get('output_directory') or directory
        top_k = int(input_data.get('top_k', 5))
        threshold = float(input_data.get('threshold', 0.55))
        keywords = input_data.get('keywords') or []

        if not directory or not os.path.isdir(directory):
            raise ValueError('directory_path must be a valid directory')

        os.makedirs(out_dir, exist_ok=True)

        for pkg in ['scikit-learn', 'sentence-transformers', 'aiofiles']:
            try:
                importlib.import_module(pkg.replace('-', '_'))
            except:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

        def load_file(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

        supported = [os.path.join(directory, f) for f in os.listdir(directory)
                     if os.path.splitext(f)[1].lower() in ('.txt', '.md')]

        if not supported:
            return {'summaries': []}

        summaries = []

        for path in supported:
            content = load_file(path)
            if not content.strip(): continue

            sentences = []
            for paragraph in content.split('\n'):
                paragraph = paragraph.strip()
                if not paragraph: continue
                para_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', paragraph) if s.strip()]
                for sent in para_sentences:
                    words = sent.split()
                    chunk_size = 50
                    for i in range(0, len(words), chunk_size):
                        chunk = ' '.join(words[i:i+chunk_size])
                        sentences.append(chunk)

            if not sentences: continue

            if keywords:
                pattern = re.compile(r'\\b(' + '|'.join(re.escape(k) for k in keywords) + r')\\b', re.I)
                filtered = [s for s in sentences if pattern.search(s)]
                if filtered:
                    sentences = filtered

            base = os.path.splitext(os.path.basename(path))[0]
            out_file = os.path.join(out_dir, f"{base}_summary.txt")

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await loop.run_in_executor(pool, lambda: summarize(sentences, top_k, threshold, out_file))

            summaries.append({"input": os.path.basename(path), "summary_file": out_file})

        return {"summaries": summaries}


    def summarize(sentences, top_k, threshold, out_file):
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(sentences, normalize_embeddings=True)

        centroid = embeddings.mean(axis=0)
        sims = embeddings @ centroid
        idx = np.where(sims >= threshold)[0]
        if len(idx) < max(3, top_k):
            idx = list(range(len(sentences)))

        filtered_s = [sentences[i] for i in idx]
        filtered_e = embeddings[idx]

        n_clusters = min(top_k, len(filtered_s))
        km = KMeans(n_clusters=n_clusters, n_init='auto', random_state=42)
        labels = km.fit_predict(filtered_e)

        summary_s = []
        for cluster_id in range(n_clusters):
            cluster_idxs = [i for i, lbl in enumerate(labels) if lbl == cluster_id]
            cluster_emb = filtered_e[cluster_idxs]
            cluster_centroid = cluster_emb.mean(axis=0)
            closest_idx = cluster_idxs[np.argmax(cluster_emb @ cluster_centroid)]
            summary_s.append(filtered_s[closest_idx])

        final = ' '.join(re.sub(r'\\s+', ' ', s.strip()) for s in summary_s if s.strip())
        asyncio.run(write_out(final, out_file))


    async def write_out(text, path):
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(text)


    return asyncio.run(main())
