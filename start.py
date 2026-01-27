#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import shutil
import shlex
import time
import urllib.request
import urllib.error
from typing import Tuple, Optional, Dict, Any

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# --- Configuration ---
CONFIG_FILE = "config.json"
MAIN_APP_SCRIPT = "main.py"
YML_FILE = "environment.yml"
REQUIREMENTS_FILE = "requirements.txt"

OMNIPARSER_REPO_URL = "https://github.com/zfoong/OmniParser_CraftOS.git"
OMNIPARSER_BRANCH = "CraftOS"
OMNIPARSER_ENV_NAME = "omni"
OMNIPARSER_SERVER_URL = os.getenv(
    "OMNIPARSER_BASE_URL",
    "http://localhost:7861",
)
# NEW: Marker file to indicate OmniParser env is fully set up
OMNIPARSER_MARKER_FILE = ".omniparser_setup_complete_v1"

# ==========================================
# HELPER FUNCTIONS (Config & System Internals)
# ==========================================
def _wrap_windows_bat(cmd_list: list[str]) -> list[str]:
    if sys.platform != "win32":
        return cmd_list
    exe = shutil.which(cmd_list[0])
    if exe and exe.lower().endswith((".bat", ".cmd")):
        # /d disables AutoRun (more predictable); /c runs then exits
        return ["cmd.exe", "/d", "/c", exe] + cmd_list[1:]
    return cmd_list
    
