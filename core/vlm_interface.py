# -*- coding: utf-8 -*-
"""
Created on Fri Aug  1 14:17:29 2025

@author: zfoong
"""

from __future__ import annotations
import base64, os, requests
from io import BytesIO
from typing import Any, Dict, Optional, List
from core.prompt import UI_ELEMS_SYS_PROMPT, UI_ELEMS_USER_PROMPT

import json, re
from PIL import Image
import pytesseract
from openai import OpenAI

from core.models.factory import ModelFactory
from core.models.types import InterfaceType
from core.google_gemini_client import GeminiClient
from core.logger import logger

class VLMInterface:
    _CODE_BLOCK_RE = None     # not needed for vision

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
        *,
        system_prompt: str | None = None,
        user_prompt: str | None = "Describe this image in detail."
    ) -> str:
        if self.provider == "openai":
            return self._openai_describe_bytes(image_bytes, system_prompt, user_prompt)
        if self.provider == "remote":
            return self._ollama_describe_bytes(image_bytes, system_prompt, user_prompt)
        if self.provider == "gemini":
            return self._gemini_describe_bytes(image_bytes, system_prompt, user_prompt)
        if self.provider == "byteplus":
            return self._byteplus_describe_bytes(image_bytes, system_prompt, user_prompt)
        raise RuntimeError(f"Unsupported provider {self.provider!r}")

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

    def _safe_json(self, text: str) -> Dict[str, Any]:
        """Extract and parse the first JSON object from the model response."""
        try:
            m = re.search(r'\{[\s\S]*\}', text)
            if not m:
                return {}
            return json.loads(m.group(0))
        except Exception:
            return {}

    def _format_elements_readable(
        self,
        screen_size: Dict[str, int],
        elems: List[Dict[str, Any]]
    ) -> str:
        lines = []
        lines.append(f"# UI Elements ({len(elems)})")
        for i, e in enumerate(elems, 1):
            b = e.get("bbox", {}) or {}
            x, y, w, h = int(b.get("x", 0)), int(b.get("y", 0)), int(b.get("w", 0)), int(b.get("h", 0))
            cx, cy = x + max(w, 0)//2, y + max(h, 0)//2
            role = e.get("role", "other")
            lbl = (e.get("label") or "").strip()
            state = e.get("state", {}) or {}
            enabled = bool(state.get("enabled", True))
            selected = bool(state.get("selected", False))
            conf = float(e.get("confidence", 0.5))
            eid = (e.get("id") or f"el-{i}")[:64]
            label_str = f"\"{lbl}\"" if lbl else "\"\""
            lines.append(
                f"{i}. [{role}] {label_str}  "
                f"bbox(x={x},y={y},w={w},h={h}) center({cx},{cy})  "
                f"state(enabled={enabled},selected={selected})  "
                f"conf={conf:.2f}  id={eid}"
            )
        return "\n".join(lines) if lines else "# UI Elements (0)"

    # --- primary simple API method: call this to get a readable string ---
    def scan_ui_bytes(
        self,
        image_bytes: bytes,
        *,
        use_ocr: bool = False,
        max_elements: int = 120
    ) -> str:
        """
        Simple UI scan from in-memory bytes → readable list of elements.
        """
        # 1) Ask the VLM for a flat element list
        raw = self.describe_image_bytes(
            image_bytes,
            system_prompt=UI_ELEMS_SYS_PROMPT,
            user_prompt=UI_ELEMS_USER_PROMPT,
        )
        parsed = self._safe_json(raw)
        screen = parsed.get("screen_size", {}) if isinstance(parsed, dict) else {}
        elems = parsed.get("elements", []) if isinstance(parsed, dict) else []
        elems = elems if isinstance(elems, list) else []
    
        # 2) Basic cleanup + center computation; clamp + truncate
        cleaned: List[Dict[str, Any]] = []
        for idx, e in enumerate(elems[:max_elements]):
            try:
                b = e.get("bbox", {}) or {}
                x, y, w, h = int(b.get("x", 0)), int(b.get("y", 0)), int(b.get("w", 0)), int(b.get("h", 0))
                cx, cy = x + max(w, 0)//2, y + max(h, 0)//2
                cleaned.append({
                    "id": (str(e.get("id") or f"el-{idx}"))[:64],
                    "role": str(e.get("role") or "other"),
                    "label": (str(e.get("label") or "").strip())[:256],
                    "bbox": {"x": x, "y": y, "w": w, "h": h},
                    "center": {"cx": cx, "cy": cy},
                    "state": {
                        "enabled": bool((e.get("state") or {}).get("enabled", True)),
                        "selected": bool((e.get("state") or {}).get("selected", False)),
                    },
                    "confidence": float(e.get("confidence", 0.5)),
                })
            except Exception:
                continue
    
        # 3) Optional OCR backfill for labels (OFF by default)
        if use_ocr and pytesseract is not None and Image is not None:
            try:
                img = Image.open(BytesIO(image_bytes)).convert("RGB")
                ocr = pytesseract.image_to_data(img, output_type='dict')
                owords = []
                for i in range(len(ocr.get("text", []))):
                    t = (ocr["text"][i] or "").strip()
                    if not t:
                        continue
                    owords.append({
                        "text": t,
                        "bbox": {
                            "x": int(ocr["left"][i]),
                            "y": int(ocr["top"][i]),
                            "w": int(ocr["width"][i]),
                            "h": int(ocr["height"][i]),
                        }
                    })
                def contains(a, b):
                    return (b["x"] >= a["x"] and b["y"] >= a["y"] and
                            (b["x"]+b["w"]) <= (a["x"]+a["w"]) and (b["y"]+b["h"]) <= (a["y"]+a["h"]))
                for el in cleaned:
                    if el["label"]:
                        continue
                    eb = el["bbox"]
                    hits = [w["text"] for w in owords if contains(eb, w["bbox"])]
                    if hits:
                        el["label"] = " ".join(hits)[:256]
            except Exception:
                pass
    
        # 4) Format and return
        return self._format_elements_readable(screen, cleaned)
