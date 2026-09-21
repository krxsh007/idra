from __future__ import annotations

import asyncio
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.core.config import settings
from app.llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)


class GeminiLLMClient(LLMClient):
    """Google Gemini GenAI SDK Client implementation supporting structured schemas."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.timeout_s = timeout_s or settings.LLM_TIMEOUT_S
        self._client = genai.Client(api_key=self.api_key)

    async def structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        async def _call() -> T:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            if not response.text:
                raise ValueError("Gemini returned empty response text for structured call.")
            return response_schema.model_validate_json(response.text)

        return await asyncio.wait_for(_call(), timeout=self.timeout_s)

    async def short_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.2,
    ) -> str:
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        async def _call() -> str:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        return await asyncio.wait_for(_call(), timeout=self.timeout_s)
