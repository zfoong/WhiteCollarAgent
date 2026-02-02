# -*- coding: utf-8 -*-
"""
core.llm_interface

All LLM calls have to go through this interface
Currently support llm call to open ai api, google gemini, and remote call to Ollama
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import requests
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import OpenAI


# ─────────────────────────── LLM Call Types for Session Caching ───────────────────────────
class LLMCallType(str, Enum):
    """Types of LLM calls for session cache keying.

    Each call type gets its own session cache within a task, so that
    different prompt structures (reasoning vs action selection) don't
    pollute each other's KV cache.
    """
    REASONING = "reasoning"
    ACTION_SELECTION = "action_selection"
    GUI_REASONING = "gui_reasoning"
    GUI_ACTION_SELECTION = "gui_action_selection"

from core.models.factory import ModelFactory
from core.models.types import InterfaceType
from core.google_gemini_client import GeminiAPIError, GeminiClient
from core.state.agent_state import STATE
from decorators.profiler import profile, OperationCategory

# Logging setup — fall back to a basic logger if the project‑level logger
# is not available (e.g. when running this file standalone).
try:
    from core.logger import logger  # type: ignore
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ─────────────────────────── Shared Cache Configuration ───────────────────────────
@dataclass
class CacheConfig:
    """Shared cache configuration for all LLM providers.

    This configuration is used by both BytePlus (prefix/session caches) and
    Anthropic (ephemeral cache_control).

    Attributes:
        prefix_cache_ttl: TTL for prefix caches in seconds (BytePlus only).
            Anthropic uses a fixed 5-minute TTL for ephemeral caches.
        session_cache_ttl: TTL for session caches in seconds (BytePlus only).
        min_cache_tokens: Minimum system prompt length (chars) for caching.
            Rough approximation: 500 chars ≈ 1024 tokens.
    """
    prefix_cache_ttl: int = 3600  # 1 hour default
    session_cache_ttl: int = 7200  # 2 hours for long tasks
    min_cache_tokens: int = 500  # ~1024 tokens minimum

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """Load cache configuration from environment variables."""
        return cls(
            prefix_cache_ttl=int(os.getenv("CACHE_PREFIX_TTL", "3600")),
            session_cache_ttl=int(os.getenv("CACHE_SESSION_TTL", "7200")),
            min_cache_tokens=int(os.getenv("CACHE_MIN_TOKENS", "500")),
        )


# Global cache configuration instance
_cache_config: Optional[CacheConfig] = None


def get_cache_config() -> CacheConfig:
    """Get the global cache configuration, initializing from env if needed."""
    global _cache_config
    if _cache_config is None:
        _cache_config = CacheConfig.from_env()
    return _cache_config


# ─────────────────────────── Cache Metrics Tracking ───────────────────────────
@dataclass
class CacheMetricsEntry:
    """Metrics for a single cache operation type."""
    total_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    tokens_cached: int = 0
    tokens_uncached: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        if self.total_calls == 0:
            return 0.0
        return (self.cache_hits / self.total_calls) * 100

    @property
    def token_cache_rate(self) -> float:
        """Calculate percentage of tokens served from cache."""
        total = self.tokens_cached + self.tokens_uncached
        if total == 0:
            return 0.0
        return (self.tokens_cached / total) * 100


class CacheMetrics:
    """Tracks cache effectiveness metrics per provider and operation type.

    Usage:
        metrics = CacheMetrics()
        metrics.record_hit("byteplus", "prefix", cached_tokens=500, total_tokens=800)
        metrics.record_miss("byteplus", "session")
        print(metrics.get_summary())
    """

    def __init__(self) -> None:
        # Structure: provider -> cache_type -> CacheMetricsEntry
        self._metrics: Dict[str, Dict[str, CacheMetricsEntry]] = {}

    def _get_entry(self, provider: str, cache_type: str) -> CacheMetricsEntry:
        """Get or create metrics entry for provider/cache_type."""
        if provider not in self._metrics:
            self._metrics[provider] = {}
        if cache_type not in self._metrics[provider]:
            self._metrics[provider][cache_type] = CacheMetricsEntry()
        return self._metrics[provider][cache_type]

    def record_hit(
        self,
        provider: str,
        cache_type: str,
        cached_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Record a cache hit with optional token counts."""
        entry = self._get_entry(provider, cache_type)
        entry.total_calls += 1
        entry.cache_hits += 1
        entry.tokens_cached += cached_tokens
        entry.tokens_uncached += max(0, total_tokens - cached_tokens)

        logger.info(
            f"[CACHE METRICS] {provider}/{cache_type}: HIT "
            f"(cached={cached_tokens}, total={total_tokens}, "
            f"hit_rate={entry.hit_rate:.1f}%, token_cache_rate={entry.token_cache_rate:.1f}%)"
        )

    def record_miss(
        self,
        provider: str,
        cache_type: str,
        total_tokens: int = 0,
    ) -> None:
        """Record a cache miss."""
        entry = self._get_entry(provider, cache_type)
        entry.total_calls += 1
        entry.cache_misses += 1
        entry.tokens_uncached += total_tokens

        logger.info(
            f"[CACHE METRICS] {provider}/{cache_type}: MISS "
            f"(total={total_tokens}, hit_rate={entry.hit_rate:.1f}%)"
        )

    def get_summary(self) -> str:
        """Get a formatted summary of all cache metrics."""
        lines = ["=" * 60, "CACHE METRICS SUMMARY", "=" * 60]

        for provider, cache_types in self._metrics.items():
            lines.append(f"\n{provider.upper()}:")
            for cache_type, entry in cache_types.items():
                lines.append(
                    f"  {cache_type}:"
                    f"\n    Calls: {entry.total_calls} "
                    f"(hits={entry.cache_hits}, misses={entry.cache_misses})"
                    f"\n    Hit Rate: {entry.hit_rate:.1f}%"
                    f"\n    Tokens Cached: {entry.tokens_cached:,}"
                    f"\n    Tokens Uncached: {entry.tokens_uncached:,}"
                    f"\n    Token Cache Rate: {entry.token_cache_rate:.1f}%"
                )

        lines.append("=" * 60)
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics."""
        self._metrics.clear()


# Global cache metrics instance
_cache_metrics: Optional[CacheMetrics] = None


def get_cache_metrics() -> CacheMetrics:
    """Get the global cache metrics instance."""
    global _cache_metrics
    if _cache_metrics is None:
        _cache_metrics = CacheMetrics()
    return _cache_metrics


# ─────────────────────────── BytePlus Cache Manager ───────────────────────────
class BytePlusCacheManager:
    """Manages both prefix and session caches for BytePlus Context API.

    Prefix Cache:
        - For independent calls (event summarization, triggers, etc.)
        - Static system prompt cached, varying user prompts
        - Keyed by hash of system prompt

    Session Cache:
        - For task/GUI calls where context APPENDS over time
        - Context grows with each call (multi-turn-like)
        - Keyed by composite key: task_id:call_type
        - Each call type (reasoning, action_selection, etc.) gets its own session
          so different prompt structures don't pollute each other's KV cache
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        # Prefix cache: prompt_hash -> cache_id (for independent calls)
        self._prefix_cache_registry: Dict[str, str] = {}
        # Session cache: "task_id:call_type" -> cache_id (for task/GUI calls)
        # Each call type within a task gets its own session cache
        self._session_cache_registry: Dict[str, str] = {}
        # Use shared cache configuration
        self._config = get_cache_config()

    # ─────────────────── Session Key Helper ───────────────────

    def _make_session_key(self, task_id: str, call_type: str) -> str:
        """Create composite key for session cache: task_id:call_type"""
        return f"{task_id}:{call_type}"

    # ─────────────────── Prefix Cache Methods ───────────────────

    def get_or_create_prefix_cache(
        self, system_prompt: str, ttl: Optional[int] = None
    ) -> Optional[str]:
        """Get existing cache_id or create new prefix cache for system prompt.

        Args:
            system_prompt: The static system prompt to cache.
            ttl: Time-to-live in seconds. Defaults to BYTEPLUS_PREFIX_CACHE_TTL.

        Returns:
            cache_id if successful, None if cache creation failed.
        """
        prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]

        if prompt_hash in self._prefix_cache_registry:
            logger.debug(f"[CACHE] Prefix cache hit for hash {prompt_hash}")
            return self._prefix_cache_registry[prompt_hash]

        cache_id = self._create_cache(
            system_prompt,
            mode="prefix",
            ttl=ttl or self._config.prefix_cache_ttl,
        )
        if cache_id:
            self._prefix_cache_registry[prompt_hash] = cache_id
            logger.info(f"[CACHE] Created prefix cache {cache_id} for hash {prompt_hash}")
        return cache_id

    def invalidate_prefix_cache(self, system_prompt: str) -> None:
        """Remove prefix cache entry (e.g., when cache expired)."""
        prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]
        removed = self._prefix_cache_registry.pop(prompt_hash, None)
        if removed:
            logger.info(f"[CACHE] Invalidated prefix cache {removed} for hash {prompt_hash}")

    # ─────────────────── Session Cache Methods ───────────────────

    def create_session_cache(
        self, task_id: str, call_type: str, system_prompt: str, ttl: Optional[int] = None
    ) -> Optional[str]:
        """Create a new session cache for a specific call type within a task.

        Called at task start. The cache will accumulate context as the task progresses.
        Each call type (reasoning, action_selection, etc.) gets its own session cache.

        Args:
            task_id: Unique identifier for the task.
            call_type: Type of LLM call (e.g., "reasoning", "action_selection").
            system_prompt: Initial system prompt for the session.
            ttl: Time-to-live in seconds. Defaults to BYTEPLUS_SESSION_CACHE_TTL.

        Returns:
            cache_id if successful, None if cache creation failed.
        """
        session_key = self._make_session_key(task_id, call_type)
        if session_key in self._session_cache_registry:
            logger.warning(f"[CACHE] Session cache already exists for {session_key}")
            return self._session_cache_registry[session_key]

        cache_id = self._create_cache(
            system_prompt,
            mode="session",
            ttl=ttl or self._config.session_cache_ttl,
            truncation_strategy={"type": "rolling_tokens", "rolling_tokens": True},
        )
        if cache_id:
            self._session_cache_registry[session_key] = cache_id
            logger.info(f"[CACHE] Created session cache {cache_id} for {session_key}")
        return cache_id

    def get_session_cache(self, task_id: str, call_type: str) -> Optional[str]:
        """Get the session cache_id for a task and call type, if it exists."""
        session_key = self._make_session_key(task_id, call_type)
        return self._session_cache_registry.get(session_key)

    def end_session(self, task_id: str, call_type: str) -> None:
        """Clean up session cache for a specific call type when task ends."""
        session_key = self._make_session_key(task_id, call_type)
        cache_id = self._session_cache_registry.pop(session_key, None)
        if cache_id:
            logger.info(f"[CACHE] Ended session cache {cache_id} for {session_key}")

    def end_all_sessions_for_task(self, task_id: str) -> None:
        """Clean up ALL session caches for a task (all call types)."""
        keys_to_remove = [k for k in self._session_cache_registry if k.startswith(f"{task_id}:")]
        for key in keys_to_remove:
            cache_id = self._session_cache_registry.pop(key, None)
            if cache_id:
                logger.info(f"[CACHE] Ended session cache {cache_id} for {key}")

    def has_session(self, task_id: str, call_type: str) -> bool:
        """Check if a session cache exists for the given task and call type."""
        session_key = self._make_session_key(task_id, call_type)
        return session_key in self._session_cache_registry

    # ─────────────────── Chat with Cache ───────────────────

    def chat_with_cache(
        self,
        cache_id: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Send a message using a cache (prefix or session).

        Args:
            cache_id: The cache_id to use.
            user_prompt: The user prompt to send.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            Raw response dict from the API.

        Raises:
            requests.HTTPError: If the API call fails.
        """
        url = f"{self.base_url.rstrip('/')}/context/chat"
        payload = {
            "model": self.model,
            "cache_id": cache_id,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        return response.json()

    # ─────────────────── Internal Helpers ───────────────────

    def _create_cache(
        self,
        system_prompt: str,
        mode: str,
        ttl: int,
        truncation_strategy: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a new cache via /context/create endpoint.

        Args:
            system_prompt: The system prompt to initialize the cache with.
            mode: Either "prefix" or "session".
            ttl: Time-to-live in seconds.
            truncation_strategy: Optional truncation config for session caches.

        Returns:
            cache_id if successful, None if creation failed.
        """
        url = f"{self.base_url.rstrip('/')}/context/create"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}],
            "mode": mode,
            "ttl": ttl,
        }
        if truncation_strategy:
            payload["truncation_strategy"] = truncation_strategy

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result.get("id")
        except requests.RequestException as e:
            logger.warning(f"[CACHE] Failed to create {mode} cache: {e}")
            return None


