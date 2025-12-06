# -*- coding: utf-8 -*-
"""
core.main

Main driver code that starts the **vanilla BaseAgent**.
Environment variables let you tweak connection details without code
changes, making this usable inside Docker containers.

Run this before the core directory, using 'python -m core.main'
"""

import asyncio
import os

from dotenv import load_dotenv

from core.agent_base import AgentBase

load_dotenv()


def _initial_settings() -> tuple[str, str]:
    provider = os.getenv("LLM_PROVIDER", "byteplus")
    key_lookup = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "byteplus": "BYTEPLUS_API_KEY",
    }
    key_name = key_lookup.get(provider, "")
    api_key = os.getenv(key_name, "") if key_name else ""
    return provider, api_key


def _apply_api_key(provider: str, api_key: str) -> None:
    key_lookup = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "byteplus": "BYTEPLUS_API_KEY",
    }
    key_name = key_lookup.get(provider)
    if key_name and api_key:
        os.environ[key_name] = api_key
    os.environ["LLM_PROVIDER"] = provider


async def main_async() -> None:
    provider, api_key = _initial_settings()
    _apply_api_key(provider, api_key)

    agent = AgentBase(
        data_dir=os.getenv("DATA_DIR", "core/data"),
        chroma_path=os.getenv("CHROMA_PATH", "./chroma_db"),
        llm_provider=provider,
    )
    await agent.run(provider=provider, api_key=api_key)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
