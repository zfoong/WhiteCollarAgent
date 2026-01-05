# core/action_framework/loader.py
import os
import importlib.util
import sys
from typing import List
import logging
from pathlib import Path

logger = logging.getLogger("ActionLoader")

# Define default paths relative to the project root to scan for actions
DEFAULT_ACTION_PATHS = [
    os.path.join('core', 'data', 'action'),
    # Looks for actions in any custom agent folder
    # os.path.join('agents'), 
]

def load_actions_from_directories(base_dir: str = None, paths_to_scan: List[str] = None):
    """
    Walks through specified directories, finds .py files, and dynamically imports them.
    Importing them triggers the @action decorator, registering them in the registry.
    """
    if base_dir is None:
         # Assuming app is run from project root
        base_dir = os.getcwd()

    if paths_to_scan is None:
        paths_to_scan = DEFAULT_ACTION_PATHS
    else:
        paths_to_scan += DEFAULT_ACTION_PATHS
        
    logger.info(f"--- Starting Action Discovery from base: {base_dir} ---")
    
    count = 0
    processed_files = set()

    for relative_path in paths_to_scan:
        relative_path = Path(relative_path)  
        full_search_path = Path(base_dir) / relative_path
        
        if not os.path.exists(full_search_path):
            logger.debug(f"Skipping non-existent directory: {full_search_path}")
            continue
            
        logger.debug(f"Scanning directory structure: {full_search_path}")

        # Walk the directory tree
        for root, _, files in os.walk(full_search_path):
            # Special handling to only look into 'data/action' if we are scanning the 'agents' folder
            root_path = Path(root) 
            
            if "agents" in relative_path.parts and "data" in root_path.parts and "action" not in root_path.parts:
                 continue

            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    file_path = os.path.join(root, file)
                    
                    # Prevent loading the same file twice if paths overlap
                    if file_path in processed_files:
                        continue
                    processed_files.add(file_path)

                    # Generate a unique module name based on file path to prevent collisions in sys.modules
                    # e.g., agents/custom/actions.py -> agents_custom_actions
                    rel_path_from_base = os.path.relpath(file_path, base_dir)
                    # sanitize path for module name
                    module_name_safe = rel_path_from_base.replace(os.path.sep, "_").replace(".", "_").replace("-", "_")

                    try:
                        logger.debug(f"Loading action file: {rel_path_from_base}")
                        # --- Dynamic Import Magic ---
                        # 1. Create a module spec from the file location
                        spec = importlib.util.spec_from_file_location(module_name_safe, file_path)
                        if spec and spec.loader:
                            # 2. Create the module from the spec
                            module = importlib.util.module_from_spec(spec)
                            # 3. Add to sys.modules so imports inside that script work normally
                            sys.modules[module_name_safe] = module
                            # 4. Execute the module body. This triggers the @action decorators.
                            spec.loader.exec_module(module)
                            count += 1
                    except Exception as e:
                        # Catch errors so one bad action file doesn't crash the whole startup
                         logger.error(f"Failed to load action script {file_path}: {e}", exc_info=True)

    logger.info(f"--- Action Discovery Complete. Processed {count} files. ---")