class LLMInterface:
    """Simple wrapper to interact with multiple Large-Language-Model back-ends.

    Supported providers
    -------------------
    * ``openai``  – OpenAI Chat Completions API
    * ``remote``  – Local Ollama HTTP endpoint (``/api/generate``)
    * ``gemini``  – Google Generative AI (Gemini) API
    * ``byteplus`` – BytePlus ModelArk Chat Completions API
    * ``anthropic`` – Anthropic Claude API
    """

    _CODE_BLOCK_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        db_interface: Optional[Any] = None,
        temperature: float = 0.0,
        max_tokens: int = 8000,
        deferred: bool = False,
    ) -> None:
        self.db_interface = db_interface
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._gemini_client: GeminiClient | None = None
        self._anthropic_client = None
        self._initialized = False
        self._deferred = deferred

        ctx = ModelFactory.create(
            provider=provider,
            interface=InterfaceType.LLM,
            model_override=model,
            deferred=deferred,
        )

        logger.info(f"[LLM FACTORY] {ctx}")

        self.provider = ctx["provider"]
        self.model = ctx["model"]
        self.client = ctx["client"]
        self._gemini_client = ctx["gemini_client"]
        self.remote_url = ctx["remote_url"]
        self._anthropic_client = ctx["anthropic_client"]
        self._initialized = ctx.get("initialized", False)

        # Initialize BytePlus-specific attributes
        self._byteplus_cache_manager: Optional[BytePlusCacheManager] = None

        if ctx["byteplus"]:
            self.api_key = ctx["byteplus"]["api_key"]
            self.byteplus_base_url = ctx["byteplus"]["base_url"]
            # Initialize cache manager for BytePlus (caching always enabled)
            self._byteplus_cache_manager = BytePlusCacheManager(
                api_key=self.api_key,
                base_url=self.byteplus_base_url,
                model=self.model,
            )

    @property
    def is_initialized(self) -> bool:
        """Check if the LLM client is properly initialized."""
        return self._initialized

    def reinitialize(self, provider: Optional[str] = None) -> bool:
        """Reinitialize the LLM client with current environment variables.

        Args:
            provider: Optional provider override. If None, uses current provider.

        Returns:
            True if initialization was successful, False otherwise.
        """
        target_provider = provider or self.provider
        try:
            logger.info(f"[LLM] Reinitializing with provider: {target_provider}")
            ctx = ModelFactory.create(
                provider=target_provider,
                interface=InterfaceType.LLM,
                model_override=None,
                deferred=False,
            )

            self.provider = ctx["provider"]
            self.model = ctx["model"]
            self.client = ctx["client"]
            self._gemini_client = ctx["gemini_client"]
            self.remote_url = ctx["remote_url"]
            self._anthropic_client = ctx["anthropic_client"]
            self._initialized = ctx.get("initialized", False)

            if ctx["byteplus"]:
                self.api_key = ctx["byteplus"]["api_key"]
                self.byteplus_base_url = ctx["byteplus"]["base_url"]
                # Reinitialize cache manager for BytePlus
                self._byteplus_cache_manager = BytePlusCacheManager(
                    api_key=self.api_key,
                    base_url=self.byteplus_base_url,
                    model=self.model,
                )
            else:
                self._byteplus_cache_manager = None

            logger.info(f"[LLM] Reinitialized successfully with provider: {self.provider}, model: {self.model}")
            return self._initialized
        except EnvironmentError as e:
            logger.warning(f"[LLM] Failed to reinitialize - missing API key: {e}")
            return False
        except Exception as e:
            logger.error(f"[LLM] Failed to reinitialize - unexpected error: {e}", exc_info=True)
            return False

    # ───────────────────────────  Public helpers  ────────────────────────────
    def _generate_response_sync(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Synchronous implementation shared by sync/async entry points."""
        if user_prompt is None:
            raise ValueError("`user_prompt` cannot be None.")

        if log_response:
            logger.info(f"[LLM SEND] system={system_prompt} | user={user_prompt}")

        if self.provider == "openai":
            response = self._generate_openai(system_prompt, user_prompt)
        elif self.provider == "remote":
            response = self._generate_ollama(system_prompt, user_prompt)
        elif self.provider == "gemini":
            response = self._generate_gemini(system_prompt, user_prompt)
        elif self.provider == "byteplus":
            response = self._generate_byteplus(system_prompt, user_prompt)
        elif self.provider == "anthropic":
            response = self._generate_anthropic(system_prompt, user_prompt)
        else:  # pragma: no cover
            raise RuntimeError(f"Unknown provider {self.provider!r}")

        cleaned = re.sub(self._CODE_BLOCK_RE, "", response.get("content", "").strip())

        STATE.set_agent_property("token_count", STATE.get_agent_property("token_count", 0) + response.get("tokens_used", 0))
        if log_response:
            logger.info(f"[LLM RECV] {cleaned}")
        return cleaned

    @profile("llm_generate_response", OperationCategory.LLM)
    def generate_response(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Generate a single response from the configured provider."""
        return self._generate_response_sync(system_prompt, user_prompt, log_response)

    @profile("llm_generate_response_async", OperationCategory.LLM)
    async def generate_response_async(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Async wrapper that defers the blocking call to a worker thread."""
        return await asyncio.to_thread(
            self._generate_response_sync,
            system_prompt,
            user_prompt,
            log_response,
        )

    # ─────────────────── Session Cache Methods (BytePlus only) ───────────────────

    def create_session_cache(
        self, task_id: str, call_type: str, system_prompt: str
    ) -> Optional[str]:
        """Create a session cache for a specific call type within a task (BytePlus only).

        Should be called at task start. The session will accumulate context
        as the task progresses. Each call type gets its own session cache.

        Args:
            task_id: Unique identifier for the task.
            call_type: Type of LLM call (use LLMCallType enum values).
            system_prompt: Initial system prompt for the session.

        Returns:
            cache_id if successful, None if caching not available or failed.
        """
        if self.provider != "byteplus" or not self._byteplus_cache_manager:
            logger.debug("[SESSION] Session cache only available for BytePlus provider")
            return None

        return self._byteplus_cache_manager.create_session_cache(task_id, call_type, system_prompt)

    def end_session_cache(self, task_id: str, call_type: str) -> None:
        """End a session cache for a specific call type (BytePlus only).

        Should be called at task end to clean up resources.

        Args:
            task_id: The task ID.
            call_type: Type of LLM call (use LLMCallType enum values).
        """
        if self.provider == "byteplus" and self._byteplus_cache_manager:
            self._byteplus_cache_manager.end_session(task_id, call_type)

    def end_all_session_caches(self, task_id: str) -> None:
        """End ALL session caches for a task (all call types).

        Convenience method to clean up all caches when a task ends.

        Args:
            task_id: The task whose sessions should be ended.
        """
        if self.provider == "byteplus" and self._byteplus_cache_manager:
            self._byteplus_cache_manager.end_all_sessions_for_task(task_id)

    def has_session_cache(self, task_id: str, call_type: str) -> bool:
        """Check if a session cache exists for the given task and call type."""
        if self.provider != "byteplus" or not self._byteplus_cache_manager:
            return False
        return self._byteplus_cache_manager.has_session(task_id, call_type)

    def get_cache_stats(self) -> str:
        """Get a summary of cache metrics for all providers.

        Returns a formatted string with cache hit rates, token savings, etc.
        Useful for validating cache effectiveness.

        Example output:
            ============================================================
            CACHE METRICS SUMMARY
            ============================================================

            BYTEPLUS:
              prefix:
                Calls: 10 (hits=8, misses=2)
                Hit Rate: 80.0%
                Tokens Cached: 5000
                Tokens Uncached: 1200
                Token Cache Rate: 80.6%
              session:
                Calls: 25 (hits=22, misses=3)
                Hit Rate: 88.0%
                ...
            ============================================================
        """
        return get_cache_metrics().get_summary()

    def reset_cache_stats(self) -> None:
        """Reset all cache metrics to zero.

        Useful for starting a new measurement period.
        """
        get_cache_metrics().reset()
        logger.info("[CACHE] Cache metrics reset")

    def _generate_response_with_session_sync(
        self,
        task_id: str,
        call_type: str,
        user_prompt: str,
        system_prompt_for_new_session: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Generate response using session cache for the given task and call type.

        If no session exists and system_prompt_for_new_session is provided,
        creates a new session cache first. Each call type gets its own session.

        Args:
            task_id: The task ID to use for session cache.
            call_type: Type of LLM call (use LLMCallType enum values).
            user_prompt: The user prompt to send.
            system_prompt_for_new_session: System prompt to use if creating new session.
            log_response: Whether to log the response.

        Returns:
            The cleaned response content.
        """
        if user_prompt is None:
            raise ValueError("`user_prompt` cannot be None.")

        if log_response:
            logger.info(f"[LLM SESSION] task={task_id} call_type={call_type} | user={user_prompt}")

        # If not BytePlus, fall back to standard
        if self.provider != "byteplus" or not self._byteplus_cache_manager:
            return self._generate_response_sync(
                system_prompt_for_new_session, user_prompt, log_response=False
            )

        # Check if session exists, create if needed
        if not self._byteplus_cache_manager.has_session(task_id, call_type):
            if system_prompt_for_new_session:
                cache_id = self._byteplus_cache_manager.create_session_cache(
                    task_id, call_type, system_prompt_for_new_session
                )
                if not cache_id:
                    logger.warning("[SESSION] Failed to create session, falling back to standard")
                    return self._generate_response_sync(
                        system_prompt_for_new_session, user_prompt, log_response=False
                    )
            else:
                raise ValueError(
                    f"No session for task {task_id}:{call_type} and no system prompt to create one"
                )

        # Use the session cache
        response = self._generate_byteplus_with_session(task_id, call_type, user_prompt)

        cleaned = re.sub(self._CODE_BLOCK_RE, "", response.get("content", "").strip())

        STATE.set_agent_property(
            "token_count",
            STATE.get_agent_property("token_count", 0) + response.get("tokens_used", 0)
        )
        if log_response:
            logger.info(f"[LLM SESSION RECV] {cleaned}")
        return cleaned

    def generate_response_with_session(
        self,
        task_id: str,
        call_type: str,
        user_prompt: str,
        system_prompt_for_new_session: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Synchronous session-based response generation.

        Args:
            task_id: The task ID to use for session cache.
            call_type: Type of LLM call (use LLMCallType enum values).
            user_prompt: The user prompt to send.
            system_prompt_for_new_session: System prompt to use if creating new session.
            log_response: Whether to log the response.
        """
        return self._generate_response_with_session_sync(
            task_id, call_type, user_prompt, system_prompt_for_new_session, log_response
        )

    @profile("llm_generate_response_with_session_async", OperationCategory.LLM)
    async def generate_response_with_session_async(
        self,
        task_id: str,
        call_type: str,
        user_prompt: str,
        system_prompt_for_new_session: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Async wrapper for session-based response generation.

        Args:
            task_id: The task ID to use for session cache.
            call_type: Type of LLM call (use LLMCallType enum values).
            user_prompt: The user prompt to send.
            system_prompt_for_new_session: System prompt to use if creating new session.
            log_response: Whether to log the response.
        """
        return await asyncio.to_thread(
            self._generate_response_with_session_sync,
            task_id,
            call_type,
            user_prompt,
            system_prompt_for_new_session,
            log_response,
        )

    def _generate_byteplus_with_session(
        self, task_id: str, call_type: str, user_prompt: str
    ) -> Dict[str, Any]:
        """Use Context API with session caching for task/GUI calls.

        The context grows with each call as the session cache accumulates messages.
        Each call type has its own session to avoid polluting different prompt structures.
        """
        token_count_input = token_count_output = 0
        total_tokens = 0
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None
        session_key = f"{task_id}:{call_type}"

        try:
            cache_id = self._byteplus_cache_manager.get_session_cache(task_id, call_type)
            if not cache_id:
                raise ValueError(f"No session cache found for {session_key}")

            result = self._byteplus_cache_manager.chat_with_cache(
                cache_id=cache_id,
                user_prompt=user_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            logger.info(f"BYTEPLUS SESSION RESPONSE: {result}")

            # Parse response
            choices = result.get("choices", [])
            if choices:
                content = (
                    choices[0].get("message", {}).get("content")
                    or choices[0].get("delta", {}).get("content", "")
                    or ""
                ).strip()

            total_tokens = int(result.get("usage", {}).get("total_tokens", 0))
            usage = result.get("usage") or {}
            token_count_input = int(usage.get("prompt_tokens", 0))
            token_count_output = int(usage.get("completion_tokens", 0))

            # Log cache info and record metrics
            cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
            metrics = get_cache_metrics()
            if cached_tokens and cached_tokens > 0:
                logger.info(f"[CACHE] BytePlus session cache hit: {cached_tokens}/{token_count_input} tokens cached")
                metrics.record_hit("byteplus", "session", cached_tokens=cached_tokens, total_tokens=token_count_input)
            else:
                # First call in session or growing context
                metrics.record_miss("byteplus", "session", total_tokens=token_count_input)

            status = "success"

        except Exception as exc:
            exc_obj = exc
            logger.error(f"Error calling BytePlus Session API for {session_key}: {exc}")

        self._log_to_db(
            f"[SESSION:{session_key}]",  # Mark as session call in logs with call_type
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
        }

    # ───────────────────── Provider‑specific private helpers ─────────────────────
    @profile("llm_openai_call", OperationCategory.LLM)
    def _generate_openai(self, system_prompt: str | None, user_prompt: str) -> str:
        token_count_input = token_count_output = 0
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None
        
        try:
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content.strip()
            token_count_input = response.usage.prompt_tokens
            token_count_output = response.usage.completion_tokens
            status = "success"
        except Exception as exc: 
            exc_obj = exc
            logger.error(f"Error calling OpenAI API: {exc}")

        total_tokens = token_count_input + token_count_output

        self._log_to_db(
            system_prompt,
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
        }

    @profile("llm_ollama_call", OperationCategory.LLM)
    def _generate_ollama(self, system_prompt: str | None, user_prompt: str) -> str:
        token_count_input = token_count_output = 0
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None

        try:
            payload = {
                "model": self.model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                }
            }
            url: str = f"{self.remote_url.rstrip('/')}/generate"
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()

            content = result.get("response", "").strip()
            total_tokens = result.get("usage", {}).get("total_tokens", 0)
            token_count_input = result.get("prompt_eval_count", 0)
            token_count_output = result.get("eval_count", 0)
            status = "success"
        except Exception as exc:  
            exc_obj = exc
            logger.error(f"Error calling Ollama API: {exc}")

        self._log_to_db(
            system_prompt,
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
        }

    @profile("llm_gemini_call", OperationCategory.LLM)
    def _generate_gemini(self, system_prompt: str | None, user_prompt: str) -> str:
        token_count_input = token_count_output = 0  # Not returned by the Gemini SDK
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None
    
        try:
            if not self._gemini_client:
                raise RuntimeError("Gemini client was not initialised.")

            content = self._gemini_client.generate_text(
                self.model,
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
            status = "success"
        except GeminiAPIError as exc:  # pragma: no cover
            exc_obj = exc
            logger.error(f"Gemini API rejected the prompt: {exc}")
        except Exception as exc:  # pragma: no cover
            exc_obj = exc
            logger.error(f"Error calling Gemini API: {exc}")
    
        self._log_to_db(
            system_prompt,
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return content or {
            "tokens_used": 0,
            "content": ""
        }

    @profile("llm_byteplus_call", OperationCategory.LLM)
    def _generate_byteplus(self, system_prompt: str | None, user_prompt: str) -> Dict[str, Any]:
        """Generate response using BytePlus with automatic prefix caching.

        Routes to prefix cache or standard API based on context.
        """
        config = get_cache_config()
        # Use prefix caching if:
        # - System prompt is provided
        # - System prompt is long enough (uses shared config)
        # - Cache manager is available
        if (
            system_prompt
            and len(system_prompt) >= config.min_cache_tokens
            and self._byteplus_cache_manager
        ):
            return self._generate_byteplus_with_prefix_cache(system_prompt, user_prompt)

        # Standard path (no caching)
        return self._generate_byteplus_standard(system_prompt, user_prompt)

    def _generate_byteplus_with_prefix_cache(
        self, system_prompt: str, user_prompt: str
    ) -> Dict[str, Any]:
        """Use Context API with prefix caching.

        The system prompt is cached and reused across calls with the same content.
        Only the user prompt is processed fresh each time.
        """
        token_count_input = token_count_output = 0
        total_tokens = 0
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None

        try:
            # Get or create prefix cache for this system prompt
            cache_id = self._byteplus_cache_manager.get_or_create_prefix_cache(system_prompt)

            if not cache_id:
                # Cache creation failed, fall back to standard
                logger.warning("[CACHE] Prefix cache creation failed, falling back to standard API")
                return self._generate_byteplus_standard(system_prompt, user_prompt)

            # Use the cache for the request
            result = self._byteplus_cache_manager.chat_with_cache(
                cache_id=cache_id,
                user_prompt=user_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            logger.info(f"BYTEPLUS CACHED RESPONSE: {result}")

            # Parse response (same format as chat/completions)
            choices = result.get("choices", [])
            if choices:
                content = (
                    choices[0].get("message", {}).get("content")
                    or choices[0].get("delta", {}).get("content", "")
                    or ""
                ).strip()

            total_tokens = int(result.get("usage", {}).get("total_tokens", 0))
            usage = result.get("usage") or {}
            token_count_input = int(usage.get("prompt_tokens", 0))
            token_count_output = int(usage.get("completion_tokens", 0))

            # Log cache hit info if available and record metrics
            cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
            metrics = get_cache_metrics()
            if cached_tokens and cached_tokens > 0:
                logger.info(f"[CACHE] BytePlus prefix cache hit: {cached_tokens}/{token_count_input} tokens cached")
                metrics.record_hit("byteplus", "prefix", cached_tokens=cached_tokens, total_tokens=token_count_input)
            else:
                # First call or cache miss
                metrics.record_miss("byteplus", "prefix", total_tokens=token_count_input)

            status = "success"

        except requests.HTTPError as e:
            # Check if this is a cache-related error (expired, not found)
            if e.response is not None and e.response.status_code in (404, 410):
                logger.warning(f"[CACHE] Cache expired or not found, recreating: {e}")
                # Invalidate and retry once
                self._byteplus_cache_manager.invalidate_prefix_cache(system_prompt)
                cache_id = self._byteplus_cache_manager.get_or_create_prefix_cache(system_prompt)
                if cache_id:
                    try:
                        result = self._byteplus_cache_manager.chat_with_cache(
                            cache_id=cache_id,
                            user_prompt=user_prompt,
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                        )
                        choices = result.get("choices", [])
                        if choices:
                            content = (
                                choices[0].get("message", {}).get("content")
                                or choices[0].get("delta", {}).get("content", "")
                                or ""
                            ).strip()
                        total_tokens = int(result.get("usage", {}).get("total_tokens", 0))
                        usage = result.get("usage") or {}
                        token_count_input = int(usage.get("prompt_tokens", 0))
                        token_count_output = int(usage.get("completion_tokens", 0))
                        status = "success"
                    except Exception as retry_exc:
                        exc_obj = retry_exc
                        logger.error(f"[CACHE] Retry failed, falling back: {retry_exc}")
                        return self._generate_byteplus_standard(system_prompt, user_prompt)
                else:
                    # Still can't create cache, fall back
                    return self._generate_byteplus_standard(system_prompt, user_prompt)
            else:
                exc_obj = e
                logger.error(f"Error calling BytePlus Context API: {e}")
        except Exception as exc:
            exc_obj = exc
            logger.error(f"Error calling BytePlus Context API: {exc}")

        self._log_to_db(
            system_prompt,
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
        }

    def _generate_byteplus_standard(
        self, system_prompt: str | None, user_prompt: str
    ) -> Dict[str, Any]:
        """Standard BytePlus API call without caching (uses /chat/completions)."""
        token_count_input = token_count_output = 0
        total_tokens = 0
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None

        try:
            # Build OpenAI-compatible messages array
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            url = f"{self.byteplus_base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": self.model,
                "messages": messages,
                # Wire through sampling + output control
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                # "stream": False,  # default is non-streaming
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            result = response.json()

            logger.info(f"BYTEPLUS RESPONSE: {result}")

            # Non-streaming content location (OpenAI-compatible)
            choices = result.get("choices", [])
            if choices:
                # choices[0].message.content is the OpenAI-compatible field
                content = (
                    choices[0].get("message", {}).get("content")
                    or choices[0].get("delta", {}).get("content", "")
                    or ""
                ).strip()

            total_tokens = int(result.get("usage", {}).get("total_tokens", 0))

            # Token usage (prompt/completion/total)
            usage = result.get("usage") or {}
            token_count_input = int(usage.get("prompt_tokens", 0))
            token_count_output = int(usage.get("completion_tokens", 0))
            status = "success"

        except Exception as exc:  # pragma: no cover
            exc_obj = exc
            logger.error(f"Error calling BytePlus API: {exc}")

        self._log_to_db(
            system_prompt,
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
        }

    @profile("llm_anthropic_call", OperationCategory.LLM)
    def _generate_anthropic(self, system_prompt: str | None, user_prompt: str) -> str:
        """Generate response using Anthropic with automatic prompt caching.

        Anthropic's prompt caching uses `cache_control` markers on content blocks.
        When the system prompt is long enough (>500 chars), we enable caching
        with a 5-minute ephemeral TTL (Anthropic's default, free).

        Cache hits are logged when `cache_read_input_tokens` > 0 in the response.
        """
        token_count_input = token_count_output = 0
        total_tokens = 0
        cached_tokens = 0
        status = "failed"
        content: Optional[str] = None
        exc_obj: Optional[Exception] = None
        config = get_cache_config()

        try:
            if not self._anthropic_client:
                raise RuntimeError("Anthropic client was not initialised.")

            # Build the message with optional system prompt
            message_kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": user_prompt}],
            }

            if system_prompt:
                # Use caching if system prompt is long enough
                if len(system_prompt) >= config.min_cache_tokens:
                    # Format system as list of content blocks with cache_control
                    # Anthropic's ephemeral cache has a 5-minute TTL (free)
                    message_kwargs["system"] = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                else:
                    # Short prompt - use simple string format (no caching)
                    message_kwargs["system"] = system_prompt

            # Always pass temperature for Anthropic (their default is 1.0, not 0.0)
            message_kwargs["temperature"] = self.temperature

            response = self._anthropic_client.messages.create(**message_kwargs)

            # Extract content from the response
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            content = content.strip()

            # Token usage from Anthropic response
            token_count_input = response.usage.input_tokens
            token_count_output = response.usage.output_tokens
            total_tokens = token_count_input + token_count_output

            # Log cache stats if available (Anthropic returns cache info in usage)
            # cache_creation_input_tokens: tokens written to cache (first call)
            # cache_read_input_tokens: tokens read from cache (subsequent calls)
            cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cached_tokens = cache_creation + cache_read

            # Record metrics
            metrics = get_cache_metrics()
            if cache_read > 0:
                logger.info(f"[CACHE] Anthropic cache hit: {cache_read}/{token_count_input} tokens from cache")
                metrics.record_hit("anthropic", "ephemeral", cached_tokens=cache_read, total_tokens=token_count_input)
            elif cache_creation > 0:
                logger.info(f"[CACHE] Anthropic cache created: {cache_creation} tokens cached")
                # Cache creation is a "miss" for the current call but sets up future hits
                metrics.record_miss("anthropic", "ephemeral", total_tokens=token_count_input)
            elif system_prompt and len(system_prompt) >= config.min_cache_tokens:
                # Caching was attempted but no cache info returned - unexpected
                metrics.record_miss("anthropic", "ephemeral", total_tokens=token_count_input)

            status = "success"

        except Exception as exc:  # pragma: no cover
            exc_obj = exc
            logger.error(f"Error calling Anthropic API: {exc}")

        self._log_to_db(
            system_prompt,
            user_prompt,
            content if content is not None else str(exc_obj),
            status,
            token_count_input,
            token_count_output,
        )
        return {
            "tokens_used": total_tokens or 0,
            "content": content or "",
            "cached_tokens": cached_tokens,
        }

    # ─────────────────── Internal utilities ───────────────────
    @profile("llm_log_to_db", OperationCategory.DATABASE)
    def _log_to_db(
        self,
        system_prompt: str | None,
        user_prompt: str,
        output: str,
        status: str,
        token_count_input: int,
        token_count_output: int,
    ) -> None:
        """Persist prompt/response metadata using the optional `db_interface`."""
        if not self.db_interface:
            return

        input_data: Dict[str, Optional[str]] = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }
        config: Dict[str, Any] = {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        self.db_interface.log_prompt(
            input_data=input_data,
            output=output,
            provider=self.provider,
            model=self.model,
            config=config,
            status=status,
            token_count_input=token_count_input,
            token_count_output=token_count_output,
        )

    # ─────────────────── CLI helper for ad‑hoc testing ───────────────────
    def _cli(self) -> None:  # pragma: no cover
        """Run a quick interactive shell for manual testing."""
        logger.debug(
            "Provider: {provider!r}, model: {model!r}",
            provider=self.provider,
            model=self.model,
        )
        while True:
            user_prompt = input("\nEnter prompt (or 'exit'): ").strip()
            if user_prompt.lower() in {"exit", "quit"}:
                break
            response = self.generate_response(user_prompt=user_prompt)
            logger.debug(f"AI Response:\n{response}\n")