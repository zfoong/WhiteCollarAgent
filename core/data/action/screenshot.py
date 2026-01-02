from core.action.action_framework.registry import action

@action(
    name="screenshot",
    description="Takes a screenshot of the agent screen.",
    platforms=["linux"],
    input_schema={
        "output_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png",
            "description": "Optional absolute file path for the screenshot. If omitted, a timestamped PNG is saved in the workspace root."
        },
        "format": {
            "type": "string",
            "example": "png",
            "description": "Image format: \"png\" or \"jpg\". Defaults to \"png\"."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success"
        },
        "file_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png"
        },
        "message": {
            "type": "string",
            "example": "Unable to capture screen."
        }
    },
    requirement=["mss", "Pillow"],
    test_payload={
        "output_path": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png",
        "format": "png",
        "simulated_mode": True
    }
)
def screenshot(input_data: dict) -> dict:
    import json, os, sys, subprocess, importlib, time
    from datetime import datetime

    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        output_path = str(input_data.get('output_path', '')).strip()
        if not output_path:
            output_path = '/tmp/screenshot_test.png'
        return {'status': 'success', 'file_path': output_path, 'message': ''}

    # Install required packages
    def _ensure(pkg):
        try:
            importlib.import_module(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])

    for pkg in ("mss", "Pillow"):
        _ensure(pkg)

    import mss
    from PIL import Image

    # Inputs
    output_path = str(input_data.get('output_path','')).strip()
    fmt = str(input_data.get('format','png')).lower()
    if fmt not in ('png','jpg','jpeg'):
        fmt='png'

    if not output_path:
        root = os.getenv('AGENT_WORKSPACE_ROOT', os.getcwd())
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(root, f"screenshot_{ts}.{fmt}")

    # Helper: MSS
    def try_mss():
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                img = Image.frombytes('RGB', shot.size, shot.rgb)
                img.save(output_path, fmt.upper())
            return True
        except Exception:
            return False

    # Helper: sudo command execution
    sudo_prefix = ['sudo', '-n']  # -n prevents password prompt

    def try_sudo(cmd_list):
        try:
            subprocess.check_call(sudo_prefix + cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    # OS detection
    is_wayland = bool(os.getenv('WAYLAND_DISPLAY'))

    try:
        # ===== WAYLAND =====
        if is_wayland:
            pics = os.path.expanduser('~/Pictures')
            before = set(os.listdir(pics)) if os.path.isdir(pics) else set()

            # 1. xdg-desktop-portal
            try:
                subprocess.run([
                    'dbus-send','--session',
                    '--dest=org.freedesktop.portal.Desktop',
                    '--type=method_call',
                    '/org/freedesktop/portal/desktop',
                    'org.freedesktop.portal.Screenshot.Screenshot',
                    'dict:string:string:()', 'string:""'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            time.sleep(1.8)
            after = set(os.listdir(pics)) if os.path.isdir(pics) else set()
            new_files = list(after - before)
            if new_files:
                latest = max([os.path.join(pics,f) for f in new_files], key=os.path.getmtime)
                os.replace(latest, output_path)
                return {'status':'success','file_path':output_path,'message':'portal'}
                sys.exit(0)

            # 2. grim
            try:
                png_bytes = subprocess.check_output(['grim','-'], stderr=subprocess.DEVNULL)
                with open(output_path,'wb') as f: f.write(png_bytes)
                return {'status':'success','file_path':output_path,'message':'grim'}
                sys.exit(0)
            except Exception:
                pass

            # 3. sudo grim
            if try_sudo(['grim', output_path]):
                return {'status':'success','file_path':output_path,'message':'sudo grim'}
                sys.exit(0)

            # 4. MSS fallback
            if try_mss():
                return {'status':'success','file_path':output_path,'message':'mss fallback'}
                sys.exit(0)

            # 5. sudo MSS
            if try_sudo([sys.executable, '-c', f'import mss; import PIL.Image; ' \
                          f'mss_instance=mss.mss(); img=mss_instance.grab(mss_instance.monitors[1]); ' \
                          f'Image.frombytes("RGB", img.size, img.rgb).save("{output_path}", "{fmt.upper()}")']):
                return {'status':'success','file_path':output_path,'message':'sudo mss'}
                sys.exit(0)

            raise RuntimeError('Wayland blocked screenshot (all methods failed)')

        # ===== X11 =====
        if try_mss():
            return {'status':'success','file_path':output_path,'message':'mss'}
            sys.exit(0)

        raise RuntimeError('Unable to capture screen (X11)')

    except Exception as e:
        return {'status':'error','file_path':'','message':str(e)}

@action(
    name="screenshot",
    description="Takes a screenshot of the agent screen.",
    platforms=["windows"],
    input_schema={
        "output_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png",
            "description": "Optional absolute file path for the screenshot. If omitted, a timestamped PNG is saved in the workspace root."
        },
        "format": {
            "type": "string",
            "example": "png",
            "description": "Image format: \"png\" or \"jpg\". Defaults to \"png\"."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success"
        },
        "file_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png"
        },
        "message": {
            "type": "string",
            "example": "Unable to capture screen."
        }
    },
    requirement=["mss", "Pillow"],
)
def screenshot_windows(input_data: dict) -> dict:
    import json, os, sys, subprocess, importlib
    from datetime import datetime

    def _ensure(pkg):
        try: importlib.import_module(pkg)
        except ImportError: subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--quiet'])
    for pkg in ('mss','Pillow'): _ensure(pkg)

    import mss
    from PIL import Image

    output_path = str(input_data.get('output_path','')).strip()
    fmt = str(input_data.get('format','png')).lower()
    if fmt not in ('png','jpg','jpeg'): fmt='png'

    if not output_path:
        root=os.getenv('AGENT_WORKSPACE_ROOT',os.getcwd())
        ts=datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_path=os.path.join(root,f'screenshot_{ts}.{fmt}')

    try:
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors)>1 else sct.monitors[0]
            shot = sct.grab(mon)
            img = Image.frombytes('RGB', shot.size, shot.rgb)
            img.save(output_path, fmt.upper())
        return {'status':'success','file_path':output_path,'message':'mss'}
    except Exception as e:
        return {'status':'error','file_path':'','message':str(e)}

