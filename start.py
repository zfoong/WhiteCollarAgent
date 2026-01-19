#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import platform
import shutil
import shlex
from typing import Tuple, Optional

# --- Configuration ---
CONFIG_FILE = "config.json"
MAIN_APP_SCRIPT = "main.py"
YML_FILE = "environment.yml"
REQUIREMENTS_FILE = "requirements.txt"

# ==========================================
# HELPER FUNCTIONS (Environment Setup)
# ==========================================
def initialize_environment(args: set[str]):
    flag_ignore_omniparse = "--no-omniparser" in args
    os.environ["USE_OMNIPARSER"] = str(not flag_ignore_omniparse)
    print(f"[*] Using Omniparser: {os.getenv('USE_OMNIPARSER')}")
    flag_ignore_conda = "--no-conda" in args
    os.environ["USE_CONDA"] = str(not flag_ignore_conda)
    print(f"[*] Using Conda: {os.getenv('USE_CONDA')}")

def is_conda_installed_robust() -> Tuple[bool, str, Optional[str]]:
    """
    Checks if Conda is installed and returns its status, reason, and base path.
    The base path is essential for locating activation scripts on unix-like systems.
    """
    conda_exe = shutil.which("conda")
    if conda_exe:
        # On unix, if conda is /foo/bar/bin/conda, base is /foo/bar
        # On win, if conda is C:\foo\Scripts\conda.exe, base is C:\foo
        conda_base_path = os.path.dirname(os.path.dirname(conda_exe))
        return True, f"Found executable at {conda_exe}", conda_base_path

    # Windows fallback checks for hidden/local installations
    if sys.platform == "win32":
        print("... Standard check failed on Windows. Attempting to locate hidden installation ...")
        current_python_dir = os.path.dirname(sys.executable)
        # Often python is installed within conda envs, so base dir is a few levels up from python.exe
        potential_base_paths = [
            os.path.dirname(current_python_dir), 
            os.path.dirname(os.path.dirname(current_python_dir))
        ]
        
        for base_path in potential_base_paths:
            # Check for typical windows activation/management scripts
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
    cmd = ["conda", "env", "update", "-f", yml_path, "--prune"]
    try:
        subprocess.check_call(cmd, shell=(sys.platform == "win32"))
        print("✅ Conda environment installation command finished successfully.")
    except subprocess.CalledProcessError: 
        print("❌ Conda environment setup failed.")
        sys.exit(1)
    except FileNotFoundError: 
        print("❌ Error: 'conda' command not found during setup.")
        sys.exit(1)

def verify_conda_env_ready(env_name: str):
    print(f"Attempting to verify environment '{env_name}' is active and working...")
    # Use 'conda run' just for verification as it's simpler for single commands
    verification_cmd = ["conda", "run", "-n", env_name, "python", "-c", "import sys; print(f'SUCCESS: Verified {sys.executable}')"]
    try:
        subprocess.run(verification_cmd, capture_output=True, text=True, check=True, shell=(sys.platform == "win32"))
        print(f"✅ Verification successful. The environment is ready.")
        return True
    except subprocess.CalledProcessError as e: 
        print(f"❌ Verification FAILED. Error Output:\n{e.stderr}") 
        sys.exit(1)
    except FileNotFoundError: 
        print("❌ Error: 'conda' command lost during verification.")
        sys.exit(1)

def setup_global_environment(requirements_file: str = REQUIREMENTS_FILE):
    print("Setting up global environment using pip...")
    if not os.path.exists(requirements_file): print(f"❌ Error: {requirements_file} not found."); sys.exit(1)
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
        print("✅ Pip install finished successfully.")
    except subprocess.CalledProcessError: print("❌ Pip setup failed."); sys.exit(1)

def save_config_file(env_name: str, created_success: bool):
    data = {"conda_environment_name": env_name, "conda_environment_created": created_success}
    try: 
        with open(CONFIG_FILE, 'w') as f: 
            json.dump(data, f, indent=4)
            print(f"ℹ️ Config saved to {CONFIG_FILE}")
    except IOError as e: print(f"⚠️ Warning: Could not save config file: {e}")

