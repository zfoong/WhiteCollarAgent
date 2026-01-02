from core.action.action_framework.registry import action

@action(
    name="open browser google chrome",
    description="Opens a web browser (Chrome, Edge, Firefox, Safari, or system default) across platforms. Optionally opens a specified URL.",
    mode="GUI",
    input_schema={
        "url": {
            "type": "string",
            "example": "https://www.example.com",
            "description": "Optional URL to open in the browser."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if a browser launched, 'error' otherwise."
        },
        "process_id": {
            "type": "integer",
            "example": 12345,
            "description": "Process ID of the launched browser instance when successful; \u22121 when opened via system default browser."
        },
        "browser": {
            "type": "string",
            "example": "chrome",
            "description": "Name of the browser that was launched."
        },
        "executable_path": {
            "type": "string",
            "example": "/usr/bin/google-chrome",
            "description": "Absolute path to the browser executable used, if applicable."
        },
        "message": {
            "type": "string",
            "example": "Launched successfully.",
            "description": "Error or informational message."
        }
    },
    test_payload={
        "url": "https://www.example.com",
        "simulated_mode": False
    }
)
def open_browser(input_data: dict) -> dict:
    import json, webbrowser
    url = str(input_data.get('url', '')).strip()
    try:
        if url:
            webbrowser.open(url)
        return {
            'status': 'success',
            'process_id': -1,
            'browser': 'default',
            'executable_path': '',
            'message': 'Opened URL using system default browser.'
        }
    except Exception as e:
        return {
            'status': 'error',
            'process_id': -1,
            'browser': '',
            'executable_path': '',
            'message': str(e)
        }

@action(
    name="open browser google chrome",
    description="Opens a web browser (Chrome, Edge, Firefox, Safari, or system default) across platforms. Optionally opens a specified URL.",
    platforms=["windows"],
    input_schema={
        "url": {
                "type": "string",
                "example": "https://www.example.com",
                "description": "Optional URL to open in the browser."
        }
},
    output_schema={
        "status": {
                "type": "string",
                "example": "success",
                "description": "'success' if a browser launched, 'error' otherwise."
        },
        "process_id": {
                "type": "integer",
                "example": 12345,
                "description": "Process ID of the launched browser instance when successful; \u22121 when opened via system default browser."
        },
        "browser": {
                "type": "string",
                "example": "chrome",
                "description": "Name of the browser that was launched."
        },
        "executable_path": {
                "type": "string",
                "example": "/usr/bin/google-chrome",
                "description": "Absolute path to the browser executable used, if applicable."
        },
        "message": {
                "type": "string",
                "example": "Launched successfully.",
                "description": "Error or informational message."
        }
},
)
def open_browser_windows(input_data: dict) -> dict:
    import os, json, subprocess, shutil, webbrowser
    url = str(input_data.get('url', '')).strip()

    candidates = [
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
        r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
        r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        r"C:\\Program Files\\Mozilla Firefox\\firefox.exe"
    ]

    try:
        browser_path = next((p for p in candidates if os.path.isfile(p)), None)
        if browser_path:
            cmd = [browser_path] + ([url] if url else [])
            creation_flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
            return {
                'status': 'success',
                'process_id': proc.pid,
                'browser': os.path.basename(browser_path).split('.')[0],
                'executable_path': browser_path,
                'message': 'Launched specific browser successfully.'
            }
        else:
            if url:
                webbrowser.open(url)
            return {
                'status': 'success',
                'process_id': -1,
                'browser': 'default',
                'executable_path': '',
                'message': 'Opened URL using system default browser.'
            }
    except Exception as e:
        return {
            'status': 'error',
            'process_id': -1,
            'browser': '',
            'executable_path': '',
            'message': str(e)
        }

