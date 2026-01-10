import os
import subprocess
import sys

REPO_URL = "https://github.com/web-arena-x/webarena"
TARGET_DIR = "src"

def setup():
    print(f"Setting up WebArena environment in {os.getcwd()}...")
    if os.path.exists(TARGET_DIR):
        print(f"Directory '{TARGET_DIR}' already exists. Skipping clone.")
    else:
        print(f"Cloning {REPO_URL} into {TARGET_DIR}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            print("Clone successful.")
        except subprocess.CalledProcessError as e:
            print(f"Error cloning repository: {e}")
            sys.exit(1)
            
    # Check for requirements.txt
    req_path = os.path.join(TARGET_DIR, "requirements.txt")
    if os.path.exists(req_path):
        print("Found requirements.txt. Installing dependencies...")
        try:
             subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
             print("Dependencies installed.")
        except subprocess.CalledProcessError as e:
             print(f"Error installing dependencies: {e}")
    else:
        print("No requirements.txt found in the root of the cloned repo.")

if __name__ == "__main__":
    setup()
