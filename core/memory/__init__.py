# -*- coding: utf-8 -*-
"""
core.memory

Memory management module for the agent file system.

This package provides:
- MemoryManager: RAG-based memory system with ChromaDB backend
- MemoryFileWatcher: File system watcher for automatic index updates
- create_memory_processing_task: Create a task to process events into memories
"""

from core.memory.memory_manager import (
    MemoryManager,
    MemoryPointer,
    MemoryChunk,
    create_memory_processing_task,
)
from core.memory.memory_file_watcher import MemoryFileWatcher


__all__ = [
    "MemoryManager",
    "MemoryPointer",
    "MemoryChunk",
    "MemoryFileWatcher",
    "create_memory_processing_task",
]
