import asyncio
import json
import os
import subprocess
import tempfile
import venv
import uuid
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Optional

from core.action.action import Action

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
            action_file = tmp / "action.py"
            action_file.write_text(
                f"""
import json
input_data = json.loads({json.dumps(json.dumps(input_data))})

# ─── USER CODE ───
{action_code}
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
    Has access to core.*, state, internals.
    """

    try:
        local_ns = {
            "input_data": input_data,
        }

        exec(action_code, local_ns, local_ns)

        return {
            "stdout": local_ns.get("output", ""),
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
        action: Action,
        input_data: dict,
        *,
        timeout: int = 1800,
    ) -> dict:
        execution_mode = getattr(action, "execution_mode", "sandboxed")

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
                    "raw_stdout": "",
                }

        else:
            raise ValueError(f"Unknown execution_mode: {execution_mode}")

        # ─── Normalize result ───
        if result["stderr"]:
            return {
                "error": result["stderr"],
                "raw_stdout": result.get("stdout", ""),
                "raw_stderr": result.get("stderr", ""), # TODO remove this after testing
            }
        return {
            "raw_stdout": result.get("stdout", ""),
        }

    async def execute_action(
        self,
        action: Action,
        input_data: dict,
    ) -> dict:
        run_id = str(uuid.uuid4())
        self._inflight[run_id] = action

        try:
            if action.action_type != "atomic":
                raise ValueError("Only atomic actions supported")

            return await self.execute_atomic_action(action, input_data)

        finally:
            self._inflight.pop(run_id, None)
