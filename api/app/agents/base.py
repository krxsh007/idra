from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AgentName, AgentStatus
from app.llm.client import LLMClient

logger = structlog.get_logger(__name__)

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentFailure(BaseModel):
    """Structured error descriptor returned when an agent cannot complete its task."""

    status: AgentStatus = AgentStatus.FAILED
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: dict[str, Any] = Field(default_factory=dict)


class RunContext(BaseModel):
    """Execution context passed into an agent run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    event_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    agent_name: AgentName
    db: AsyncSession | None = None
    llm: LLMClient
    timeout_s: float = 30.0
    max_repair_retries: int = 1

    @property
    def llm_budget_s(self) -> float:
        """Share of the agent timeout an optional LLM step may use, leaving time to fall back."""
        return self.timeout_s * 0.75


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """Abstract Base Class for IDRA intelligent agents with timeout and repair handling."""

    def __init__(self, agent_name: AgentName, response_schema: type[OutputT]) -> None:
        self.agent_name = agent_name
        self.response_schema = response_schema

    @abstractmethod
    async def _execute(self, ctx: RunContext, input_data: InputT) -> OutputT | AgentFailure:
        """Core execution logic implemented by subclasses."""
        ...

    async def run(self, ctx: RunContext, input_data: InputT) -> OutputT | AgentFailure:
        """Run agent wrapped in timeout protection and error isolation."""
        log = logger.bind(
            agent=self.agent_name.value,
            event_id=str(ctx.event_id) if ctx.event_id else None,
        )
        log.info("agent_run_started")

        try:
            result = await asyncio.wait_for(
                self._execute(ctx, input_data),
                timeout=ctx.timeout_s,
            )
            if isinstance(result, AgentFailure):
                log.warning("agent_run_returned_failure", code=result.code, message=result.message)
            else:
                log.info("agent_run_succeeded")
            return result
        except TimeoutError:
            log.error("agent_run_timed_out", timeout_s=ctx.timeout_s)
            return AgentFailure(
                status=AgentStatus.TIMEOUT,
                code="AGENT_TIMEOUT",
                message=f"Agent '{self.agent_name.value}' timed out after {ctx.timeout_s}s.",
                details={"timeout_s": ctx.timeout_s},
            )
        except Exception as e:
            log.exception("agent_run_unhandled_exception", error=str(e))
            err_str = str(e)
            if "LLM_UNAVAILABLE" in err_str or isinstance(e, ConnectionError):
                code = "LLM_UNAVAILABLE"
            elif "ValidationError" in type(e).__name__ or "validation" in err_str.lower():
                code = "LLM_INVALID_OUTPUT"
            else:
                code = "AGENT_UNHANDLED_EXCEPTION"
            return AgentFailure(
                status=AgentStatus.FAILED,
                code=code,
                message=f"Agent '{self.agent_name.value}' failed ({code}): {e}",
                details={"exception_type": type(e).__name__},
            )

    async def call_llm_with_repair(
        self,
        ctx: RunContext,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> OutputT:
        """Execute structured LLM call with a single automatic repair retry if parsing fails."""
        try:
            return await ctx.llm.structured(
                prompt=prompt,
                response_schema=self.response_schema,
                system_instruction=system_instruction,
                temperature=temperature,
            )
        except Exception as first_err:
            if (
                ctx.max_repair_retries < 1
                or "LLM_UNAVAILABLE" in str(first_err)
                or isinstance(first_err, ConnectionError)
            ):
                raise

            repair_prompt = (
                f"{prompt}\n\n"
                f"[REPAIR REQUIRED]: Your previous output failed schema validation with error:\n"
                f"{first_err}\n"
                f"Please fix all schema errors and return strictly valid JSON matching the schema."
            )

            logger.warning(
                "agent_attempting_llm_repair",
                agent=self.agent_name.value,
                error=str(first_err),
            )

            return await ctx.llm.structured(
                prompt=repair_prompt,
                response_schema=self.response_schema,
                system_instruction=system_instruction,
                temperature=temperature,
            )
