"""Temporary local HTTP server for OAuth callbacks."""
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _OAuthCallbackHandler.code = params.get("code", [None])[0]
        _OAuthCallbackHandler.state = params.get("state", [None])[0]
        _OAuthCallbackHandler.error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if _OAuthCallbackHandler.code:
            self.wfile.write(b"<h2>Authorization successful!</h2><p>You can close this tab.</p>")
        else:
            self.wfile.write(f"<h2>Failed</h2><p>{_OAuthCallbackHandler.error}</p>".encode())

    def log_message(self, format, *args):
        pass


def run_oauth_flow(auth_url: str, port: int = 8765, timeout: int = 120) -> Tuple[Optional[str], Optional[str]]:
    """Open browser for OAuth, wait for callback. Returns (code, error_message)."""
    _OAuthCallbackHandler.code = None
    _OAuthCallbackHandler.state = None
    _OAuthCallbackHandler.error = None

    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.timeout = timeout

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    try:
        webbrowser.open(auth_url)
    except Exception:
        server.server_close()
        return None, f"Could not open browser. Visit manually:\n{auth_url}"

    thread.join(timeout=timeout)
    server.server_close()

    if _OAuthCallbackHandler.error:
        return None, _OAuthCallbackHandler.error
    if _OAuthCallbackHandler.code:
        return _OAuthCallbackHandler.code, None
    return None, "OAuth timed out."
