# -*- coding: utf-8 -*-
"""
core.embedding_interface

Embedding interface supporting:
- OpenAI (via openai SDK)
- Google Gemini (via the public REST API)
- Remote (Ollama /api/embeddings)

Environment variables:
- OPENAI_API_KEY (for provider="openai")
- GOOGLE_API_KEY (for provider="gemini")
"""

import os
from typing import List, Optional

import requests

from core.logger import logger

# Optional imports so the module works even if some SDKs aren't installed
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from core.google_gemini_client import GeminiAPIError, GeminiClient


class EmbeddingInterface:
    """
    A class to handle interactions with embedding models:
    - OpenAI
    - Google Gemini
    - Local/remote Ollama
    """

    def __init__(
        self,
        provider: str = "gemini",
        model: str | None = None,
    ):
        self.provider = provider.lower()
        self._gemini_client: GeminiClient | None = None

        ctx = ModelFactory.create(
            provider=self.provider,
            interface=InterfaceType.EMBEDDING,
            model_override=model,
        )

        self.model = ctx["model"]
        self.client = ctx["client"]
        self._gemini_client = ctx["gemini_client"]
        self.ollama_url = ctx["remote_url"]

        if ctx["byteplus"]:
            self.api_key = ctx["byteplus"]["api_key"]
            self.byteplus_base_url = ctx["byteplus"]["base_url"]

        if self.provider == "gemini":
            self.model = self._normalize_gemini_model(self.model)

    # ─────────────────────────── Public API ───────────────────────────
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding vector for input text.

        :param text: Input text to embed
        :return: List[float] embedding vector, or None on failure
        """
        if not isinstance(text, str):
            raise TypeError("`text` must be a string.")

        if self.provider == "openai":
            return self._get_openai_embedding(text)
        elif self.provider == "gemini":
            return self._get_gemini_embedding(text)
        elif self.provider == "remote":
            return self._get_ollama_embedding(text)
        else:  # pragma: no cover
            raise RuntimeError(f"Unknown provider {self.provider!r}")

    # ───────────────────── Provider-specific helpers ───────────────────
    def _get_openai_embedding(self, text: str) -> Optional[List[float]]:
        try:
            response = self.client.embeddings.create(model=self.model, input=text)
            # OpenAI returns: response.data[0].embedding
            return response.data[0].embedding  # type: ignore[attr-defined]
        except Exception as e:
            logger.exception(f"Error calling OpenAI Embedding API: {e}")
            return None

    def _get_gemini_embedding(self, text: str) -> Optional[List[float]]:
        if not self._gemini_client:
            raise RuntimeError("Gemini client was not initialised.")

        try:
            return self._gemini_client.embed_text(self.model, text=text)
        except GeminiAPIError as e:
            logger.exception(f"Gemini rejected the embedding request: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error calling Gemini Embedding API: {e}")
            return None

    def _get_ollama_embedding(self, text: str) -> Optional[List[float]]:
        try:
            payload = {
                "model": self.model,
                "prompt": text,  # Ollama accepts "prompt" for /api/embeddings
            }
            response = requests.post(self.ollama_url, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            # Ollama returns {"embedding": [floats]}
            return result.get("embedding", None)
        except Exception as e:
            logger.exception(f"Error calling Ollama Embedding API: {e}")
            return None

    # ─────────────────────────── Utilities ───────────────────────────
    @staticmethod
    def _normalize_gemini_model(model_name: str) -> str:
        """
        Ensure Gemini embedding model names have the 'models/' prefix that the SDK expects.
        """
        model_name = model_name.strip()
        return model_name if model_name.startswith("models/") else f"models/{model_name}"
