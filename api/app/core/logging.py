from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

# Context variables for tracing requests and multi-agent runs
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
run_id_ctx: ContextVar[str] = ContextVar("run_id", default="")
agent_ctx: ContextVar[str] = ContextVar("agent", default="")


def add_context_vars(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    req_id = request_id_ctx.get()
    if req_id:
        event_dict["request_id"] = req_id

    run_id = run_id_ctx.get()
    if run_id:
        event_dict["run_id"] = run_id

    agent = agent_ctx.get()
    if agent:
        event_dict["agent"] = agent

    return event_dict


def filter_secrets(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    sensitive_keys = {"password", "secret", "token", "key", "authorization", "jwt"}
    for k in list(event_dict.keys()):
        if any(secret in k.lower() for secret in sensitive_keys):
            event_dict[k] = "[REDACTED]"
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    level: int = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_context_vars,
            filter_secrets,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()
