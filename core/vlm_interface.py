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

class VLMInterface:
    _CODE_BLOCK_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.5,
    ) -> None:
        self.provider = provider
        self.temperature = temperature
        self._gemini_client: GeminiClient | None = None

        ctx = ModelFactory.create(
            provider=provider,
            interface=InterfaceType.VLM,
            model_override=model,
        )

        self.model = ctx["model"]
        self.client = ctx["client"]
        self._gemini_client = ctx["gemini_client"]
        self.remote_url = ctx["remote_url"]

        if ctx["byteplus"]:
            self.api_key = ctx["byteplus"]["api_key"]
            self.byteplus_base_url = ctx["byteplus"]["base_url"]

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
            if self.provider == "remote":
                response = self._ollama_describe_bytes(image_bytes, system_prompt, user_prompt)
            if self.provider == "gemini":
                response = self._gemini_describe_bytes(image_bytes, system_prompt, user_prompt)
            if self.provider == "byteplus":
                response = self._byteplus_describe_bytes(image_bytes, system_prompt, user_prompt)
            
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
    def _openai_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> str:
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
        total_tokens = response.usage.prompt_tokens + response.usage.completion_tokens

        return {
            "tokens_used": total_tokens or 0,
            "content": content or ""
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
    
    def _gemini_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> str:
        if not self._gemini_client:
            raise RuntimeError("Gemini client was not initialised.")

        content = self._gemini_client.generate_multimodal(
            self.model,
            text=usr,
            image_bytes=image_bytes,
            system_prompt=sys,
            temperature=self.temperature,
        )
        return content

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

