from core.action.action_framework.registry import action

@action(
    name="read web page from URL",
    description="Downloads a web page by URL and returns a clean, markdown-friendly text summary and title (no JavaScript execution).",
    mode="CLI",
    input_schema={
        "url": {
            "type": "string",
            "example": "https://example.com/article",
            "description": "The absolute URL of the page to fetch."
        },
        "timeout": {
            "type": "number",
            "example": 20,
            "description": "Request timeout in seconds."
        },
        "extract_main": {
            "type": "boolean",
            "example": True,
            "description": "If true, extract the main article content; otherwise return full-page text."
        },
        "include_html": {
            "type": "boolean",
            "example": False,
            "description": "If true, include the raw HTML in the output (truncated to max_bytes)."
        },
        "max_bytes": {
            "type": "integer",
            "example": 50000000,
            "description": "Maximum number of bytes to download before aborting."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if the page was fetched and parsed, 'error' otherwise."
        },
        "final_url": {
            "type": "string",
            "example": "https://example.com/article",
            "description": "The final URL after redirects."
        },
        "title": {
            "type": "string",
            "example": "Example Article Title",
            "description": "The best-effort page title."
        },
        "content": {
            "type": "string",
            "example": "A concise, readable version of the page content in Markdown.",
            "description": "Markdown-friendly text extracted from the page."
        },
        "html": {
            "type": "string",
            "example": "<!doctype html><html>...</html>",
            "description": "Raw HTML if include_html=true; omitted otherwise."
        },
        "message": {
            "type": "string",
            "example": "Unsupported content-type.",
            "description": "Optional error or diagnostic message."
        }
    },
    requirement=["BeautifulSoup", "trafilatura", "bs4"],
    test_payload={
        "url": "https://example.com/article",
        "timeout": 20,
        "extract_main": True,
        "include_html": False,
        "max_bytes": 50000000,
        "simulated_mode": True
    }
)
def read_web_page_from_url(input_data: dict) -> dict:
    import json, re, sys, os, subprocess, importlib, requests

    def _ensure(p):
        try:
            importlib.import_module(p)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', p, '--quiet'])

    for _p in ('requests', 'trafilatura', 'beautifulsoup4', 'lxml'):
        _ensure(_p)

    from bs4 import BeautifulSoup
    import trafilatura


    def main():
        global output
        url = str(input_data.get('url', '')).strip()
        if not url or not re.match(r'^https?://', url, re.I):
            return {'status': 'error', 'final_url': '', 'title': '', 'content': '', 'message': 'A valid http(s) URL is required.'}
            return

        timeout = float(input_data.get('timeout', 20))
        extract_main = bool(input_data.get('extract_main', True))
        include_html = bool(input_data.get('include_html', False))
        max_bytes = int(input_data.get('max_bytes', 10_000_000))

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        }

        final_url = url
        data = b''
        encoding = None

        try:
            with requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True) as r:
                r.raise_for_status()
                final_url = str(r.url)
                ctype = r.headers.get('Content-Type', '')
                if not any(t in ctype for t in ('text/html', 'application/xhtml+xml', 'text/plain')):
                    return {'status': 'error', 'final_url': final_url, 'title': '', 'content': '', 'message': 'Unsupported content-type.'}
                    return
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        data += chunk
                        if len(data) > max_bytes:
                            return {'status': 'error', 'final_url': final_url, 'title': '', 'content': '', 'message': 'Download exceeds max_bytes.'}
                            return
                encoding = r.encoding
        except Exception as e:
            return {'status': 'error', 'final_url': '', 'title': '', 'content': '', 'message': str(e)}
            return

        html_text = data.decode(encoding or 'utf-8', errors='replace') if data else ''

        title = ''
        content_md = ''

        try:
            if extract_main:
                content_md = trafilatura.extract(data, url=final_url, include_comments=False, include_tables=True, output_format='markdown') or ''
                try:
                    meta = trafilatura.metadata.extract_metadata(data, url=final_url)
                    if meta and getattr(meta, 'title', None):
                        title = meta.title.strip()
                except Exception:
                    pass
            if not content_md:
                soup = BeautifulSoup(html_text, 'lxml')
                if not title:
                    t = soup.title.string.strip() if soup.title and soup.title.string else ''
                    title = t
                for tag in soup(['script', 'style', 'noscript']):
                    tag.decompose()
                txt = soup.get_text('\n')
                txt = re.sub(r'\n\s*\n\s*\n+', '\n\n', txt)
                content_md = txt.strip()
        except Exception as e:
            return {'status': 'error', 'final_url': final_url, 'title': '', 'content': '', 'message': str(e)}
            return

        out = {
            'status': 'success',
            'final_url': final_url,
            'title': title or '',
            'content': content_md or '',
            'message': ''
        }
        if include_html:
            out['html'] = html_text[:max_bytes]
        return out

    simulated_mode = input_data.get('simulated_mode', False)
    if simulated_mode:
        # Return a mock response for testing
        return {
            'status': 'success',
            'final_url': input_data.get('url', ''),
            'title': 'Test Page Title',
            'content': 'Test page content in markdown format.',
            'message': ''
        }
    
    return main()