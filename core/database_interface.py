# -*- coding: utf-8 -*-
"""core.database_interface

A filesystem backed storage layer (plus ChromaDB) so the rest of the
codebase never talks to persistence details directly.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import chromadb

from core.logger import logger
from core.task.task import Task

from core.action.action_framework.registry import registry_instance
from core.action.action_framework.loader import load_actions_from_directories


class DatabaseInterface:
    """All persistence operations for the agent live here."""

    def __init__(
        self,
        *,
        data_dir: str = "core/data",
        chroma_path: str = "./chroma_db",
        log_file: Optional[str] = None,
    ) -> None:
        """
        Initialize storage directories and vector stores for agent data.

        The constructor sets up filesystem paths for logs, actions, task
        documents, and agent info. It also initializes separate Chroma
        collections for actions and task documents, ensuring they are synced
        with existing files on startup.

        Args:
            data_dir: Base directory used to persist logs and JSON artifacts.
            chroma_path: Root path for ChromaDB persistence; distinct suffixes
                are used for actions and task documents.
            log_file: Optional explicit log file path; defaults to
                ``<data_dir>/agent_logs.txt`` when omitted.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.log_file_path = Path(log_file) if log_file else self.data_dir / "agent_logs.txt"
        self.actions_dir = self.data_dir / "action"
        self.task_docs_dir = self.data_dir / "task_document"
        self.agent_info_path = self.data_dir / "agent_info.json"


        self.actions_dir.mkdir(parents=True, exist_ok=True)
        self.task_docs_dir.mkdir(parents=True, exist_ok=True)
        self.log_file_path.touch(exist_ok=True)
        if not self.agent_info_path.exists():
            self.agent_info_path.write_text("{}", encoding="utf-8")


        try:
            self._initialize_chroma(chroma_path)
        except Exception:
            logger.error(
                "Failed to initialize ChromaDB; attempting a clean rebuild.",
                exc_info=True,
            )
            self._reset_chroma_storage(chroma_path)
            self._initialize_chroma(chroma_path)

    def _initialize_chroma(self, chroma_path: str) -> None:
        # ChromaDB (for vector search on actions and task documents)
        self.chroma = chromadb.PersistentClient(path=f"{chroma_path}_actions")
        self.chroma_actions = self.chroma.get_or_create_collection("agent_actions")

        # separate ChromaDB client/collection for task documents
        self.chroma_taskdocs = chromadb.PersistentClient(path=f"{chroma_path}_taskdocs")
        self.chroma_taskdocs_coll = self.chroma_taskdocs.get_or_create_collection("task_documents")

        # Ensure Chroma stays in sync with the filesystem sources on startup
        self.sync_actions_to_chroma(paths_to_scan=[self.actions_dir])

        # Retrieve everything currently in the collection
        stored_data = self.chroma_actions.get()
        stored_ids = stored_data.get("ids", [])
        count = len(stored_ids)
        
        if count > 0:
            # Create a readable comma-separated string of action names
            actions_list_str = ", ".join(sorted(stored_ids))
            logger.info(f"✅ ChromaDB sync successful. Collection now holds {count} actions: [{actions_list_str}]")
        else:
            logger.warning("⚠️ ChromaDB sync completed, but the collection is empty.")

        self.sync_task_documents_to_chroma()

    def _reset_chroma_storage(self, chroma_path: str) -> None:
        for suffix in ("_actions", "_taskdocs"):
            path = Path(f"{chroma_path}{suffix}")
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _load_log_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        try:
            with self.log_file_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"[LOG PARSE] Skipping malformed line in {self.log_file_path}")
        except FileNotFoundError:
            pass
        return entries

    def _write_log_entries(self, entries: Iterable[Dict[str, Any]]) -> None:
        with self.log_file_path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, default=str) + "\n")

    def _append_log_entry(self, entry: Dict[str, Any]) -> None:
        with self.log_file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    # ------------------------------------------------------------------
    # Prompt logging & token usage helpers
    # ------------------------------------------------------------------
    def log_prompt(
        self,
        *,
        input_data: Dict[str, str],
        output: Optional[str],
        provider: str,
        model: str,
        config: Dict[str, Any],
        status: str,
        token_count_input: Optional[int] = None,
        token_count_output: Optional[int] = None,
    ) -> None:
        """
        Store a single prompt interaction with metadata and token counts.

        Each call appends a structured record to the log file so usage metrics
        and model behavior can be inspected later.

        Args:
            input_data: Serialized prompt inputs sent to the model provider.
            output: The raw model output string, if available.
            provider: Name of the LLM provider (e.g., OpenAI, Anthropic).
            model: Specific model identifier used for the request.
            config: Provider-specific configuration details for the call.
            status: Execution status for the prompt (e.g., ``"success"`` or
                ``"error"``).
            token_count_input: Optional token count for the prompt payload.
            token_count_output: Optional token count for the model response.
        """
        entry = {
            "entry_type": "prompt_log",
            "datetime": datetime.datetime.utcnow().isoformat(),
            "input": input_data,
            "output": output,
            "provider": provider,
            "model": model,
            "config": config,
            "status": status,
            "token_count_input": token_count_input,
            "token_count_output": token_count_output,
        }
        self._append_log_entry(entry)

    def _iter_prompt_logs(self) -> Iterable[Dict[str, Any]]:
        for entry in self._load_log_entries():
            if entry.get("entry_type") == "prompt_log":
                yield entry

    # ------------------------------------------------------------------
    # Action history logging
    # ------------------------------------------------------------------
    def upsert_action_history(
        self,
        run_id: str,
        *,
        session_id: str,
        parent_id: str | None,
        name: str,
        action_type: str,
        status: str,
        inputs: Dict[str, Any] | None,
        outputs: Dict[str, Any] | None,
        started_at: str | None,
        ended_at: str | None,
    ) -> None:
        """
        Insert or update an action execution history entry.

        The log is keyed by ``run_id``; repeated writes merge new details while
        preserving the initial ``startedAt`` value when absent.

        Args:
            run_id: Unique identifier for the action execution instance.
            session_id: Identifier for the session that triggered the action.
            parent_id: Optional run identifier for the parent action in a tree.
            name: Human-readable action name.
            action_type: Action type label; duplicated into ``type`` for
                backward compatibility.
            status: Current execution status.
            inputs: Serialized action inputs, if available.
            outputs: Serialized action outputs, if available.
            started_at: ISO timestamp for when execution began.
            ended_at: ISO timestamp for when execution completed.
        """
        entries = self._load_log_entries()
        payload = {
            "entry_type": "action_history",
            "runId": run_id,
            "sessionId": session_id,
            "parentId": parent_id,
            "name": name,
            "action_type": action_type,
            "type": action_type,
            "status": status,
            "inputs": inputs,
            "outputs": outputs,
            "startedAt": started_at,
            "endedAt": ended_at,
        }

        found = False
        for entry in entries:
            if entry.get("entry_type") == "action_history" and entry.get("runId") == run_id:
                entry["action_type"] = payload["action_type"]
                entry["type"] = payload["type"]
                entry.update({k: v for k, v in payload.items() if v is not None or k in {"inputs", "outputs"}})
                if entry.get("startedAt") is None:
                    entry["startedAt"] = started_at
                found = True
                break

        if not found:
            if payload["startedAt"] is None:
                payload["startedAt"] = datetime.datetime.utcnow().isoformat()
            entries.append(payload)

        self._write_log_entries(entries)

    def _iter_action_history(self) -> Iterable[Dict[str, Any]]:
        for entry in self._load_log_entries():
            if entry.get("entry_type") == "action_history":
                yield entry

    def find_actions_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Return all action history entries matching the given status.

        Args:
            status: Status value to filter (e.g., ``"current"`` or ``"pending"``).

        Returns:
            List of action history dictionaries where ``status`` matches.
        """
        return [entry for entry in self._iter_action_history() if entry.get("status") == status]

    def get_action_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve recent action history entries ordered by start time.

        Args:
            limit: Maximum number of entries to return, sorted newest-first.

        Returns:
            A list of action history dictionaries truncated to ``limit``
            entries.
        """
        history = list(self._iter_action_history())
        history.sort(
            key=lambda e: datetime.datetime.fromisoformat(e.get("startedAt") or datetime.datetime.min.isoformat()),
            reverse=True,
        )
        return history[:limit]

    # ------------------------------------------------------------------
    # Task logging helpers
    # ------------------------------------------------------------------
    def log_task(self, task: Task) -> None:
        """
        Persist or update a task log entry for tracking execution progress.

        The task is serialized to JSON-compatible primitives and either
        appended to the log or merged with an existing entry for the same task
        identifier.

        Args:
            task: The :class:`~core.task.task.Task` instance to record.
        """
        doc = {
            "entry_type": "task_log",
            "task_id": task.id,
            "name": task.name,
            "instruction": task.instruction,
            "steps": [asdict(step) for step in task.steps],
            "created_at": task.created_at,
            "status": task.status,
            "results": task.results,
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }

        entries = self._load_log_entries()
        for entry in entries:
            if entry.get("entry_type") == "task_log" and entry.get("task_id") == task.id:
                entry.update(doc)
                break
        else:
            entries.append(doc)

        self._write_log_entries(entries)

    def _iter_task_logs(self) -> Iterable[Dict[str, Any]]:
        for entry in self._load_log_entries():
            if entry.get("entry_type") == "task_log":
                yield entry

    # ------------------------------------------------------------------
    # Action definitions (filesystem + Chroma)
    # ------------------------------------------------------------------
    def _sanitize_action_filename(self, name: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_") or "action"
        return f"{sanitized}.json"

    def _load_actions_from_disk(self) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for path in self.actions_dir.glob("*.json"):
            try:
                actions.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning(f"[ACTION LOAD] Failed to read {path}: {exc}")
        return actions

    def store_action(self, action_dict: Dict[str, Any]) -> None:
        """
        Persist an action definition and refresh its vector index entry.

        Args:
            action_dict: Action payload to store, expected to include a ``name``
                field used for the filename and Chroma identifier.
        """
        action_dict["updatedAt"] = datetime.datetime.utcnow().isoformat()
        file_name = self._sanitize_action_filename(action_dict["name"])
        path = self.actions_dir / file_name
        path.write_text(json.dumps(action_dict, indent=2, default=str), encoding="utf-8")

        # keep Chroma in sync
        self.chroma_actions.delete(ids=[action_dict["name"]], ignore_missing=True)
        self.chroma_actions.add(
            ids=[action_dict["name"]],
            documents=[action_dict["name"]],
        )

    def list_actions(
        self,
        *,
        default: bool | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Return stored actions optionally filtered by the ``default`` flag.

        Args:
            default: When provided, only return actions whose ``default`` field
                matches the boolean value.

        Returns:
            List of action dictionaries stored on disk that satisfy the filter.
        """
        actions = registry_instance.list_all_actions_as_json()

        if default is not None:
            actions = [action for action in actions if action.get("default") == default]

        return actions

    def get_action(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a stored action by case-insensitive name match.

        Args:
            name: The human-readable name used to identify the action.

        Returns:
            The action dictionary when found, otherwise ``None``.
        """
        needle = name.lower()
        action = registry_instance.find_action_by_name(action_name=name)
        
        # if action is None:
        #     for action in self._load_actions_from_disk():
        #         if action.get("name", "").lower() == needle:
        #             return action
        return action

    def delete_action(self, name: str) -> None:
        """
        Remove an action definition from disk and its Chroma index.

        Args:
            name: Name of the action to delete.
        """
        for path in self.actions_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if payload.get("name") == name:
                path.unlink(missing_ok=True)
                break
        self.chroma_actions.delete(ids=[name], ignore_missing=True)

    def search_actions(self, query: str, top_k: int = 7) -> List[str]:
        """
        Search stored actions using vector similarity on their names and description.

        Args:
            query: Freeform text used to locate similar action names and description.
            top_k: Maximum number of action identifiers to return.

        Returns:
            List of action names ranked by similarity to ``query``.
        """
        result = self.chroma_actions.query(
            query_texts=[query],
            n_results=top_k,
        )
        return result.get("ids", [[]])[0] if result else []

    def sync_actions_to_chroma(self, paths_to_scan: List[str] = None) -> int:
        """
        Build the Chroma action collection from JSON files on disk.

        Returns:
            Number of action definitions indexed in Chroma.
        """        
        load_actions_from_directories(paths_to_scan=paths_to_scan)

        actions: List[Dict[str, Any]] = registry_instance.list_all_actions_as_json()

        try:
            existing = self.chroma_actions.get()
            ids = existing.get("ids", []) if existing else []
            if ids:
                self.chroma_actions.delete(ids=list(ids))
        except Exception:
            pass

        ids: List[str] = []
        documents: List[str] = []
        for action in actions:
            name = action.get("name")
            if not name:
                continue
            ids.append(name)
            documents.append(name)

        if not ids:
            return 0

        self.chroma_actions.add(ids=ids, documents=documents)
        return len(ids)

    # ------------------------------------------------------------------
    # Agent configuration
    # ------------------------------------------------------------------
    def set_agent_info(self, info: Dict[str, Any], key: str = "singleton") -> None:
        """
        Persist arbitrary agent configuration under the provided key.

        Args:
            info: Mapping of configuration fields to store.
            key: Logical namespace under which the configuration is saved.
        """        
        try:
            existing = json.loads(self.agent_info_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        existing[key] = {**existing.get(key, {}), **info}
        self.agent_info_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def get_agent_info(self, key: str = "singleton") -> Optional[Dict[str, Any]]:
        """
        Load persisted agent configuration for the given key.

        Args:
            key: Namespace key used when persisting the configuration.

        Returns:
            A configuration dictionary when present, otherwise ``None``.
        """        
        try:
            info = json.loads(self.agent_info_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return info.get(key)

    # ------------------------------------------------------------------
    # Task documents (filesystem + Chroma)
    # ------------------------------------------------------------------
    def _extract_task_document_metadata(self, raw_text: str, fallback_name: str) -> tuple[str, str]:
        name: Optional[str] = None
        description: Optional[str] = None
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("name:") and not name:
                name = stripped.split(":", 1)[1].strip() or None
            elif lowered.startswith("description:") and not description:
                description = stripped.split(":", 1)[1].strip() or None
            if name and description:
                break
        
        if not name:
            name = fallback_name
        if not description:
            first_para = next((blk.strip() for blk in raw_text.split("\n\n") if blk.strip()), "")
            description = first_para[:400]
        return name, description
    
    def _load_task_documents_from_disk(self) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for path in sorted(self.task_docs_dir.glob("*.txt")):
            try:
                raw_text = path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning(f"[TASKDOC LOAD] Failed to read {path}: {exc}")
                continue
    
            name, description = self._extract_task_document_metadata(raw_text, path.stem)
            docs.append(
                {
                    "task_id": path.stem,
                    "name": name,
                    "description": description,
                    "raw_text": raw_text,
                    "source_path": str(path),
                }
            )
        return docs

    def sync_task_documents_to_chroma(self) -> int:
        """
        Rebuild the Chroma collection from task document text files.

        Returns:
            Number of task documents indexed in Chroma after the sync.
        """        
        docs = self._load_task_documents_from_disk()
        try:
            existing = self.chroma_taskdocs_coll.get()
            ids = existing.get("ids", []) if existing else []
            if ids:
                self.chroma_taskdocs_coll.delete(ids=list(ids))
        except Exception:
            pass

        if not docs:
            return 0

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        for doc in docs:
            ids.append(doc["task_id"])
            documents.append(f"{doc['name']}\n\n{doc['description']}")
            metadatas.append({"name": doc["name"]})

        self.chroma_taskdocs_coll.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def retrieve_similar_task_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Return task documents ranked by similarity to the query text.

        Args:
            query: Text prompt used for semantic similarity search.
            top_k: Maximum number of documents to return.

        Returns:
            Ordered list of task document dictionaries in descending similarity
            rank.
        """        
        if not query or not query.strip():
            logger.debug("[NO QUERY FOUND]")
            return []

        result = self.chroma_taskdocs_coll.query(
            query_texts=[query],
            n_results=top_k,
        )

        ids = result.get("ids", [[]])[0] if result else []
        if not ids:
            return []

        docs_by_id = {doc["task_id"]: doc for doc in self._load_task_documents_from_disk()}
        docs: List[Dict[str, Any]] = []
        for doc_id in ids:
            doc = docs_by_id.get(doc_id)
            if doc:
                docs.append(doc)

        order = {tid: i for i, tid in enumerate(ids)}
        docs.sort(key=lambda d: order.get(d.get("task_id", ""), 10**9))
        return docs

    def get_task_document_texts(self, query: str, top_k: int = 3) -> List[str]:
        """
        Fetch raw task document texts based on similarity search results.

        Args:
            query: Freeform text query used to find related documents.
            top_k: Maximum number of raw documents to return.

        Returns:
            List of raw task document strings ordered by similarity.
        """        
        matches = self.retrieve_similar_task_documents(query, top_k=top_k)
        return [m.get("raw_text", "") for m in matches]

    # ------------------------------------------------------------------
    # Task helpers (for recovery)
    # ------------------------------------------------------------------
    def find_current_task_steps(self) -> List[Dict[str, Any]]:
        """
        List steps across all tasks that are marked as ``current``.
        Ideally, it should only return one step. However, there might be case 
        where multple steps are assigned with ``current`` due to LLM error.

        Returns:
            A list of dictionaries pairing ``task_id`` with the active step
            metadata.
        """        
        results: List[Dict[str, Any]] = []
        for entry in self._iter_task_logs():
            task_id = entry.get("task_id")
            for step in entry.get("steps", []):
                if step.get("status") == "current":
                    results.append({"task_id": task_id, "step": step})
        return results

    def update_step_status(
        self,
        task_id: str,
        action_id: str,
        status: str,
        failure_message: Optional[str] = None,
    ) -> None:
        """
        Update the status of a task step and persist the change.

        Args:
            task_id: Identifier for the task owning the step.
            action_id: The step's action identifier used to locate it.
            status: New status string to assign to the step.
            failure_message: Optional failure detail to attach when updating.
        """        
        entries = self._load_log_entries()
        updated = False
        for entry in entries:
            if entry.get("entry_type") != "task_log" or entry.get("task_id") != task_id:
                continue
            for step in entry.get("steps", []):
                if step.get("action_id") == action_id:
                    step["status"] = status
                    if failure_message is not None:
                        step["failure_message"] = failure_message
                    updated = True
                    break
            if updated:
                entry["updated_at"] = datetime.datetime.utcnow().isoformat()
                break
        if updated:
            self._write_log_entries(entries)
