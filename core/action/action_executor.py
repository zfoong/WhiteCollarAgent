import asyncio
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

def _atomic_action_venv_process(
    action_code: str,
    input_data: dict,
    timeout: int,
    mode: str,
    requirements: List[str] = None,
) -> dict:
    """
    Executes an action inside an ephemeral virtual environment.
    Runs in a SEPARATE PROCESS.
    """
    # GUI mode - in a Docker container
    if mode == "GUI":
        return GUIHandler.execute_action(GUIHandler.TARGET_CONTAINER, action_code, input_data, mode)

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
                [python_bin, str(action_file)],
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