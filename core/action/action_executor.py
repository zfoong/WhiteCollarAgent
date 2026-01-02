import asyncio
import json
import os
import subprocess
import tempfile
import venv
import uuid
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import Any
from core.logger import logger

# ============================================
# Global process pool (shared safely)
# ============================================

PROCESS_POOL = ProcessPoolExecutor()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ============================================
# Worker: runs in a separate PROCESS
# ============================================

def _atomic_action_venv_process(
    action_code: str,
    input_data: dict,
    timeout: int,
) -> dict:
    """
    Executes an action inside an ephemeral virtual environment.
    Runs in a SEPARATE PROCESS.
    """
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
    action_code: str,
    input_data: dict,
) -> dict:
    """
    Executes an internal action in-process.
    """
    try:
        import json
        local_ns = {
            "input_data": input_data,
            "json": json,
            "asyncio": asyncio,
        }

        # Execute the function definition
        exec(action_code, local_ns, local_ns)
        
        # Find the function that was defined (it should be the only callable in local_ns)
        func = None
        for name, obj in local_ns.items():
            if callable(obj) and not name.startswith('_') and name != 'input_data':
                func = obj
                break
        
        if func is None:
            # Fallback: check if output variable was set (legacy behavior)
            if "output" in local_ns:
                return {
                    "stdout": local_ns.get("output", ""),
                    "stderr": "",
                    "returncode": 0,
                }
            return {
                "stdout": "",
                "stderr": "Internal execution failed: No function found in action code",
                "returncode": -1,
            }
        
        # Call the function and capture its return value
        result = func(input_data)
        
        # Convert result to JSON string for stdout
        if isinstance(result, dict):
            output_str = json.dumps(result, ensure_ascii=False)
        else:
            output_str = str(result)
        
        return {
            "stdout": output_str,
            "stderr": "",
            "returncode": 0,
        }

    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Internal execution failed: {e}",
            "returncode": -1,
        }

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
        timeout: int = 1800,
    ) -> dict:
        execution_mode = getattr(action, "execution_mode", "sandboxed")
        logger.debug(f"[EXECTION CODE] {action.code}")

        if execution_mode == "internal":
            result = _atomic_action_internal(action.code, input_data)

        elif execution_mode == "sandboxed":
            loop = asyncio.get_running_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        PROCESS_POOL,
                        _atomic_action_venv_process,
                        action.code,
                        input_data,
                        timeout,
                    ),
                    timeout=timeout + 5,
                )
            except asyncio.TimeoutError:
                return {
                    "error": f"Execution timed out after {timeout}s while running sandboxed action.",
                    "status": "error"
                }
        else:
            raise ValueError(f"Unknown execution_mode: {execution_mode}")

        # ─── Parse and Normalize Result ───

        # 1. Handle hardware/process level errors
        if result.get("returncode", 0) != 0:
            return {
                "error": result.get("stderr") or "Unknown execution error",
                "raw_stdout": result.get("stdout", ""),
                "status": "error"
            }

        raw_output = result.get("stdout", "").strip()

        # 2. Attempt to parse the stdout as JSON
        if raw_output:
            try:
                # Both internal and sandboxed actions are designed to return JSON strings
                parsed_data = json.loads(raw_output)
                
                # If the parsed data is already a dict, return it directly
                if isinstance(parsed_data, dict):
                    return parsed_data
                
                # If it's a valid JSON but not a dict (like a string/bool), wrap it
                return {"raw_stdout": parsed_data, "status": "success"}
                
            except json.JSONDecodeError:
                # Fallback if the script output text that wasn't JSON
                return {
                    "raw_stdout": raw_output,
                    "error": "Output was not valid JSON",
                    "status": "partial_success"
                }
        
        # 3. Handle empty output
        if result.get("stderr"):
            return {"error": result["stderr"], "status": "error"}
            
        return {"status": "success", "message": "Action completed with no output."}

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