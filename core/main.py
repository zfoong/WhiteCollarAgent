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


def _initial_settings() -> tuple[str, str, bool]:
    """Determine initial provider and API key settings.

    Returns:
        Tuple of (provider, api_key, has_valid_key) where has_valid_key
        indicates if a working API key was found.
    """
    # If LLM_PROVIDER is explicitly set, use it
    explicit_provider = os.getenv("LLM_PROVIDER")
    if explicit_provider:
        key_lookup = {
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "byteplus": "BYTEPLUS_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        key_name = key_lookup.get(explicit_provider, "")
        api_key = os.getenv(key_name, "") if key_name else ""
        # Remote (Ollama) doesn't require API key
        has_key = bool(api_key) or explicit_provider == "remote"
        return explicit_provider, api_key, has_key

    # Default to BytePlus if its API key is available
    byteplus_key = os.getenv("BYTEPLUS_API_KEY", "")
    if byteplus_key:
        return "byteplus", byteplus_key, True

    # Auto-detect provider based on which API key is set
    fallback_providers = [
        ("openai", "OPENAI_API_KEY"),
        ("gemini", "GOOGLE_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ]
    for provider, key_name in fallback_providers:
        api_key = os.getenv(key_name, "")
        if api_key:
            return provider, api_key, True

    # No API keys found - default to openai but flag as not configured
    # This allows the TUI to start so user can configure settings
    return "openai", "", False


def _apply_api_key(provider: str, api_key: str) -> None:
    """Apply provider and API key to environment variables."""
    key_lookup = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "byteplus": "BYTEPLUS_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    key_name = key_lookup.get(provider)
    if key_name and api_key:
        os.environ[key_name] = api_key
    os.environ["LLM_PROVIDER"] = provider


async def main_async() -> None:
    provider, api_key, has_valid_key = _initial_settings()
    _apply_api_key(provider, api_key)

    # Use deferred initialization if no valid API key is configured yet
    # This allows the TUI to start so first-time users can configure settings
    agent = AgentBase(
        data_dir=os.getenv("DATA_DIR", "core/data"),
        chroma_path=os.getenv("CHROMA_PATH", "./chroma_db"),
        llm_provider=provider,
        deferred_init=not has_valid_key,
    )

    # Initialize onboarding manager with agent reference
    from core.onboarding.manager import onboarding_manager
    onboarding_manager.set_agent(agent)

    await agent.run(provider=provider, api_key=api_key)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