@action(
    name="open browser google chrome",
    description="Opens a web browser (Chrome, Edge, Firefox, Safari, or system default) across platforms. Optionally opens a specified URL.",
    platforms=["darwin"],
    input_schema={
        "url": {
                "type": "string",
                "example": "https://www.example.com",
                "description": "Optional URL to open in the browser."
        }
},
    output_schema={
        "status": {
                "type": "string",
                "example": "success",
                "description": "'success' if a browser launched, 'error' otherwise."
        },
        "process_id": {
                "type": "integer",
                "example": 12345,
                "description": "Process ID of the launched browser instance when successful; \u22121 when opened via system default browser."
        },
        "browser": {
                "type": "string",
                "example": "chrome",
                "description": "Name of the browser that was launched."
        },
        "executable_path": {
                "type": "string",
                "example": "/usr/bin/google-chrome",
                "description": "Absolute path to the browser executable used, if applicable."
        },
        "message": {
                "type": "string",
                "example": "Launched successfully.",
                "description": "Error or informational message."
        }
},
)
def open_browser_darwin(input_data: dict) -> dict:
    import os, json, subprocess, shutil, webbrowser
    url = str(input_data.get('url', '')).strip()

    candidates = [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        '/Applications/Firefox.app/Contents/MacOS/firefox',
        '/Applications/Safari.app/Contents/MacOS/Safari'
    ]

    try:
        browser_path = next((p for p in candidates if os.path.isfile(p)), None)
        if browser_path:
            cmd = [browser_path] + ([url] if url else [])
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {
                'status': 'success',
                'process_id': proc.pid,
                'browser': os.path.basename(browser_path).split('.')[0],
                'executable_path': browser_path,
                'message': 'Launched specific browser successfully.'
            }
        else:
            if url:
                webbrowser.open(url)
            return {
                'status': 'success',
                'process_id': -1,
                'browser': 'default',
                'executable_path': '',
                'message': 'Opened URL using system default browser.'
            }
    except Exception as e:
        return {
            'status': 'error',
            'process_id': -1,
            'browser': '',
            'executable_path': '',
            'message': str(e)
        }

@action(
    name="open browser google chrome",
    description="Opens a web browser (Chrome, Edge, Firefox, Safari, or system default) across platforms. Optionally opens a specified URL.",
    platforms=["linux"],
    input_schema={
        "url": {
                "type": "string",
                "example": "https://www.example.com",
                "description": "Optional URL to open in the browser."
        }
},
    output_schema={
        "status": {
                "type": "string",
                "example": "success",
                "description": "'success' if a browser launched, 'error' otherwise."
        },
        "process_id": {
                "type": "integer",
                "example": 12345,
                "description": "Process ID of the launched browser instance when successful; \u22121 when opened via system default browser."
        },
        "browser": {
                "type": "string",
                "example": "chrome",
                "description": "Name of the browser that was launched."
        },
        "executable_path": {
                "type": "string",
                "example": "/usr/bin/google-chrome",
                "description": "Absolute path to the browser executable used, if applicable."
        },
        "message": {
                "type": "string",
                "example": "Launched successfully.",
                "description": "Error or informational message."
        }
},
)
def open_browser_linux(input_data: dict) -> dict:
    import os, json, subprocess, shutil, webbrowser
    url = str(input_data.get('url', '')).strip()

    candidates = [
        shutil.which('google-chrome'),
        shutil.which('chromium'),
        shutil.which('brave-browser'),
        shutil.which('firefox'),
        shutil.which('microsoft-edge')
    ]

    try:
        browser_path = next((p for p in candidates if p and os.path.isfile(p)), None)
        if browser_path:
            cmd = [browser_path] + ([url] if url else [])
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {
                'status': 'success',
                'process_id': proc.pid,
                'browser': os.path.basename(browser_path).split('.')[0],
                'executable_path': browser_path,
                'message': 'Launched specific browser successfully.'
            }
        else:
            if url:
                webbrowser.open(url)
            return {
                'status': 'success',
                'process_id': -1,
                'browser': 'default',
                'executable_path': '',
                'message': 'Opened URL using system default browser.'
            }
    except Exception as e:
        return {
            'status': 'error',
            'process_id': -1,
            'browser': '',
            'executable_path': '',
            'message': str(e)
        }