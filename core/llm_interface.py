# -*- coding: utf-8 -*-
"""
core.llm_interface

All LLM calls have to go through this interface
Currently support llm call to open ai api, google gemini, and remote call to Ollama
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import requests
from typing import Any, Dict, List, Optional

from openai import OpenAI

from core.models.factory import ModelFactory
from core.models.types import InterfaceType
from core.google_gemini_client import GeminiAPIError, GeminiClient
from core.state.agent_state import STATE
from decorators import profiler, profile, log_events

# Logging setup — fall back to a basic logger if the project‑level logger
# is not available (e.g. when running this file standalone).
try:
    from core.logger import logger  # type: ignore
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class LLMInterface:
    """Simple wrapper to interact with multiple Large-Language-Model back-ends.

    Supported providers
    -------------------
    * ``openai``  – OpenAI Chat Completions API
    * ``remote``  – Local Ollama HTTP endpoint (``/api/generate``)
    * ``gemini``  – Google Generative AI (Gemini) API
    * ``byteplus`` – BytePlus ModelArk Chat Completions API
    """

    _CODE_BLOCK_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        db_interface: Optional[Any] = None,
        temperature: float = 0.0,
        max_tokens: int = 8000
    ) -> None:
        self.db_interface = db_interface
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._gemini_client: GeminiClient | None = None

        INFO_KEY = "singleton"
        info = (db_interface.get_agent_info(INFO_KEY) if db_interface else {}) or {}

        resolved_provider = provider or info.get("provider", "gemini")

        ctx = ModelFactory.create(
            provider=resolved_provider,
            interface=InterfaceType.LLM,
            model_override=model or info.get("model"),
        )

        self.provider = ctx["provider"]
        self.model = ctx["model"]
        self.client = ctx["client"]
        self._gemini_client = ctx["gemini_client"]
        self.remote_url = ctx["remote_url"]

        if ctx["byteplus"]:
            self.api_key = ctx["byteplus"]["api_key"]
            self.byteplus_base_url = ctx["byteplus"]["base_url"]

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
        else:  # pragma: no cover
            raise RuntimeError(f"Unknown provider {self.provider!r}")

        cleaned = re.sub(self._CODE_BLOCK_RE, "", response.get("content", "").strip())

        STATE.set_agent_property("token_count", STATE.get_agent_property("token_count", 0) + response.get("tokens_used", 0))
        if log_response:
            logger.info(f"[LLM RECV] {cleaned}")
        return cleaned

    # @log_events(name="generate_response")
    # @profile("llm_generate_response")
    def generate_response(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        log_response: bool = True,
    ) -> str:
        """Generate a single response from the configured provider."""
        return self._generate_response_sync(system_prompt, user_prompt, log_response)

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

    # ───────────────────── Provider‑specific private helpers ─────────────────────
    @log_events(name="_generate_ollama")
    @profile("llm_openai_call")
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

    @log_events(name="_generate_ollama")
    @profile("llm_ollama_call")
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

    @log_events(name="_generate_gemini")
    @profile("llm_gemini_call")
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

    @log_events(name="_generate_byteplus")
    @profile("llm_byteplus_call")
    def _generate_byteplus(self, system_prompt: str | None, user_prompt: str) -> str:
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

            logger.info(f"BUTTPLUG RESPONSE: {result}")

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

    # ─────────────────── Internal utilities ───────────────────
    @log_events(name="_log_to_db")
    @profile("_log_to_db")
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