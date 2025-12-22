import os
from openai import OpenAI

from core.models.types import InterfaceType
from core.models.model_registry import MODEL_REGISTRY
from core.models.provider_config import PROVIDER_CONFIG
from core.google_gemini_client import GeminiClient


class ModelFactory:
    @staticmethod
    def create(
        *,
        provider: str,
        interface: InterfaceType,
        model_override: str | None = None,
    ) -> dict:
        if provider not in PROVIDER_CONFIG:
            raise ValueError(f"Unsupported provider: {provider}")

        cfg = PROVIDER_CONFIG[provider]
        model = model_override or MODEL_REGISTRY[provider][interface]

        # Resolve base URL (if any)
        base_url = None
        if cfg.default_base_url:
            base_url = os.getenv(cfg.base_url_env, cfg.default_base_url)

        # Providers
        if provider == "openai":
            api_key = os.getenv(cfg.api_key_env)
            if not api_key:
                raise EnvironmentError("OPENAI_API_KEY not set")

            return {
                "provider": provider,
                "model": model,
                "client": OpenAI(api_key=api_key),
                "gemini_client": None,
                "ollama_url": None,
                "byteplus": None,
            }

        if provider == "gemini":
            api_key = os.getenv(cfg.api_key_env)
            if not api_key:
                raise EnvironmentError("GOOGLE_API_KEY not set")

            return {
                "provider": provider,
                "model": model,
                "client": None,
                "gemini_client": GeminiClient(api_key),
                "ollama_url": None,
                "byteplus": None,
            }

        if provider == "byteplus":
            api_key = os.getenv(cfg.api_key_env)
            if not api_key:
                raise EnvironmentError("BYTEPLUS_API_KEY not set")

            return {
                "provider": provider,
                "model": model,
                "client": None,
                "gemini_client": None,
                "ollama_url": None,
                "byteplus": {
                    "api_key": api_key,
                    "base_url": base_url,
                },
            }

        if provider == "remote":
            return {
                "provider": provider,
                "model": model,
                "client": None,
                "gemini_client": None,
                "ollama_url": f"{base_url.rstrip('/')}/api/generate",
                "byteplus": None,
            }

        raise RuntimeError("Unreachable")
