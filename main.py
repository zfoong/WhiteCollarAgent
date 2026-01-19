import os
import sys
import subprocess
import platform

if __name__ == "__main__":

    current_os = platform.system()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if current_os == "Windows":
        script_name = "run.bat"
        script_path = os.path.join(script_dir, script_name)
        # On Windows, shell=True is usually needed for .bat files
        use_shell = True
        cmd = [script_path]
        print(f"[*] Detected Windows. Launching {script_name}...")
    else:
        # Linux or Darwin (macOS)
        script_name = "run.sh"
        script_path = os.path.join(script_dir, script_name)
        use_shell = False
        
        # 1. Make executable (keep your existing logic)
        if not os.access(script_path, os.X_OK):
            print(f"[*] Making {script_name} executable...", flush=True)
            try:
                current_permissions = os.stat(script_path).st_mode
                os.chmod(script_path, current_permissions | 0o111)
            except Exception as e:
                print(f"[!] Error making script executable: {e}")
                sys.exit(1)

        # 2. ROBUST LAUNCH COMMAND FOR LINUX/MAC
        # Instead of trying to execute the file directly (which relies on shebangs),
        # explicitly call the shell executable. This is much safer.
        cmd = ["/bin/bash", script_path] 
        # Alternatively, for broader compatibility: cmd = ["sh", script_path]
        print(f"[*] Detected {current_os}. Launching via: {' '.join(cmd)}", flush=True)


    # --- THE CRITICAL FIX ---
    try:
        sys.stdout.flush() # Ensure previous prints appear first
        
        # Use subprocess.run with explicit I/O passing, just like setup.py does.
        result = subprocess.run(
            cmd,
            shell=use_shell,
            # Pass terminal handles directly to the grandchild process
            stdout=sys.stdout,
            stderr=sys.stderr,
            stdin=sys.stdin,
            check=False # We handle return codes manually below
        )
        sys.exit(result.returncode)

    except FileNotFoundError:
        print(f"\n[ERROR] Could not find the executable to run {script_name}.")
        print(f"Attempted command: {cmd}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[!] Launcher interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred in main.py: {e}")
        sys.exit(1)