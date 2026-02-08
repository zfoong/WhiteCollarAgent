# -*- coding: utf-8 -*-
"""
Created on Fri Aug  1 14:17:29 2025

@author: zfoong
"""

from __future__ import annotations
import os
import asyncio
import time
import base64, requests
from typing import Any, Dict, Optional

import re

from core.models.factory import ModelFactory
from core.models.types import InterfaceType
from core.google_gemini_client import GeminiClient
from core.logger import logger
from core.state.agent_state import STATE
from core.llm import get_cache_metrics, get_cache_config

class VLMInterface:
    _CODE_BLOCK_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.5,
        deferred: bool = False,
    ) -> None:
        self.provider = provider
        self.temperature = temperature
        self._gemini_client: GeminiClient | None = None
        self._anthropic_client = None
        self._initialized = False
        self._deferred = deferred

        ctx = ModelFactory.create(
            provider=provider,
            interface=InterfaceType.VLM,
            model_override=model,
            deferred=deferred,
        )

        self.model = ctx["model"]
        self.client = ctx["client"]
        self._gemini_client = ctx["gemini_client"]
        self.remote_url = ctx["remote_url"]
        self._anthropic_client = ctx.get("anthropic_client")
        self._initialized = ctx.get("initialized", False)

        if ctx["byteplus"]:
            self.api_key = ctx["byteplus"]["api_key"]
            self.byteplus_base_url = ctx["byteplus"]["base_url"]

    @property
    def is_initialized(self) -> bool:
        """Check if the VLM client is properly initialized."""
        return self._initialized

    def reinitialize(self, provider: Optional[str] = None) -> bool:
        """Reinitialize the VLM client with current environment variables.

        Args:
            provider: Optional provider override. If None, uses current provider.

        Returns:
            True if initialization was successful, False otherwise.
        """
        target_provider = provider or self.provider
        try:
            logger.info(f"[VLM] Reinitializing with provider: {target_provider}")
            ctx = ModelFactory.create(
                provider=target_provider,
                interface=InterfaceType.VLM,
                model_override=None,
                deferred=False,
            )

            self.provider = ctx["provider"]
            self.model = ctx["model"]
            self.client = ctx["client"]
            self._gemini_client = ctx["gemini_client"]
            self.remote_url = ctx["remote_url"]
            self._anthropic_client = ctx.get("anthropic_client")
            self._initialized = ctx.get("initialized", False)

            if ctx["byteplus"]:
                self.api_key = ctx["byteplus"]["api_key"]
                self.byteplus_base_url = ctx["byteplus"]["base_url"]

            logger.info(f"[VLM] Reinitialized successfully with provider: {self.provider}, model: {self.model}")
            return self._initialized
        except EnvironmentError as e:
            logger.warning(f"[VLM] Failed to reinitialize - missing API key: {e}")
            return False
        except Exception as e:
            logger.error(f"[VLM] Failed to reinitialize - unexpected error: {e}", exc_info=True)
            return False

    # ───────────────────────── Public ─────────────────────────
    # Should only be used when looking for specific attributes/items in
    # the image/screen. For example, the prompt should be "Is the google
    # chrome opened?". A generic prompt will only produce a generic observation
    def describe_image_bytes(
        self,
        image_bytes: bytes,
        system_prompt: str | None = None,
        user_prompt: str | None = "Describe this image in detail.",
        log_response: bool = True,
    ) -> str:
        try:
            if log_response:
                logger.info(f"[LLM SEND] system={system_prompt} | user={user_prompt}")
            
            if self.provider == "openai":
                response = self._openai_describe_bytes(image_bytes, system_prompt, user_prompt)
            elif self.provider == "remote":
                response = self._ollama_describe_bytes(image_bytes, system_prompt, user_prompt)
            elif self.provider == "gemini":
                response = self._gemini_describe_bytes(image_bytes, system_prompt, user_prompt)
            elif self.provider == "byteplus":
                response = self._byteplus_describe_bytes(image_bytes, system_prompt, user_prompt)
            elif self.provider == "anthropic":
                response = self._anthropic_describe_bytes(image_bytes, system_prompt, user_prompt)
            else:
                raise RuntimeError(f"Unknown provider {self.provider!r}")
            
            cleaned = re.sub(self._CODE_BLOCK_RE, "", response.get("content", "").strip())
            
            STATE.set_agent_property("token_count", STATE.get_agent_property("token_count", 0) + response.get("tokens_used", 0))
            
            if log_response:
                logger.info(f"[LLM RECV] {cleaned}")
            return cleaned
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            return ""

    async def generate_response_async(
        self,
        image_bytes,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        debug: bool = False,
        log_response: bool = True,
    ) -> str:
        """Async wrapper that defers the blocking call to a worker thread."""
        if debug:
            # Save image to file
            debug_dir = "debug_images"
            file_name = f"{debug_dir}/image_{time.time()}.png"
            os.makedirs(debug_dir, exist_ok=True)
            with open(file_name, "wb") as f:
                f.write(image_bytes)
            logger.info(f"[DEBUG] Image saved to {file_name}")

        return await asyncio.to_thread(
            self.describe_image_bytes,
            image_bytes,
            system_prompt,
            user_prompt,
            log_response,
        )


    # ───────────────────── Provider helpers ─────────────────────
    def _openai_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> Dict[str, Any]:
        """OpenAI vision request with automatic prompt caching metrics.

        OpenAI's prompt caching is automatic for prompts ≥1024 tokens.
        Returns cached_tokens in usage.prompt_tokens_details.cached_tokens.
        """
        img_b64 = base64.b64encode(image_bytes).decode()
        messages: list[Dict[str, Any]] = []
        if sys:
            messages.append({"role": "system", "content": sys})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": usr},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}} ,
                ],
            }
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=2048,
        )
        content = response.choices[0].message.content.strip()
        token_count_input = response.usage.prompt_tokens
        token_count_output = response.usage.completion_tokens
        total_tokens = token_count_input + token_count_output

        # Extract cached tokens from prompt_tokens_details (OpenAI automatic caching)
        cached_tokens = 0
        prompt_tokens_details = getattr(response.usage, "prompt_tokens_details", None)
        if prompt_tokens_details:
            cached_tokens = getattr(prompt_tokens_details, "cached_tokens", 0) or 0

        # Record cache metrics
        config = get_cache_config()
        metrics = get_cache_metrics()
        if cached_tokens > 0:
            logger.info(f"[CACHE] OpenAI VLM cache hit: {cached_tokens}/{token_count_input} tokens from cache")
            metrics.record_hit("openai", "automatic_vlm", cached_tokens=cached_tokens, total_tokens=token_count_input)
        elif sys and len(sys) >= config.min_cache_tokens:
            metrics.record_miss("openai", "automatic_vlm", total_tokens=token_count_input)

        return {
            "tokens_used": total_tokens or 0,
            "content": content or "",
            "cached_tokens": cached_tokens,
        }
    
    def _ollama_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> str:
        img_b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": self.model,
            "prompt": usr,
            "system": sys,
            "images": [img_b64],
            "stream": False,
            "temperature": self.temperature,
        }
        url: str = f"{self.remote_url.rstrip('/')}/vision"
        r = requests.post(url, json=payload, timeout=600)
        r.raise_for_status()
        content = r.json().get("response", "").strip()
        total_tokens = r.json().get("usage", {}).get("total_tokens", 0)
        
        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
        }
    
    def _gemini_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> Dict[str, Any]:
        """Gemini vision request with implicit caching metrics.

        Gemini's implicit caching is automatic (since May 2025).
        Returns cachedContentTokenCount in usageMetadata when cache is used.
        """
        if not self._gemini_client:
            raise RuntimeError("Gemini client was not initialised.")

        result = self._gemini_client.generate_multimodal(
            self.model,
            text=usr,
            image_bytes=image_bytes,
            system_prompt=sys,
            temperature=self.temperature,
        )

        # Record cache metrics
        cached_tokens = result.get("cached_tokens", 0)
        token_count_input = result.get("prompt_tokens", 0)
        config = get_cache_config()
        metrics = get_cache_metrics()

        if cached_tokens > 0:
            logger.info(f"[CACHE] Gemini VLM implicit cache hit: {cached_tokens}/{token_count_input} tokens from cache")
            metrics.record_hit("gemini", "implicit_vlm", cached_tokens=cached_tokens, total_tokens=token_count_input)
        elif sys and len(sys) >= config.min_cache_tokens:
            metrics.record_miss("gemini", "implicit_vlm", total_tokens=token_count_input)

        return result

    def _byteplus_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> str:
        img_b64 = base64.b64encode(image_bytes).decode()
        messages: list[Dict[str, Any]] = []
        if sys:
            messages.append({"role": "system", "content": sys})

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": usr},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        )

        url = f"{self.byteplus_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},  # Enforce JSON output
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        result = response.json()

        choices = result.get("choices", [])
        if choices:
            content = (
                choices[0].get("message", {}).get("content")
                or choices[0].get("delta", {}).get("content", "")
                or ""
            ).strip()
            total_tokens = result.get("usage", {}).get("total_tokens", 0)

            return {
                "tokens_used": total_tokens or 0,
                "content": content or ""
            }

        return ""

    def _anthropic_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> Dict[str, Any]:
        """Anthropic vision request with ephemeral caching metrics.

        Anthropic's prompt caching uses cache_control markers on system prompt.
        Cache hits are reported in cache_read_input_tokens.
        """
        if not self._anthropic_client:
            raise RuntimeError("Anthropic client was not initialised.")

        img_b64 = base64.b64encode(image_bytes).decode()
        config = get_cache_config()

        # Detect media type from image bytes (default to jpeg)
        media_type = "image/jpeg"
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        elif image_bytes[:4] == b'GIF8':
            media_type = "image/gif"
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            media_type = "image/webp"

        # Build message content with image
        message_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img_b64,
                },
            },
            {
                "type": "text",
                "text": usr,
            },
        ]

        message_kwargs = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": message_content}],
        }

        if sys:
            # Use caching if system prompt is long enough
            if len(sys) >= config.min_cache_tokens:
                # Format system as list of content blocks with cache_control
                message_kwargs["system"] = [
                    {
                        "type": "text",
                        "text": sys,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                message_kwargs["system"] = sys

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

        # Cache metrics from Anthropic response
        cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cached_tokens = cache_creation + cache_read

        # Record cache metrics
        metrics = get_cache_metrics()
        if cache_read > 0:
            logger.info(f"[CACHE] Anthropic VLM cache hit: {cache_read}/{token_count_input} tokens from cache")
            metrics.record_hit("anthropic", "ephemeral_vlm", cached_tokens=cache_read, total_tokens=token_count_input)
        elif cache_creation > 0:
            logger.info(f"[CACHE] Anthropic VLM cache created: {cache_creation} tokens cached")
            metrics.record_miss("anthropic", "ephemeral_vlm", total_tokens=token_count_input)
        elif sys and len(sys) >= config.min_cache_tokens:
            metrics.record_miss("anthropic", "ephemeral_vlm", total_tokens=token_count_input)

        return {
            "tokens_used": total_tokens or 0,
            "content": content or "",
            "cached_tokens": cached_tokens,
        }

