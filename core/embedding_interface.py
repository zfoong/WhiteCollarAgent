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
        model: str = "text-embedding-004",
        ollama_url: str = "http://localhost:11434/api/embeddings",
    ):
        """
        :param provider: "openai", "gemini", or "remote"
        :param model: Embedding model name for the chosen provider.
                      - OpenAI: e.g. "text-embedding-3-small" / "text-embedding-3-large"
                      - Gemini: e.g. "text-embedding-004" (or "models/text-embedding-004")
                      - Remote: e.g. "nomic-embed-text" in Ollama
        :param ollama_url: Base URL for Ollama embeddings endpoint.
        """
        self.provider = provider.lower()
        self.model = model
        self.ollama_url = ollama_url
        self._gemini_client: GeminiClient | None = None

        if self.provider == "openai":
            if OpenAI is None:
                raise ImportError("openai package not installed. Run `pip install openai`.")
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise EnvironmentError("OPENAI_API_KEY is not set.")
            self.client = OpenAI(api_key=api_key)

        elif self.provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise EnvironmentError("GOOGLE_API_KEY is not set.")
            self._gemini_client = GeminiClient(api_key)
            # Normalize model name to include 'models/' prefix if omitted
            self.model = self._normalize_gemini_model(self.model or "text-embedding-004")

        elif self.provider == "remote":
            # Nothing else to set up.
            pass
        else:
            raise ValueError("Unsupported provider. Use 'openai', 'gemini', or 'remote'.")

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
