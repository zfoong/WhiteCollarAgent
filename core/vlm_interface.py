# -*- coding: utf-8 -*-
"""
Created on Fri Aug  1 14:17:29 2025

@author: zfoong
"""

from __future__ import annotations
import asyncio
import base64, os, requests
from io import BytesIO
from typing import Any, Dict, Optional, List

import json, re
from PIL import Image
import pytesseract
from openai import OpenAI

from core.models.factory import ModelFactory
from core.models.types import InterfaceType
from core.google_gemini_client import GeminiClient
from core.logger import logger

class VLMInterface:
    _CODE_BLOCK_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
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
        user_prompt: str | None = "Describe this image in detail."
    ) -> str:
        
        logger.info(f"[LLM SEND] system={system_prompt} | user={user_prompt}")
        
        if self.provider == "openai":
            response = self._openai_describe_bytes(image_bytes, system_prompt, user_prompt)
        if self.provider == "remote":
            response = self._ollama_describe_bytes(image_bytes, system_prompt, user_prompt)
        if self.provider == "gemini":
            response = self._gemini_describe_bytes(image_bytes, system_prompt, user_prompt)
        if self.provider == "byteplus":
            response = self._byteplus_describe_bytes(image_bytes, system_prompt, user_prompt)
        
        # TODO return response as content + token info, then clean up using:
        # cleaned = re.sub(self._CODE_BLOCK_RE, "", response.get("content", "").strip())
        
        logger.info(f"[LLM RECV] {response}")
        return response

    async def generate_response_async(
        self,
        image_bytes,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> str:
        """Async wrapper that defers the blocking call to a worker thread."""
        return await asyncio.to_thread(
            self.describe_image_bytes,
            image_bytes,
            system_prompt,
            user_prompt,
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
        return response.choices[0].message.content.strip()
    
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
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    
    def _gemini_describe_bytes(self, image_bytes: bytes, sys: str | None, usr: str) -> str:
        if not self._gemini_client:
            raise RuntimeError("Gemini client was not initialised.")

        return self._gemini_client.generate_multimodal(
            self.model,
            text=usr,
            image_bytes=image_bytes,
            system_prompt=sys,
            temperature=self.temperature,
        )

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
            return content

        return ""

