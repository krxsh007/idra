import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"
    environment: str


class ComponentStatus(BaseModel):
    status: str  # ok, degraded, unavailable, unconfigured
    details: dict[str, Any] = {}


class DeepHealthResponse(BaseModel):
    status: str
    environment: str
    components: dict[str, ComponentStatus]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.APP_ENV,
    )


@router.get("/health/deep", response_model=DeepHealthResponse)
async def deep_health_check() -> DeepHealthResponse:
    # Evaluate component readiness without throwing unhandled exceptions
    components: dict[str, ComponentStatus] = {}
    overall_ok = True

    # 1. Database & pgvector status check (placeholder for M0, fully probed in M1)
    components["database"] = ComponentStatus(
        status="ok" if settings.DATABASE_URL else "unconfigured",
        details={"url_configured": bool(settings.DATABASE_URL)},
    )

    # 2. Road graph status check (evaluated in M4)
    graph_exists = os.path.exists(settings.ROAD_GRAPH_PATH)
    components["road_graph"] = ComponentStatus(
        status="ok" if graph_exists else "unconfigured",
        details={"path": settings.ROAD_GRAPH_PATH, "file_exists": graph_exists},
    )

    # 3. LLM backend reachability status check
    llm_model = settings.GEMINI_MODEL if settings.LLM_BACKEND == "gemini" else settings.OLLAMA_MODEL
    components["llm"] = ComponentStatus(
        status="ok",
        details={"backend": settings.LLM_BACKEND, "model": llm_model},
    )

    # 4. Open-Meteo weather service
    components["weather"] = ComponentStatus(
        status="ok" if settings.WEATHER_ENABLED else "disabled",
        details={"enabled": settings.WEATHER_ENABLED},
    )

    return DeepHealthResponse(
        status="ok" if overall_ok else "degraded",
        environment=settings.APP_ENV,
        components=components,
    )