# =========================================
# NEW LAUNCHER: SEPARATE MAXIMIZED TERMINAL
# =========================================
def launch_in_new_terminal(conda_env_name: Optional[str] = None, conda_base_path: Optional[str] = None):
    """
    Detects OS and launches main.py in a newly spawned, MAXIMIZED terminal window.
    On Linux/macOS, it uses an "activate then run" strategy to ensure real-time output.
    On Windows, it uses the simpler 'conda run' approach.
    """
    abs_main_script_path = os.path.abspath(MAIN_APP_SCRIPT)
    if not os.path.exists(abs_main_script_path):
        print(f"❌ Error: The main application script was not found at: {abs_main_script_path}")
        sys.exit(1)

    setup_flags = {"--no-conda", "--no-omniparser"}
    pass_through_args = [arg for arg in sys.argv[1:] if arg not in setup_flags]
    current_os = sys.platform

    print("-------------------------------------------------")
    print(f"🚀 Setting up launch command for OS: {current_os}")
    print("-------------------------------------------------")

    # === Windows Implementation ===
    if current_os == "win32":
        # Windows 'conda run' approach is usually fine with buffering and easier to implement.
        if conda_env_name and os.getenv('USE_CONDA') == "True":
             cmd_list = ["conda", "run", "-n", conda_env_name, "python", "-u", abs_main_script_path] + pass_through_args
        else:
             cmd_list = [sys.executable, "-u", abs_main_script_path] + pass_through_args
        
        cmd_string = shlex.join(cmd_list)
        # start /MAX: Maximize window. cmd /k: keep open. set PYTHONUNBUFFERED=1: backup buffering measure.
        launch_cmd = f'start /MAX cmd /k "set PYTHONUNBUFFERED=1 && {cmd_string}"'
        subprocess.Popen(launch_cmd, shell=True)

    # === Linux & macOS Implementation (The "Activate then Run" strategy) ===
    else:
        # 1. Define the raw python command to run *after* activation.
        # We assume that once activated, 'python' will point to the correct env's python.
        # We still use '-u' for good measure.
        python_cmd_string = shlex.join(["python", "-u", abs_main_script_path] + pass_through_args)

        # 2. Construct the complex shell command string to run inside the new terminal
        shell_commands = []
        shell_commands.append('echo "--- Terminal Started ---"')

        use_conda = (conda_env_name and os.getenv('USE_CONDA') == "True" and conda_base_path)
        
        if use_conda:
            print(f"ℹ️ Configuring shell to activate conda environment: '{conda_env_name}'")
            # Find the standard conda activation script on Unix systems
            conda_sh_path = os.path.join(conda_base_path, "etc", "profile.d", "conda.sh")
            
            if os.path.exists(conda_sh_path):
                # The robust way: source the setup script using '.', then activate.
                shell_commands.append(f". '{conda_sh_path}'")
                shell_commands.append(f"conda activate '{conda_env_name}'")
            else:
                 print(f"⚠️ Warning: Could not find conda.sh at {conda_sh_path}. Trying fallback activation method.")
                 # Fallback: hope 'conda' alias is already available in the new shell session.
                 shell_commands.append(f"conda activate '{conda_env_name}'")
        else:
             print("ℹ️ Using global python environment.")

        # Add the actual python command
        shell_commands.append('echo "--- Launching main.py ---"')
        # Use || to catch exit codes so the terminal doesn't close instantly on error
        shell_commands.append(f"{python_cmd_string} || echo '\n❌ Process exited with error code $?'")
        shell_commands.append('echo "\n--- Session Finished ---"')
        
        # Add the "wait for keypress" command
        if current_os.startswith("linux"):
             shell_commands.append('read -p "Press Enter to close terminal..."')
        else: # macos
             shell_commands.append('read -n 1 -p "Press any key to close terminal..."')

        # Join them into a single one-liner separated by semicolons
        full_shell_cmd_string = "; ".join(shell_commands)

        # --- Launch Logic ---
        if current_os == "darwin":
            # macOS Terminal launch via AppleScript
            applescript = f'tell application "Terminal" to do script "{full_shell_cmd_string}" activate'
            subprocess.run(["osascript", "-e", applescript])

        elif current_os.startswith("linux"):
            # Linux Maximized Launch with various terminal emulators
            terminals = [
                ("gnome-terminal", "--", "--maximize"),
                ("konsole", "-e", "--maximize"),
                ("xfce4-terminal", "-x", "--maximize"),
                ("terminator", "-x", "-m"),
            ]
            terminal_found = False
            for term_bin, exec_flag, max_flag in terminals:
                if shutil.which(term_bin):
                    print(f"✅ Found terminal emulator: {term_bin}")
                    # Build command: [terminal, max, execute, bash, login, interactive, command_string]
                    # Using 'bash -l -i' is important to ensure profiles are loaded.
                    launch_cmd = [term_bin, max_flag, exec_flag, "bash", "-l", "-i", "-c", full_shell_cmd_string]
                    
                    # Launch and disconnect (don't wait for it)
                    subprocess.Popen(launch_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    terminal_found = True
                    break
            if not terminal_found:
                print("\n❌ Error: Could not find a supported terminal emulator (gnome-terminal, konsole, xfce4-terminal, or terminator).")
                sys.exit(1)

    print("✅ New terminal launched. Setup script exiting.")
    sys.exit(0)

# --- Main Execution ---
if __name__ == "__main__":
    args_set = set(sys.argv[1:])
    initialize_environment(args_set)
    
    conda_base_path = None
    env_name = None

    if os.getenv('USE_CONDA') == "True":
        # Retrieve installation status and the crucial base path
        is_installed, reason, conda_base_path = is_conda_installed_robust()
        
        if not is_installed:
            print(f"❌ Conda is not installed ({reason}). Please use --no-conda.")
            sys.exit(1)
        else:
            print(f"✅ Conda detected ({reason}). Base path: {conda_base_path}")
            env_name = get_env_name_from_yml(YML_FILE)

            # --- Setup Steps (Uncomment for real use) ---
            setup_conda_environment(env_name=env_name, yml_path=YML_FILE)
            verify_conda_env_ready(env_name=env_name)
            save_config_file(env_name, True)

    else:
        print("✅ Conda is not used. Using global environment.")
        setup_global_environment(requirements_file=REQUIREMENTS_FILE)

    # Launch the terminal with the necessary info
    launch_in_new_terminal(conda_env_name=env_name, conda_base_path=conda_base_path)