from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from app.llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)


class FakeLLMClient(LLMClient):
    """Deterministic Fake LLM Client for unit testing and offline development."""

    def __init__(
        self,
        fixture_responses: list[Any] | None = None,
        default_short_text: str = "Fake LLM summary text response.",
        error_to_raise: Exception | None = None,
    ) -> None:
        self.fixture_responses = list(fixture_responses or [])
        self.default_short_text = default_short_text
        self.error_to_raise = error_to_raise
        self.call_count: int = 0
        self.recorded_prompts: list[str] = []
        self.recorded_schemas: list[type[BaseModel]] = []

    async def structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        self.call_count += 1
        self.recorded_prompts.append(prompt)
        self.recorded_schemas.append(response_schema)

        if self.error_to_raise is not None:
            raise self.error_to_raise

        if self.fixture_responses:
            next_fixture = self.fixture_responses.pop(0)
            if isinstance(next_fixture, Exception):
                raise next_fixture
            if isinstance(next_fixture, response_schema):
                return next_fixture
            if isinstance(next_fixture, dict):
                return response_schema.model_validate(next_fixture)
            if isinstance(next_fixture, str):
                return response_schema.model_validate_json(next_fixture)
            msg = f"Cannot cast fixture of type {type(next_fixture)} to {response_schema}"
            raise TypeError(msg)

        # Attempt to construct default instance if no fixture is registered
        try:
            return response_schema.model_validate({})
        except Exception as e:
            raise ValueError(
                f"FakeLLMClient received no fixture response for {response_schema.__name__} "
                f"and model could not be instantiated with defaults: {e}"
            ) from e

    async def short_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.2,
    ) -> str:
        self.call_count += 1
        self.recorded_prompts.append(prompt)

        if self.error_to_raise is not None:
            raise self.error_to_raise

        if self.fixture_responses:
            next_fixture = self.fixture_responses.pop(0)
            if isinstance(next_fixture, Exception):
                raise next_fixture
            if isinstance(next_fixture, str):
                return next_fixture
            if isinstance(next_fixture, dict):
                return json.dumps(next_fixture)

        return self.default_short_text
