from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)


class OllamaLLMClient(LLMClient):
    """Local Ollama HTTP client supporting structured JSON schemas and text generation."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.OLLAMA_MODEL
        self.timeout_s = timeout_s or settings.LLM_TIMEOUT_S

    async def structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        schema_json = response_schema.model_json_schema()
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_instruction or "",
            "stream": False,
            "format": schema_json,
            "options": {
                "temperature": temperature,
            },
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_s)) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_text = str(data.get("response", ""))
            if not raw_text:
                raise ValueError("Ollama returned empty response for structured call.")
            return response_schema.model_validate_json(raw_text)

    async def short_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.2,
    ) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_instruction or "",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_s)) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("response", ""))
