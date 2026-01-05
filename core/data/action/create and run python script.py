from core.action.action_framework.registry import action

@action(
    name="create and run python script",
    description="This action takes a single Python code snippet as input and executes it in a fresh environment with no pre-installed third-party libraries—only base Python is available. This action is intended for cases when the AI agent needs to create a one-off solution dynamically.",
    execution_mode="sandboxed",
    default=True,
    input_schema={
        "code": {
            "type": "string",
            "example": "import subprocess, sys\nsubprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'requests'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\nimport requests\nprint(requests.get('https://example.com').text)",
            "description": "The Python code snippet to execute. It must be self-contained and handle all package installations needed at runtime. The input code MUST NOT have any malicious code, the code MUST BE SANDBOXED. The code must be production code with the highest level of quality. DO NOT give any placeholder code or fabricated data. You MUST NOT handle exception with system exit. To avoid corrupting the structured action output, silence noisy installers (e.g., pip) by passing '--quiet' and redirecting stdout/stderr. The result of the code return to the agent can only be returned with 'print'."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if the script ran without errors; otherwise 'error'."
        },
        "stdout": {
            "type": "string",
            "example": "Hello, World!",
            "description": "Captured standard output from the script execution."
        },
        "stderr": {
            "type": "string",
            "example": "Traceback (most recent call last): ...",
            "description": "Captured standard error from the script execution (empty if no error)."
        },
        "message": {
            "type": "string",
            "example": "Script executed successfully.",
            "description": "A short message indicating the result of the script execution. Only present if status is 'error'."
        }
    },
    requirement=["traceback"],
    test_payload={
        "code": "import subprocess, sys\nsubprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'requests'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\nimport requests\nprint(requests.get('https://example.com').text)",
        "simulated_mode": True
    }
)
def create_and_run_python_script(input_data: dict) -> dict:
    import json
    import sys
    import subprocess
    import io
    import traceback

    code_snippet = input_data.get("code", "")

    if not code_snippet.strip():
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "message": "The 'code' field is required."
        }

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        exec_globals = {}
        exec(code_snippet, exec_globals)

        sys.stdout = original_stdout
        sys.stderr = original_stderr

        return {
            "status": "success",
            "stdout": stdout_capture.getvalue().strip(),
            "stderr": stderr_capture.getvalue().strip()
        }

    except Exception:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        return {
            "status": "error",
            "stdout": stdout_capture.getvalue().strip(),
            "stderr": stderr_capture.getvalue().strip(),
            "message": traceback.format_exc()
        }