def load_config() -> Dict[str, Any]:
    """Reads the existing config file safely."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Warning: {CONFIG_FILE} is corrupted. Starting with empty config.")
        return {}

def save_config_value(key: str, value: Any) -> None:
    """Updates a single key in the config file."""
    config = load_config()
    config[key] = value
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
            print(f"ℹ️ Updated config.json: Set '{key}' to '{value}'")
    except IOError as e:
        print(f"⚠️ Warning: Could not save config file: {e}")

def run_command(cmd_list: list[str], cwd: Optional[str] = None, check: bool = True, capture: bool = False, env_extras: Dict[str, str] = None) -> subprocess.CompletedProcess:
    """
    Centralized helper to run subprocesses robustly (BLOCKING).
    Waits for command to finish.
    """
    cmd_list = _wrap_windows_bat(cmd_list)
    my_env = os.environ.copy()
    if env_extras:
        my_env.update(env_extras)
    
    my_env["PYTHONUNBUFFERED"] = "1"

    kwargs = {}
    if capture:
        kwargs['capture_output'] = True
        kwargs['text'] = True
    else:
        kwargs['stdout'] = sys.stdout
        kwargs['stderr'] = sys.stderr
        print(f"Wait > Executing: {' '.join(cmd_list)}", flush=True)

    try:
        result = subprocess.run(
            cmd_list, 
            cwd=cwd, 
            check=check,
            env=my_env,
            **kwargs
        )
        return result
    except subprocess.CalledProcessError as e:
        if capture:
            print(f"\n❌ Error running command:\nCommand: {' '.join(cmd_list)}")
            print(f"STDOUT:\n{e.stdout}")
            print(f"STDERR:\n{e.stderr}")
        else:
             print(f"\n❌ Command failed (see output above).")
        print("Exiting setup script due to error.")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n❌ Executable not found: {e.filename}")
        sys.exit(1)

def launch_background_command(cmd_list: list[str], cwd: Optional[str] = None, env_extras: Dict[str, str] = None, silence_output: bool = False) -> Optional[subprocess.Popen]:
    """
    NEW HELPER: Launches a process in the background and moves on immediately (NON-BLOCKING).
    Using Popen instead of run.
    """
    cmd_list = _wrap_windows_bat(cmd_list)
    my_env = os.environ.copy()
    if env_extras: my_env.update(env_extras)
    my_env["PYTHONUNBUFFERED"] = "1"

    if silence_output:
         stdout_target = subprocess.DEVNULL
         stderr_target = subprocess.DEVNULL
         print(f"ℹ️ Launching background process (silent): {' '.join(cmd_list)}")
    else:
         stdout_target = sys.stdout
         stderr_target = sys.stderr
         print(f"ℹ️ Launching background process (streaming): {' '.join(cmd_list)}", flush=True)

    kwargs = {}
    if sys.platform != "win32":
         kwargs['start_new_session'] = True

    try:
        process = subprocess.Popen(
            cmd_list,
            cwd=cwd,
            env=my_env,
            stdout=stdout_target,
            stderr=stderr_target,
            **kwargs
        )
        print(f"✅ Process launched in background with PID: {process.pid}. Moving on immediately.")
        return process
        
    except FileNotFoundError as e:
        print(f"⚠️ Cannot launch background process. Executable not found: {e.filename}")
        return None
    except Exception as e:
         print(f"⚠️ Error launching background process: {e}")
         return None

def wait_for_server_health(url: str, timeout_seconds: int = 180) -> bool:
    """
    Repeatedly polls a HTTP URL until it returns a 200 OK status or times out.
    """
    print(f"⏳ Waiting for server at {url} to become ready (Timeout: {timeout_seconds}s)...", end="", flush=True)
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=1) as response:
                if response.status == 200:
                    print(" ✅ Ready!")
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        except Exception as e:
            print(f"\n⚠️ Unexpected error checking server health: {e}")

        print(".", end="", flush=True)
        time.sleep(1)

    print(f"\n❌ Error: Server at {url} did not start within {timeout_seconds} seconds.")
    return False


# ==========================================
# HELPER FUNCTIONS (Main Environment Setup)
# ==========================================
def initialize_environment(args: set[str]) -> Tuple[bool, bool]:
    """Parses flags. Returns (force_cpu, fast_mode)."""
    flag_ignore_omniparse = "--no-omniparser" in args
    os.environ["USE_OMNIPARSER"] = str(not flag_ignore_omniparse)
    print(f"[*] Using Omniparser: {os.getenv('USE_OMNIPARSER')}")
    
    flag_ignore_conda = "--no-conda" in args
    os.environ["USE_CONDA"] = str(not flag_ignore_conda)
    print(f"[*] Using Conda base env: {os.getenv('USE_CONDA')}")

    force_cpu = "--cpu-only" in args
    if force_cpu:
        print("[*] CPU-Only mode requested for installations.")

    # NEW: Detect fast mode flag
    fast_mode = "--fast" in args
    if fast_mode:
        print("[*] FAST MODE ENABLED: Skipping heavy update checks.")
    
    return force_cpu, fast_mode

def is_conda_installed_robust() -> Tuple[bool, str, Optional[str]]:
    """
    Checks if Conda is installed and returns its status, reason, and base path.
    """
    conda_exe = shutil.which("conda")
    if conda_exe:
        conda_base_path = os.path.dirname(os.path.dirname(conda_exe))
        return True, f"Found executable at {conda_exe}", conda_base_path

    if sys.platform == "win32":
        print("... Standard check failed on Windows. Attempting to locate hidden installation ...")
        current_python_dir = os.path.dirname(sys.executable)
        potential_base_paths = [
            os.path.dirname(current_python_dir), 
            os.path.dirname(os.path.dirname(current_python_dir))
        ]
        
        for base_path in potential_base_paths:
            activate_bat = os.path.join(base_path, "Scripts", "activate.bat")
            condabin_bat = os.path.join(base_path, "condabin", "conda.bat")
            if os.path.exists(activate_bat) or os.path.exists(condabin_bat):
                 return True, f"Found likely base installation at {base_path}", base_path
                 
    return False, "Not found in PATH or relative to current Python installation", None

def get_env_name_from_yml(yml_path: str = YML_FILE) -> str:
    try:
        with open(yml_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("name:"): return stripped.split(":", 1)[1].strip().strip("'").strip('"')
    except FileNotFoundError: 
        print(f"❌ Error: {yml_path} not found.")
        sys.exit(1)
    print(f"❌ Error: Could not find 'name:' in {yml_path}.")
    sys.exit(1)
   
def setup_conda_environment(env_name: str, yml_path: str = YML_FILE):
    print(f"Please wait, creating/updating Conda environment: '{env_name}'...")
    run_command(["conda", "env", "update", "-f", yml_path, "--prune"])
    print("✅ Conda environment installation command finished successfully.")

def verify_conda_env_ready(env_name: str):
    print(f"Attempting to verify environment '{env_name}' is active and working...")
    verification_cmd = ["conda", "run", "-n", env_name, "python", "-c", "import sys; print(f'SUCCESS: Verified {sys.executable}')"]
    run_command(verification_cmd, capture=True)
    print(f"✅ Verification successful. The environment is ready.")
    return True

def setup_global_environment(requirements_file: str = REQUIREMENTS_FILE):
    print("Setting up global environment using pip...")
    if not os.path.exists(requirements_file): print(f"❌ Error: {requirements_file} not found."); sys.exit(1)
    run_command([sys.executable, "-m", "pip", "install", "-r", requirements_file])
    print("✅ Pip install finished successfully.")

# ==========================================
# OPTIMIZED OMNIPARSER SETUP (WITH GLOBAL FALLBACK)
# ==========================================
def setup_omniparser_local(force_cpu: bool, fast_mode: bool):
    print("\n======================================")
    print(" Setting up OmniParser locally")
    print("======================================")

    # Detect mode based on earlier checks
    use_conda_omni = os.getenv('USE_CONDA') == "True"
    mode_str = f"Conda Env '{OMNIPARSER_ENV_NAME}'" if use_conda_omni else "Global Python (Pip)"
    print(f"ℹ️ OmniParser Installation Mode: {mode_str}")

    if not shutil.which("git"):
        print("❌ Error: 'git' is not installed or in the PATH. Cannot clone OmniParser.")
        sys.exit(1)

    # 1. Config & Path Management
    config = load_config()
    repo_path = config.get("omniparser_repo_path")

    if not repo_path:
        repo_path = os.path.abspath("OmniParser_CraftOS")
        save_config_value("omniparser_repo_path", repo_path)
    else:
        repo_path = os.path.abspath(repo_path)

    # --------------------------------------------------------------------------
    # NEW HELPER: Abstracted command execution for OmniParser context
    # --------------------------------------------------------------------------
    def run_omni_cmd(cmd_list: list[str], work_dir: str = repo_path, capture_output: bool = False, env_extras: Dict[str, str] = None):
        """Runs a command either in the 'omni' conda env OR the global env based on mode."""
        if use_conda_omni:
            # Wraps command to run inside the 'omni' conda environment
            full_cmd = ["conda", "run", "-n", OMNIPARSER_ENV_NAME] + cmd_list
            run_command(full_cmd, cwd=work_dir, capture=capture_output, env_extras=env_extras)
        else:
            # Runs command globally, ensuring we use the current python interpreter
            final_cmd = []
            if cmd_list[0] == "python":
                # Replace generic 'python' with the specific current interpreter path
                final_cmd = [sys.executable] + cmd_list[1:]
            elif cmd_list[0] == "pip":
                 # Best practice for global pip installs: python -m pip
                final_cmd = [sys.executable, "-m", "pip"] + cmd_list[1:]
            else:
                # Run other commands (like 'hf') directly
                final_cmd = cmd_list
            
            # Ensure local bin paths (like where 'hf' might install) are in PATH for global mode
            local_env = env_extras.copy() if env_extras else {}
            if sys.platform != "win32":
                 user_base = subprocess.run([sys.executable, "-m", "site", "--user-base"], capture_output=True, text=True).stdout.strip()
                 local_bin = os.path.join(user_base, 'bin')
                 local_env["PATH"] = f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}"

            run_command(final_cmd, cwd=work_dir, capture=capture_output, env_extras=local_env)
    # --------------------------------------------------------------------------


    # --- STEP 1: Git Operations ---
    print(f"\n--- STEP 1: Checking OmniParser Repository ({repo_path}) ---")
    if os.path.exists(repo_path):
        if not fast_mode:
             print(f"ℹ️ Directory exists. Checking for updates on branch '{OMNIPARSER_BRANCH}'...")
             run_command(["git", "-C", repo_path, "pull"])
        else:
             print("ℹ️ Repo exists. Skipping update check (--fast).")
    else:
        print(f"ℹ️ Cloning OmniParser ({OMNIPARSER_BRANCH} branch)...")
        run_command(["git", "clone", "-b", OMNIPARSER_BRANCH, OMNIPARSER_REPO_URL, repo_path])
        print("✅ Clone successful.")

    # --- OPTIMIZATION: Check for Marker File ---
    marker_path = os.path.join(repo_path, OMNIPARSER_MARKER_FILE)
    installation_needed = True

    if os.path.exists(marker_path):
        print(f"\n✅ Found completed installation marker ({OMNIPARSER_MARKER_FILE}).")
        print("ℹ️ Skipping environment creation and package installation steps.")
        installation_needed = False
    elif fast_mode:
        print(f"\n⚠️ '--fast' specified but marker file not found. Forcing installation steps.")

    if installation_needed:
        # --- STEP 2: Environment Creation (Conda Only) ---
        if use_conda_omni:
            print(f"\n--- STEP 2: Creating Conda Environment '{OMNIPARSER_ENV_NAME}' ---")
            # Using 'create' will fail fast if it already exists, which is okay.
            try:
                 run_command(["conda", "create", "-n", OMNIPARSER_ENV_NAME, "python=3.10", "-y"], capture=True)
                 print(f"✅ Environment created.")
            except Exception:
                 print(f"ℹ️ Environment '{OMNIPARSER_ENV_NAME}' likely exists. Proceeding.")
        else:
             print(f"\n--- STEP 2: Skipping Conda Env creation (Using Global Pip) ---")
             print(f"ℹ️ Installing packages directly into: {sys.executable}")
             # Ensure pip is up to date globally first
             run_omni_cmd(["pip", "install", "--upgrade", "pip"])


        # --- STEP 3: PyTorch Installation (SLOW) ---
        print(f"\n--- STEP 3: Installing PyTorch and core dependencies (This takes time) ---")
        
        if use_conda_omni:
            # --- CONDA PYTORCH INSTALL ---
            if force_cpu:
                print("MODE: CPU Only (Conda)")
                run_omni_cmd(["conda", "install", "pytorch", "torchvision", "torchaudio", "cpuonly", "-c", "pytorch", "-y"])
            else:
                print("MODE: GPU CUDA 12.1 (Conda)")
                run_omni_cmd(["conda", "install", "pytorch", "torchvision", "torchaudio", "pytorch-cuda=12.1", "-c", "pytorch", "-c", "nvidia", "-y"])
        else:
            # --- PIP PYTORCH INSTALL (Global) ---
            # Note: We use standard pip commands from pytorch.org URLs
            if force_cpu:
                print("MODE: CPU Only (Pip)")
                # --extra-index-url is often safer than --index-url so standard packages aren't blocked
                run_omni_cmd(["pip", "install", "torch", "torchvision", "torchaudio", "--extra-index-url", "https://download.pytorch.org/whl/cpu"])
            else:
                print("MODE: GPU CUDA 12.1 (Pip)")
                # Using the cu121 index for CUDA 12.1 support matching the conda target
                run_omni_cmd(["pip", "install", "torch", "torchvision", "torchaudio", "--extra-index-url", "https://download.pytorch.org/whl/cu121"])


        # --- STEP 4: Pip Installations (SLOW) ---
        print(f"\n--- STEP 4: Installing requirements ---")
        # Note: mkl might not be strictly necessary for pip/global depending on how numpy/torch were built, but including for consistency.
        deps_to_install = ["mkl==2024.0", "sympy==1.13.1", "transformers==4.51.0", "huggingface_hub[cli]", "hf_transfer"]
        run_omni_cmd(["pip", "install"] + deps_to_install)
        
        req_txt_path = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(req_txt_path):
             print("Installing from requirements.txt...")
             run_omni_cmd(["pip", "install", "-r", "requirements.txt"])
        else:
             print(f"⚠️ Warning: {req_txt_path} not found. Skipping.")

        # --- Create Marker File on Success ---
        print(f"✅ Installation steps complete. Creating marker file: {OMNIPARSER_MARKER_FILE}")
        with open(marker_path, 'w') as f:
             f.write(f"Setup completed on {time.ctime()} using mode: {mode_str}\n")

    # --- STEP 5: Model Weights Download (Optimized by existence check) ---
    print(f"\n--- STEP 5: Checking model weights ---")
    files_to_download = [
        {"file": "icon_detect/train_args.yaml", "local_path": "icon_detect/train_args.yaml"},
        {"file": "icon_detect/model.pt", "local_path": "icon_detect/model.pt"},
        {"file": "icon_detect/model.yaml", "local_path": "icon_detect/model.yaml"},
        {"file": "icon_caption/config.json", "local_path": "icon_caption_florence/config.json"},
        {"file": "icon_caption/generation_config.json", "local_path": "icon_caption_florence/generation_config.json"},
        {"file": "icon_caption/model.safetensors", "local_path": "icon_caption_florence/model.safetensors"}
    ]
    
    weights_dir = os.path.join(repo_path, "weights")
    os.makedirs(os.path.join(weights_dir, "icon_detect"), exist_ok=True)
    os.makedirs(os.path.join(weights_dir, "icon_caption_florence"), exist_ok=True)

    hf_env_extras = {"HF_HUB_ENABLE_HF_TRANSFER": "1"}

    for file_info in files_to_download:
        local_dest_path = os.path.join(weights_dir, file_info['local_path'])
        if os.path.exists(local_dest_path):
             continue

        print(f"Downloading missing file: {file_info['file']}")
        # Use the abstracted helper to run 'hf download'
        # Note: In global mode, 'hf' must be in the PATH (installed by huggingface_hub[cli])
        download_cmd = ["hf", "download", "microsoft/OmniParser-v2.0", file_info['file'], "--local-dir", "weights"]
        run_omni_cmd(download_cmd, work_dir=repo_path, capture_output=True, env_extras=hf_env_extras)

    # --- STEP 6: File Rearrangement (Fast) ---
    print(f"\n--- STEP 6: Finalizing Setup ---")
    src_caption_dir = os.path.join(weights_dir, "icon_caption")
    dst_caption_dir = os.path.join(weights_dir, "icon_caption_florence")

    if os.path.exists(src_caption_dir):
        if os.path.exists(dst_caption_dir):
            shutil.rmtree(dst_caption_dir)
        shutil.move(src_caption_dir, dst_caption_dir)
        print(f"Moved weights/icon_caption to weights/icon_caption_florence")

    # --- STEP 7: Launch Server ---
    print("\n-------------------------------------------------")
    print(f"🚀 Launching Gradio Demo ({mode_str}) in background...")
    
    # Prepare the launch command based on the mode
    if use_conda_omni:
        run_gradio_command = ["conda", "run", "-n", OMNIPARSER_ENV_NAME, "python", "-u", "-m", "gradio_demo"]
    else:
        # Global mode: use the current executable directly
        run_gradio_command = [sys.executable, "-u", "-m", "gradio_demo"]
    
    # Launch in background so we can check its health
    launch_background_command(run_gradio_command, cwd=repo_path, silence_output=False)

    # 8. Wait for server and set Environment Variable
    if wait_for_server_health(OMNIPARSER_SERVER_URL, timeout_seconds=180):
        os.environ["OMNIPARSER_BASE_URL"] = OMNIPARSER_SERVER_URL
        print(f"✅ OmniParser local setup complete.")
        print(f"Set OMNIPARSER_BASE_URL = {OMNIPARSER_SERVER_URL}")
        print("======================================\n")
    else:
         print("\n❌ CRITICAL ERROR: OmniParser server failed to start.")
         print("Please check the console output above for errors from the background process.")
         sys.exit(1)

# =========================================
# NEW LAUNCHER: SEPARATE MAXIMIZED TERMINAL
# =========================================
def launch_in_new_terminal(conda_env_name: Optional[str] = None, conda_base_path: Optional[str] = None):
    abs_main_script_path = os.path.abspath(MAIN_APP_SCRIPT)
    if not os.path.exists(abs_main_script_path):
        print(f"❌ Error: The main application script was not found at: {abs_main_script_path}")
        sys.exit(1)

    # Add --cpu-only and --fast to flags to ignore when passing to main.py
    setup_flags = {"--no-conda", "--no-omniparser", "--cpu-only", "--fast"}
    pass_through_args = [arg for arg in sys.argv[1:] if arg not in setup_flags]
    current_os = sys.platform

    print("-------------------------------------------------")
    print(f"🚀 Setting up launch command for OS: {current_os}")
    print("-------------------------------------------------")

    # Variable to hold the running subprocess handle
    process: Optional[subprocess.Popen] = None

    if current_os == "win32":
        import subprocess

        workdir = os.path.dirname(abs_main_script_path)
        use_conda = bool(conda_env_name and os.getenv("USE_CONDA") == "True" and conda_base_path)

        launcher_cmd_path = os.path.join(workdir, "_launch_agent.cmd")

        if use_conda:
            conda_bat = os.path.join(conda_base_path, "condabin", "conda.bat")
            if not os.path.exists(conda_bat):
                conda_bat = "conda"

            cmd_list = [conda_bat, "run", "--no-capture-output", "-n", conda_env_name, "python", "-u", abs_main_script_path] + pass_through_args
            run_line = "call " + subprocess.list2cmdline(cmd_list)
        else:
            cmd_list = [sys.executable, "-u", abs_main_script_path] + pass_through_args
            run_line = subprocess.list2cmdline(cmd_list)

        lines = [
            "@echo on",
            f'cd /d "{workdir}"',
            "echo --- Terminal Started ---",
            "echo CWD: %CD%",
            "set PYTHONUNBUFFERED=1",
            "echo --- Launching main.py ---",
            run_line,
            "echo.",
            "echo Exit code: %ERRORLEVEL%",
            "echo.",
            "pause",
        ]

        with open(launcher_cmd_path, "w", encoding="utf-8") as f:
            f.write("\r\n".join(lines) + "\r\n")

        print("Launching Windows command prompt in a new window...")

        cmd_to_run = f'call {launcher_cmd_path}'
        process = subprocess.Popen(
            ["cmd.exe", "/d", "/k", cmd_to_run],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    # === Linux & macOS Implementation ===
    else:
        import subprocess
        python_cmd_string = shlex.join(["python", "-u", abs_main_script_path] + pass_through_args)
        shell_commands = []
        shell_commands.append('echo "--- Terminal Started ---"')

        use_conda = (conda_env_name and os.getenv('USE_CONDA') == "True" and conda_base_path)
        
        if use_conda:
            print(f"ℹ️ Configuring shell to activate conda environment: '{conda_env_name}'")
            conda_sh_path = os.path.join(conda_base_path, "etc", "profile.d", "conda.sh")
            if os.path.exists(conda_sh_path):
                shell_commands.append(f". '{conda_sh_path}'")
            shell_commands.append(f"conda activate '{conda_env_name}' || echo '⚠️ Conda activation failed, attempting to run in current env...'")
        else:
             print("ℹ️ Using global python environment.")

        shell_commands.append('echo "--- Launching main.py ---"')
        shell_commands.append(python_cmd_string)
        shell_commands.append('APP_EXIT_CODE=$?')
        shell_commands.append('if [ $APP_EXIT_CODE -ne 0 ]; then echo -e "\n❌ Process exited with error code $APP_EXIT_CODE"; fi')
        shell_commands.append('echo "\n--- Session Finished ---"')

        full_shell_cmd_string = "; ".join(shell_commands)

        if current_os == "darwin":
            # NOTE: macOS AppleScript launch is inherently asynchronous.
            # It is very difficult to block this Python script until the macOS Terminal window closes.
            # This part will launch the window and continue immediately.
            print("ℹ️ Launching macOS Terminal...")
            applescript = f'tell application "Terminal" to do script "{full_shell_cmd_string}" activate'
            subprocess.run(["osascript", "-e", applescript], check=True)
            print("⚠️ Note on macOS: This setup script will exit while the new Terminal window remains open.")

        elif current_os.startswith("linux"):
            terminals = [
                # term_bin, exec_flag, list_of_extra_flags
                ("gnome-terminal", "--", ["--wait", "--maximize"]),
                ("konsole", "-e", ["--nofork", "--maximize"]),
                ("xfce4-terminal", "-x", ["--disable-server", "--maximize"]),
                ("terminator", "-x", ["-u", "-m"]),
                ("xterm", "-e", []), 
            ]
            terminal_found = False
            for term_bin, exec_flag, extra_flags in terminals:
                if shutil.which(term_bin):
                    print(f"✅ Found terminal emulator: {term_bin}")
                    
                    cmd_args = [term_bin]
                    cmd_args.extend(extra_flags)
                    cmd_args.extend([exec_flag, "bash", "-l", "-i", "-c", full_shell_cmd_string])
                    
                    # Redirect stdout/stderr to avoid cluttering this script's output.
                    process = subprocess.Popen(cmd_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    terminal_found = True
                    break
            if not terminal_found:
                print("\n❌ Error: Could not find a supported terminal emulator.")
                sys.exit(1)

    # === Final Wait Block ===
    if process:
        print("\n⏳ Waiting for the newly launched terminal window to close...")
        print("(If the new window is stuck open, press Enter inside it first)")
        try:
            # This line blocks this script until the launched terminal process finishes.
            process.wait()
        except KeyboardInterrupt:
            print("\n[!] Setup script interrupted by user. The external terminal may still be open.")
    
    print("✅ Setup script finished.")
    sys.exit(0)

# --- Main Execution ---
if __name__ == "__main__":
    args_set = set(sys.argv[1:])
    # Get both flags
    requested_cpu_only, fast_mode = initialize_environment(args_set)
    
    conda_base_path = None
    main_env_name = None

    if os.getenv('USE_CONDA') == "True":
        is_installed, reason, conda_base_path = is_conda_installed_robust()
        
        if not is_installed:
            print(f"❌ Conda is not installed ({reason}). Please use --no-conda.")
            sys.exit(1)
        else:
            print(f"✅ Conda detected ({reason}). Base path: {conda_base_path}")
            main_env_name = get_env_name_from_yml(YML_FILE)

            # --- Main Environment Setup ---
            if not fast_mode:
                 setup_conda_environment(env_name=main_env_name, yml_path=YML_FILE)
            else:
                 print(f"ℹ️ Skipping main Conda env update check (--fast).")
            
            verify_conda_env_ready(env_name=main_env_name) # Optional check

    else:
        # OPTIMIZATION: Skip global pip updates in fast mode
        if not fast_mode:
             setup_global_environment(requirements_file=REQUIREMENTS_FILE)
        else:
             print(f"ℹ️ Skipping global pip requirements check (--fast).")

    # --- OmniParser Setup ---
    # This will run if USE_CONDA is true and USE_OMNIPARSER is true.
    if os.getenv('USE_OMNIPARSER') == "True":
        # Pass fast_mode to omniparser setup
        setup_omniparser_local(force_cpu=requested_cpu_only, fast_mode=fast_mode)

    # Launch the terminal with the necessary info for the MAIN environment
    launch_in_new_terminal(conda_env_name=main_env_name, conda_base_path=conda_base_path)