import asyncio
import importlib
import json
import os
import subprocess
import sys
import tempfile
import venv
import uuid
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, List
from core.logger import logger
from core.gui.handler import GUIHandler

# ============================================
# Global process pool (shared safely)
# ============================================

PROCESS_POOL = ProcessPoolExecutor()
THREAD_POOL = ThreadPoolExecutor(max_workers=4)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Default timeout for action execution (100 minutes, GUI mode might need more time to run)
DEFAULT_ACTION_TIMEOUT = 6000

# ============================================
# Worker: runs in a separate PROCESS
# ============================================

def _find_system_python() -> str | None:
    """
    Locate a usable system Python interpreter.

    When running inside a PyInstaller frozen exe, ``sys.executable``
    points to the bundled exe — not a real Python — so ``pip install``
    would fail.  This helper finds the real interpreter.

    On Windows the search order is ``python`` then ``python3`` because
    real CPython installers register ``python.exe`` while the
    WindowsApps ``python3.exe`` is only a Microsoft Store redirect
    stub (exit-code 9009).  Every candidate is validated with a quick
    ``--version`` call before being accepted.
    """
    import shutil

    # Not frozen → sys.executable is fine
    if not getattr(sys, "frozen", False):
        return sys.executable

    # On Windows real CPython is "python"; "python3" is often the
    # Store stub.  On Unix "python3" is the canonical name.
    if os.name == "nt":
        candidates = ("python", "python3")
    else:
        candidates = ("python3", "python")

    # Frozen → search PATH for a real Python
    for name in candidates:
        found = shutil.which(name)
        if not found:
            continue

        # Skip the WindowsApps Store stubs explicitly
        if os.name == "nt" and "WindowsApps" in found:
            logger.debug(f"[PYTHON] Skipping Windows Store stub: {found}")
            continue

        # Validate the interpreter actually works
        try:
            subprocess.check_call(
                [found, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return found
        except Exception:
            logger.debug(f"[PYTHON] Candidate '{found}' failed --version check, skipping.")
            continue

    return None


def _ensure_requirements(requirements: List[str], python_bin: str | None = None) -> None:
    """
    Install pip packages that are not yet available.

    *requirements* may contain a mix of importable module names (e.g.
    ``"DDGS"``) and pip package names (e.g. ``"duckduckgo-search"``).
    Only entries that look like valid pip package names (lowercase, may
    contain hyphens) are attempted.  The rest are silently skipped —
    they are likely class/symbol names listed for documentation only.

    Packages are always installed into the *system* Python's
    site-packages.  When running from a frozen exe, the action code
    itself will also run via the system Python (subprocess), so the
    packages are available where they're needed.

    Args:
        requirements: List from the action's ``requirement`` field.
        python_bin:   Python interpreter to use for pip.  When *None*
                      the system Python is auto-detected (handles
                      PyInstaller frozen exe).  Pass the venv python
                      path for sandboxed actions.
    """
    if not requirements:
        return

    pip_python = python_bin or _find_system_python()
    if not pip_python:
        logger.warning("[REQUIREMENTS] No Python interpreter found on PATH; cannot install packages.")
        return

    installed_any = False
    for pkg in requirements:
        pkg = pkg.strip()
        if not pkg:
            continue

        # Heuristic: skip entries that look like class names
        # (e.g. "DDGS", "ClientSession", "build") rather than pip
        # packages.  Pip packages are lowercase and may contain
        # hyphens/underscores/dots.
        if not pkg[0].islower() and "-" not in pkg:
            continue

        # Derive the importable module name for the quick check.
        # Only useful when NOT frozen (in-process imports work).
        import_name = pkg.replace("-", "_").split("[")[0]

        if not getattr(sys, "frozen", False):
            try:
                importlib.import_module(import_name)
                continue  # already installed
            except ImportError:
                pass
        else:
            # When frozen, we can't reliably import-check packages
            # destined for the system Python.  Use pip to check instead.
            try:
                subprocess.check_call(
                    [str(pip_python), "-m", "pip", "show", "--quiet", pkg],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                )
                continue  # already installed in system Python
            except Exception:
                pass

        try:
            subprocess.check_call(
                [str(pip_python), "-m", "pip", "install", "--quiet", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            installed_any = True
            logger.info(f"[REQUIREMENTS] Installed '{pkg}'")
        except Exception as e:
            logger.warning(f"[REQUIREMENTS] Failed to install '{pkg}': {e}")

    # Refresh import caches so in-process exec() can find new packages.
    if installed_any:
        importlib.invalidate_caches()


def _suppress_worker_stdio():
    """
    Redirect OS-level stdout/stderr to devnull in the worker process.

    This prevents venv.EnvBuilder, ensurepip, and other subprocess calls
    from writing to the inherited terminal, which would corrupt the
    Textual TUI display.

    Returns (saved_stdout_fd, saved_stderr_fd) for later restoration.
    """
    import sys as _sys
    _sys.stdout.flush()
    _sys.stderr.flush()
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    return saved_stdout, saved_stderr


def _restore_worker_stdio(saved_stdout, saved_stderr):
    """Restore stdout/stderr from saved file descriptors."""
    os.dup2(saved_stdout, 1)
    os.dup2(saved_stderr, 2)
    os.close(saved_stdout)
    os.close(saved_stderr)


def _atomic_action_venv_process(
    action_code: str,
    input_data: dict,
    timeout: int,
    mode: str,
    requirements: List[str] = None,
) -> dict:
    """
    Executes an action inside an ephemeral virtual environment.
    Runs in a SEPARATE PROCESS via ProcessPoolExecutor.

    stdout/stderr are suppressed at the OS level so that venv creation
    and other subprocess calls do not corrupt the parent's TUI.
    """
    # GUI mode - in a Docker container
    if mode == "GUI":
        return GUIHandler.execute_action(GUIHandler.TARGET_CONTAINER, action_code, input_data, mode)

    # Suppress worker stdout/stderr to prevent TUI corruption
    saved_stdout, saved_stderr = _suppress_worker_stdio()

    # Sandboxed mode - NOT in a Docker container
    try:
        with tempfile.TemporaryDirectory(prefix="action_venv_") as tmpdir:
            tmp = Path(tmpdir)

            # ─── Create virtual environment ───
            venv_dir = tmp / "venv"
            venv.EnvBuilder(with_pip=True).create(venv_dir)

            python_bin = (
                venv_dir / "Scripts" / "python.exe"
                if os.name == "nt"
                else venv_dir / "bin" / "python"
            )

            # ─── Install requirements in the venv ───
            # Installation failures are logged but don't block execution.
            # If a package is truly needed, the action will fail with an import error.
            if requirements:
                for pkg in requirements:
                    try:
                        pip_result = subprocess.run(
                            [str(python_bin), "-m", "pip", "install", "--quiet", pkg],
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        if pip_result.returncode != 0:
                            stderr_lower = pip_result.stderr.lower()
                            if "no matching distribution" in stderr_lower or "could not find" in stderr_lower:
                                pass  # Not a real package, skip silently
                            else:
                                # Log but continue - action will fail with import error if truly needed
                                print(f"Warning: Could not install '{pkg}': {pip_result.stderr.strip()[:100]}", file=sys.stderr)
                    except subprocess.TimeoutExpired:
                        print(f"Warning: Installation timed out for '{pkg}'", file=sys.stderr)
                    except Exception as e:
                        print(f"Warning: Error installing '{pkg}': {e}", file=sys.stderr)

            # ─── Write action script ───
            # We inject input_data as a global so the action code can access it
            action_file = tmp / "action.py"
            action_file.write_text(
                f"""
import json
import sys

input_data = json.loads({json.dumps(json.dumps(input_data))})

# ─── USER CODE ───
{action_code}

# ─── Find and call the function ───
func = None
local_vars = dict(locals())
for name, obj in local_vars.items():
    if callable(obj) and not name.startswith('_') and name not in ('input_data', 'json', 'sys'):
        func = obj
        break

if func is None:
    # Fallback: check if output variable was set (legacy behavior)
    if 'output' in local_vars:
        print(local_vars['output'])
        sys.exit(0)
    else:
        sys.exit(1)

# Call the function and print result as JSON
try:
    result = func(input_data)
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(str(result))
except Exception as e:
    import traceback
    print("Execution failed: " + str(e) + "\\n" + traceback.format_exc(), file=sys.stderr)
    sys.exit(1)
""",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [str(python_bin), str(action_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "returncode": proc.returncode,
            }

    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Execution timed out", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": f"Execution failed: {e}", "returncode": -1}
    finally:
        _restore_worker_stdio(saved_stdout, saved_stderr)

def _atomic_action_internal_subprocess(
    action_code: str,
    input_data: dict,
    python_bin: str,
    timeout: int = 300,
) -> dict:
    """
    Run an 'internal' action via the system Python as a subprocess.

    Used when running from a PyInstaller frozen exe: C-extension packages
    (like lxml) installed for the system Python cannot be loaded into
    the frozen runtime.  Running the action in the system Python avoids
    this incompatibility.
    """
    with tempfile.TemporaryDirectory(prefix="action_internal_") as tmpdir:
        tmp = Path(tmpdir)
        action_file = tmp / "action.py"
        action_file.write_text(
            f"""
import json
import sys

input_data = json.loads({json.dumps(json.dumps(input_data))})

# ─── USER CODE ───
{action_code}

# ─── Find and call the function ───
func = None
local_vars = dict(locals())
for name, obj in local_vars.items():
    if callable(obj) and not name.startswith('_') and name not in ('input_data', 'json', 'sys'):
        func = obj
        break

if func is None:
    if 'output' in local_vars:
        out = local_vars['output']
        print(json.dumps(out, ensure_ascii=False) if isinstance(out, dict) else str(out))
        sys.exit(0)
    else:
        print(json.dumps({{"status": "error", "message": "No callable function found in action code"}}))
        sys.exit(1)

try:
    result = func(input_data)
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(str(result))
except Exception as e:
    import traceback
    print(json.dumps({{"status": "error", "message": str(e)}}))
    sys.exit(1)
""",
            encoding="utf-8",
        )

        try:
            proc = subprocess.run(
                [python_bin, str(action_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if proc.returncode != 0:
                err = proc.stderr.strip() or f"Action exited with code {proc.returncode}"
                return {"status": "error", "message": err}

            stdout = proc.stdout.strip()
            if not stdout:
                return {"status": "success", "output": ""}

            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"status": "success", "output": stdout}

        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Execution timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


def _atomic_action_internal(
    action_name: str,
    action_code: str,
    input_data: dict,
    mode: str,
) -> dict:
    """
    Executes an internal action in-process.
    Requirements are pre-installed at startup via install_all_action_requirements().
    """
    try:
        # Execute the function definition
        if mode == "GUI" and action_name != "switch to CLI mode":
            result = GUIHandler.execute_action(GUIHandler.TARGET_CONTAINER, action_code, input_data, mode)
            return result
        else:
            import json
            import inspect

            local_ns = {
                "input_data": input_data,
                "json": json,
                "asyncio": asyncio,
            }
            pre_exec_keys = set(local_ns.keys())

            exec(action_code, local_ns, local_ns)

            function_to_call = None
            for key, value in local_ns.items():
                if key not in pre_exec_keys and key != '__builtins__' and inspect.isfunction(value):
                    function_to_call = value
                    logger.debug(f"Found action function: '{key}'")
                    break
            
            if function_to_call is None:
                 raise ValueError("The action_code string did not define a callable Python function.")
            
            execution_result = function_to_call(input_data)

            return execution_result

    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================
# Async executor (awaitable, non-blocking)
# ============================================

class ActionExecutor:
    def __init__(self):
        self._inflight = {}

    async def execute_atomic_action(
        self,
        action: Any, # Usually 'Action'
        input_data: dict,
        *,
        timeout: int = None,
    ) -> dict:
        execution_mode = getattr(action, "execution_mode", "sandboxed")
        mode = getattr(action, "mode", "CLI")
        # Use action's timeout, then parameter, then default
        effective_timeout = getattr(action, "timeout", None) or timeout or DEFAULT_ACTION_TIMEOUT
        logger.debug(f"[EXECTION CODE] {action.code}")

        frozen = getattr(sys, "frozen", False)

        # Pre-install declared pip requirements
        requirements = getattr(action, "requirements", [])
        if requirements and execution_mode == "internal":
            _ensure_requirements(requirements)

        if execution_mode == "internal":
            # Requirements are pre-installed at startup, no need to pass them
            loop = asyncio.get_running_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        THREAD_POOL,
                        _atomic_action_internal,
                        action.name,
                        action.code,
                        input_data,
                        mode,
                    ),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                return {"status": "error", "message": f"Execution timed out after {effective_timeout}s while running internal action."}

        elif execution_mode == "sandboxed":
            # Sandboxed mode needs requirements since it creates a fresh venv each time
            requirements = getattr(action, "requirements", [])
            loop = asyncio.get_running_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        PROCESS_POOL,
                        _atomic_action_venv_process,
                        action.code,
                        input_data,
                        effective_timeout,
                        mode,
                        requirements,
                    ),
                    timeout=effective_timeout + 5,
                )
            except asyncio.TimeoutError:
                return {"status": "error", "message": f"Execution timed out after {effective_timeout}s while running sandboxed action."}
        else:
            raise ValueError(f"Unknown execution_mode: {execution_mode}")

        return result

    async def execute_action(
        self,
        action: Any,
        input_data: dict,
    ) -> dict:
        run_id = str(uuid.uuid4())
        self._inflight[run_id] = action

        try:
            if getattr(action, "action_type", "atomic") != "atomic":
                raise ValueError("Only atomic actions supported")

            return await self.execute_atomic_action(action, input_data)

        finally:
            self._inflight.pop(run_id, None)