from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM interactions across Gemini, Ollama, and Fake backends."""

    async def structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """Generate structured output adhering to the provided Pydantic model schema."""
        ...

    async def short_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.2,
    ) -> str:
        """Generate short unconstrained text response."""
        ...


def get_llm_client(backend: str | None = None) -> LLMClient:
    """Factory to retrieve configured LLMClient instance."""
    backend_choice = (backend or settings.LLM_BACKEND).lower()

    if backend_choice == "fake":
        from app.llm.fake import FakeLLMClient

        return FakeLLMClient()
    elif backend_choice == "gemini":
        from app.llm.gemini import GeminiLLMClient

        return GeminiLLMClient()
    elif backend_choice == "ollama":
        from app.llm.ollama import OllamaLLMClient

        return OllamaLLMClient()
    else:
        raise ValueError(
            f"Unsupported LLM backend: '{backend_choice}'. Must be 'fake', 'gemini', or 'ollama'."
        )
