import asyncio
import json
import os
import sys
import requests
import traceback
import shutil
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Add project root to path
sys.path.append(os.getcwd())

try:
    from datasets import load_dataset
except ImportError:
    print("Please install 'datasets' library: pip install datasets")
    sys.exit(1)

from agents.personal_assistant.agent import PersonalAssistantAgent
from core.state.agent_state import STATE
from core.trigger import Trigger
from core.logger import logger
from core.config import AGENT_WORKSPACE_ROOT
import logging

GAIA_BASE_URL = "https://huggingface.co/datasets/gaia-benchmark/GAIA/resolve/main/2023/validation/"
OUTPUT_FILE = "benchmark/GAIA/results.jsonl"

async def run_agent_cycle(agent, task_id, question, file_path=None):
    """
    Placeholder function for the agent execution cycle.
    
    Args:
        agent: The initialized agent instance.
        task_id: The ID of the current task.
        question: The question or instruction for the agent.
        file_path: Optional path to a downloaded attachment.
        
    Returns:
        tuple: (final_answer, status)
    """
    
    # Need change to accept question
    await agent.triggers.put(
        Trigger(
            fire_at=0,
            priority=1,
            next_action_description=question,
            session_id=task_id,
            payload={"gui_mode": False}
        )
    )
    
    final_answer = None
    status = "failed"
    step_count = 0
    MAX_STEPS = 30 
    
    try:
        while agent.is_running and step_count < MAX_STEPS:
            # main agent cycle
            final_answer = ""
        
        if step_count >= MAX_STEPS:
            status = "timeout"
            
    except Exception as e:
        logger.error("Error in agent cycle.", exc_info=True)
        print(f"Error in agent cycle: {e}")
        traceback.print_exc()
        status = "exception"
        final_answer = str(e)
        
    return final_answer, status

async def run_benchmark(limit: int | None = None):
    # 1. Load Dataset
    print("Loading GAIA validation set via datasets library...")
    try:
        ds = load_dataset("gaia-benchmark/GAIA", "2023_all", split="validation")
        print(f"Loaded {len(ds)} questions.")
    except Exception as e:
        logger.error("Failed to load dataset.", exc_info=True)
        print(f"Failed to load dataset: {e}")
        return

    # 2. Setup Agent
    bundle_dir = Path("agents/personal_assistant")
    cfg = {"data_dir": "core/data", "rag_dir": "rag_docs"} 
    
    # Initialize workspace
    os.makedirs(AGENT_WORKSPACE_ROOT, exist_ok=True)
    
    try:
        agent = PersonalAssistantAgent(cfg, bundle_dir)
        agent.is_running = True
    except Exception as e:
        logger.error("Failed to initialize agent.", exc_info=True)
        print(f"Failed to initialize agent: {e}")
        return

    # 3. Iterate through questions
    existing_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        existing_ids.add(rec.get("task_id"))
                    except:
                        pass
    
    print(f"Found {len(existing_ids)} existing results. Resuming...")

    processed_count = 0
    for i, item in enumerate(ds):
        if limit is not None and processed_count >= limit:
            print(f"Reached limit of {limit} tasks. Stopping.")
            break

        task_id = item["task_id"]
        if task_id in existing_ids:
            continue

        processed_count += 1
        question = item["Question"]
        file_name = item.get("file_name")
        
        print(f"\n[{i+1}/{len(ds)}] Running Task {task_id}")
        print(f"Question: {question[:100]}...")

        # Handle File Attachment
        local_path = None
        if file_name and file_name.strip():
            file_url = GAIA_BASE_URL + file_name
            local_path = AGENT_WORKSPACE_ROOT / file_name
            try:
                print(f"Downloading attachment: {file_name}...")
                headers = {}
                hf_token = os.getenv("HF_TOKEN")
                if hf_token:
                    headers["Authorization"] = f"Bearer {hf_token}"
                
                r = requests.get(file_url, headers=headers)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(r.content)
                question += f"\n\n(Attachment downloaded to: {local_path})"
            except Exception as e:
                logger.warning(
                    "Failed to download attachment %s from %s.",
                    file_name,
                    file_url,
                    exc_info=True,
                )
                print(f"Failed to download attachment {file_name}: {e}")
                question += f"\n\n(Failed to download attachment {file_name})"

        # Reset Agent State before running cycle
        await agent.reset_agent_state()
        
        # --- CALL AGENT CYCLE ---
        final_answer, status = await run_agent_cycle(agent, task_id, question, local_path)
        # ------------------------

        print(f"  -> Status: {status}")
        print(f"  -> Answer: {final_answer}")
        
        # Clean up workspace file
        if local_path and os.path.exists(local_path):
             try:
                 os.remove(local_path)
             except Exception:
                 logger.warning("Failed to remove attachment %s.", local_path, exc_info=True)

        result_entry = {
            "task_id": task_id,
            "question": item["Question"],
            "file_name": file_name,
            "model_answer": final_answer,
            "status": status,
            "ground_truth": item.get("Final answer")
        }
        
        with open(OUTPUT_FILE, "a") as f:
            f.write(json.dumps(result_entry) + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GAIA Benchmark")
    parser.add_argument("--limit", type=int, help="Limit the number of tasks to run", default=None)
    args = parser.parse_args()
    
    asyncio.run(run_benchmark(limit=args.limit))
