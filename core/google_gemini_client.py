"""Utility client for interacting with the Google Generative Language REST API.

This small helper wraps the HTTP endpoints used by Gemini so that we can
interact with the service without pulling in the ``google-generativeai``
package.  Using the REST interface keeps stderr free from the gRPC warnings the
SDK emits during import/initialisation (e.g. the ``ALTS creds ignored`` message
that was polluting the CLI output).
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, Iterable, List, Optional

import requests

DEFAULT_API_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_API_VERSION = "v1beta"


class GeminiAPIError(RuntimeError):
    """Raised when the Gemini service reports an error or blocks a prompt."""


def _normalise_model_name(model: str) -> str:
    """Ensure model identifiers include the ``models/`` prefix."""
    model = model.strip()
    return model if model.startswith("models/") else f"models/{model}"


class GeminiClient:
    """Lightweight REST client for Gemini models."""

    def __init__(
        self,
        api_key: str,
        *,
        api_base: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout: int = 120,
    ) -> None:
        if not api_key:
            raise ValueError("`api_key` must be a non-empty string.")

        env_base = os.getenv("GOOGLE_API_BASE")
        env_version = os.getenv("GOOGLE_API_VERSION")

        self._api_key = api_key
        self._api_base = (api_base or env_base or DEFAULT_API_BASE).rstrip("/")
        self._api_version = api_version or env_version or DEFAULT_API_VERSION
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def generate_text(
        self,
        model: str,
        *,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate text for a purely textual prompt."""
        contents = [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]

        generation_config: Dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_output_tokens is not None:
            generation_config["maxOutputTokens"] = max_output_tokens

        payload: Dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }
        if generation_config:
            payload["generationConfig"] = generation_config

        response = self._post_json(
            f"{_normalise_model_name(model)}:generateContent", payload
        )
        total_tokens = response.get("usageMetadata", {}).get("totalTokenCount", 0)
        content = self._extract_text(response)

        return {
            "tokens_used": total_tokens,
            "content": content
        }

    def generate_multimodal(
        self,
        model: str,
        *,
        text: str,
        image_bytes: bytes,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate text from a prompt that also contains an inline image."""
        inline_data = {
            "mimeType": "image/png",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }

        parts: List[Dict[str, Any]] = [{"text": text}, {"inlineData": inline_data}]
        contents = [{"role": "user", "parts": parts}]

        payload: Dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }
        if temperature is not None:
            payload["generationConfig"] = {"temperature": temperature}

        response = self._post_json(
            f"{_normalise_model_name(model)}:generateContent", payload
        )
        total_tokens = response.get("usageMetadata", {}).get("totalTokenCount", 0)
        content = self._extract_text(response)
        return {
            "tokens_used": total_tokens,
            "content": content
        }

    def embed_text(self, model: str, *, text: str) -> List[float]:
        """Fetch an embedding vector for the supplied text."""
        payload = {
            "content": {
                "parts": [{"text": text}],
            }
        }
        response = self._post_json(
            f"{_normalise_model_name(model)}:embedContent", payload
        )

        embedding = response.get("embedding")
        if isinstance(embedding, dict) and "values" in embedding:
            return list(map(float, embedding.get("values", [])))
        if isinstance(embedding, list):
            return [float(x) for x in embedding]

        raise GeminiAPIError("Gemini embedContent response did not contain embeddings.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _endpoint(self, path: str) -> str:
        return f"{self._api_base}/{self._api_version}/{path.lstrip('/')}"

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            self._endpoint(path),
            params={"key": self._api_key},
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_text(response: Dict[str, Any]) -> str:
        feedback = response.get("promptFeedback")
        if isinstance(feedback, dict):
            reason = feedback.get("blockReason")
            if reason:
                raise GeminiAPIError(f"Prompt blocked by Gemini: {reason}")

        candidates: Iterable[Dict[str, Any]] = response.get("candidates", []) or []
        for candidate in candidates:
            if candidate.get("finishReason") == "SAFETY":
                # Skip candidates halted for safety reasons.
                continue
            content = candidate.get("content") or {}
            parts: Iterable[Dict[str, Any]] = content.get("parts", []) or []
            texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
            text = "".join(texts).strip()
            if text:
                return text

        return ""
