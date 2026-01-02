from core.action.action_framework.registry import action

@action(
    name="combine text documents",
    description="Scans a directory for .txt, .md, and .docx files, extracts their content, and combines them into a single draft Markdown file at the specified output path.",
    input_schema={
        "directory_path": {
            "type": "string",
            "example": "/workspace/tmp/",
            "description": "Directory containing .txt, .md, and .docx files."
        },
        "output_path": {
            "type": "string",
            "example": "/workspace/draft.md",
            "description": "Where to save the combined Markdown file."
        }
    },
    output_schema={
        "output_file": {
            "type": "string",
            "description": "Path to the generated draft.md file."
        },
        "files_included": {
            "type": "array",
            "description": "List of files that were included in the combined draft."
        }
    },
    test_payload={
        "directory_path": "/workspace/tmp/",
        "output_path": "/workspace/draft.md",
        "simulated_mode": True
    }
)
def combine_text_documents(input_data: dict) -> dict:
    import os, sys, json, importlib, subprocess
    from typing import List

    # Ensure dependencies

    def _ensure(pkg):
        try:
            importlib.import_module(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

    _ensure('python-docx')

    from docx import Document

    # ───────────────────────────────────────────────
    # Read file contents
    # ───────────────────────────────────────────────

    def read_txt(path: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ''


    def read_md(path: str) -> str:
        return read_txt(path)


    def read_docx(path: str) -> str:
        try:
            doc = Document(path)
            return '\n'.join([p.text for p in doc.paragraphs])
        except Exception:
            return ''

    # ───────────────────────────────────────────────
    # Entrypoint
    # ───────────────────────────────────────────────

    simulated_mode = input_data.get('simulated_mode', False)
    
    directory = input_data.get('directory_path')
    output_path = input_data.get('output_path')

    if simulated_mode:
        # Return mock result for testing
        if not output_path:
            output_path = '/workspace/draft.md'
        return {
            'status': 'success',
            'message': 'Draft created successfully.',
            'output_file': output_path,
            'files_included': ['test_file1.txt', 'test_file2.md']
        }

    if not directory or not os.path.isdir(directory):
        return {'status': 'error', 'message': "'directory_path' must be a valid directory.", 'output_file': '', 'files_included': []}
    if not output_path:
        return {'status': 'error', 'message': "'output_path' is required and must be a file path ending in .md", 'output_file': '', 'files_included': []}

    supported_ext = {'.txt', '.md', '.docx'}
    collected = []

    for fname in os.listdir(directory):
        ext = os.path.splitext(fname)[1].lower()
        if ext in supported_ext:
            collected.append(os.path.join(directory, fname))

    if not collected:
        return {'status': 'error', 'message': 'No supported text files found in directory.', 'output_file': '', 'files_included': []}

    content_blocks = []
    included_files = []

    for path in collected:
        ext = os.path.splitext(path)[1].lower()
        if ext == '.txt': text = read_txt(path)
        elif ext == '.md': text = read_md(path)
        elif ext == '.docx': text = read_docx(path)
        else: continue

        if text.strip():
            content_blocks.append(f"# File: {os.path.basename(path)}\n\n{text}\n\n---\n")
            included_files.append(os.path.basename(path))

    # Ensure directory for output exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    final_md = '\n'.join(content_blocks)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_md)

    return {
        'status': 'success',
        'message': 'Draft created successfully.',
        'output_file': output_path,
        'files_included': included_files
    }