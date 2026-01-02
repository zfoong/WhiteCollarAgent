from core.action.action_framework.registry import action

@action(
        name="download from url",
        description="Download any file from an arbitrary internet URL (HTTP/HTTPS) into the agent workspace, following redirects. Use when you need external resources such as datasets, binaries, or documents. DO NOT use this action to download attachment sent over chat",
        mode="CLI",
        input_schema={
                "url": {
                        "type": "string",
                        "example": "https://example.com/file.zip",
                        "description": "Direct download URL."
                },
                "filename": {
                        "type": "string",
                        "example": "file.zip",
                        "description": "Optional custom filename; defaults to last path component."
                },
                "dest_dir": {
                        "type": "string",
                        "example": "/workspace/downloads",
                        "description": "Optional destination directory (created if missing)."
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "ok",
                        "description": "Indicates the download completed successfully."
                },
                "path": {
                        "type": "string",
                        "example": "/workspace/downloads/file.zip",
                        "description": "Absolute path to the saved file."
                },
                "size_bytes": {
                        "type": "integer",
                        "example": 1048576,
                        "description": "Size of the downloaded file in bytes."
                }
        },
        requirement=["Path", "AGENT_WORKSPACE_ROOT"],
        test_payload={
                "url": "https://example.com/file.zip",
                "filename": "file.zip",
                "dest_dir": "/workspace/downloads",
                "simulated_mode": True
        }
)
def download_from_url(input_data: dict) -> dict:
    import json, asyncio, uuid, os
    from pathlib import Path
    
    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        url = input_data.get('url', '')
        filename = input_data.get('filename') or url.split('/')[-1] or 'file.zip'
        dest_dir = input_data.get('dest_dir', '/workspace/downloads')
        file_path = f"{dest_dir}/{filename}"
        return {'status': 'success', 'path': file_path, 'size_bytes': 1024}
    
    import httpx
    from core.config import AGENT_WORKSPACE_ROOT

    url       = input_data['url']                           # required
    filename  = input_data.get('filename') or url.split('/')[-1] or str(uuid.uuid4())
    dest_dir  = Path(input_data.get('dest_dir', AGENT_WORKSPACE_ROOT)).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    file_path = dest_dir / filename

    async def _download():
        async with httpx.AsyncClient() as client:
            async with client.stream('GET', url, follow_redirects=True, timeout=60) as resp:
                resp.raise_for_status()
                with file_path.open('wb') as out:
                    async for chunk in resp.aiter_bytes(chunk_size=1<<16):  # 64 KB
                        out.write(chunk)

    try:
        asyncio.run(_download())
        size = file_path.stat().st_size
        return {'status': 'ok', 'path': str(file_path), 'size_bytes': size}
    except Exception as e:
        return {'status': 'error', 'path': '', 'size_bytes': 0, 'message': str(e)}