@action(
    name="screenshot",
    description="Takes a screenshot of the agent screen.",
    platforms=["darwin"],
    input_schema={
        "output_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png",
            "description": "Optional absolute file path for the screenshot. If omitted, a timestamped PNG is saved in the workspace root."
        },
        "format": {
            "type": "string",
            "example": "png",
            "description": "Image format: \"png\" or \"jpg\". Defaults to \"png\"."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success"
        },
        "file_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\screenshot.png"
        },
        "message": {
            "type": "string",
            "example": "Unable to capture screen."
        }
    },
    requirement=["mss", "Pillow"],
)
def screenshot_darwin(input_data: dict) -> dict:
    import json, os, sys, subprocess, importlib
    from datetime import datetime

    def _ensure(pkg):
        try: importlib.import_module(pkg)
        except ImportError: subprocess.check_call([sys.executable,'-m','pip','install',pkg,'--quiet'])
    for pkg in ('mss','Pillow'): _ensure(pkg)

    import mss
    from PIL import Image

    output_path=str(input_data.get('output_path','')).strip()
    fmt=str(input_data.get('format','png')).lower()
    if fmt not in ('png','jpg','jpeg'): fmt='png'

    if not output_path:
        root=os.getenv('AGENT_WORKSPACE_ROOT',os.getcwd())
        ts=datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_path=os.path.join(root,f'screenshot_{ts}.{fmt}')

    # 1. Try MSS
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(mon)
            img = Image.frombytes('RGB', shot.size, shot.rgb)
            img.save(output_path, fmt.upper())
        return {'status':'success','file_path':output_path,'message':'mss'}
        sys.exit(0)
    except Exception:
        pass

    # 2. macOS native fallback
    try:
        subprocess.check_call(['screencapture', output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {'status':'success','file_path':output_path,'message':'screencapture'}
    except Exception as e:
        return {'status':'error','file_path':'','message':str(e)}