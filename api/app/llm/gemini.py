from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import logger
from app.llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

# Provider-side conditions that usually clear on retry (rate limit, overload, gateway timeout).
TRANSIENT_STATUS_CODES = {429, 500, 503, 504}


class GeminiLLMClient(LLMClient):
    """Google Gemini GenAI SDK Client implementation supporting structured schemas."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_s: int | None = None,
        fallback_model_name: str | None = None,
        max_retries: int | None = None,
        retry_backoff_s: float = 1.0,
        attempt_timeout_s: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.fallback_model_name = (
            fallback_model_name
            if fallback_model_name is not None
            else settings.GEMINI_FALLBACK_MODEL
        )
        self.timeout_s = timeout_s or settings.LLM_TIMEOUT_S
        self.max_retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
        self.retry_backoff_s = retry_backoff_s
        self.attempt_timeout_s = attempt_timeout_s or settings.LLM_ATTEMPT_TIMEOUT_S
        self._client = genai.Client(api_key=self.api_key)

    @property
    def model_chain(self) -> list[str]:
        """Primary model followed by the comma-separated fallback models, in order."""
        fallbacks = [m.strip() for m in (self.fallback_model_name or "").split(",") if m.strip()]
        return [self.model_name, *[m for m in fallbacks if m != self.model_name]]

    async def _generate(self, call: Callable[[str], Awaitable[R]]) -> R:
        """Run `call(model)` within the timeout, moving down the model chain on provider errors.

        Free-tier models are overloaded (503) or out of daily quota (429) independently of each
        other, and both errors come back within a second or two, so trying the next model is far
        more useful than waiting. Each attempt is also capped so a hung request moves on instead
        of consuming the whole budget.
        """
        chain = self.model_chain
        attempts = max(self.max_retries + 1, len(chain))

        async def _attempts() -> R:
            for attempt in range(attempts):
                model = chain[min(attempt, len(chain) - 1)]
                is_last = attempt == attempts - 1
                try:
                    return await asyncio.wait_for(call(model), timeout=self.attempt_timeout_s)
                except errors.APIError as e:
                    if e.code not in TRANSIENT_STATUS_CODES or is_last:
                        raise
                    logger.warning(
                        "gemini_transient_error_retrying",
                        model=model,
                        status=e.code,
                        attempt=attempt + 1,
                    )
                except TimeoutError:
                    if is_last:
                        raise
                    logger.warning(
                        "gemini_attempt_timed_out_retrying",
                        model=model,
                        timeout_s=self.attempt_timeout_s,
                        attempt=attempt + 1,
                    )
                # Back off only when retrying the same model; a different model is a fresh pool.
                next_model = chain[min(attempt + 1, len(chain) - 1)]
                if next_model == model:
                    await asyncio.sleep(self.retry_backoff_s * (attempt + 1))
            raise AssertionError("unreachable")

        return await asyncio.wait_for(_attempts(), timeout=self.timeout_s)

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

        async def _call(model: str) -> T:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=model,
                contents=prompt,
                config=config,
            )
            if not response.text:
                raise ValueError("Gemini returned empty response text for structured call.")
            return response_schema.model_validate_json(response.text)

        return await self._generate(_call)

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

        async def _call(model: str) -> str:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=model,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        return await self._generate(_call)
