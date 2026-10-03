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
    components: dict[str, ComponentStatus] = {}
    overall_ok = True

    db_ok = bool(settings.DATABASE_URL)
    if not db_ok:
        overall_ok = False
    components["database"] = ComponentStatus(
        status="ok" if db_ok else "unavailable",
        details={"url_configured": db_ok},
    )

    from app.gis.graph import road_graph_manager

    if not road_graph_manager.is_loaded and not road_graph_manager._unavailable:
        try:
            road_graph_manager.load_graph()
        except Exception:
            pass

    graph_loaded = road_graph_manager.is_loaded
    if road_graph_manager._unavailable or not graph_loaded:
        overall_ok = False
        rg_status = "unavailable"
    else:
        rg_status = "ok"

    components["road_graph"] = ComponentStatus(
        status=rg_status,
        details={
            "path": settings.ROAD_GRAPH_PATH,
            "loaded": graph_loaded,
            "nodes": road_graph_manager.node_count,
            "edges": road_graph_manager.edge_count,
            "manifest_bbox": road_graph_manager.manifest.get("bbox", []),
        },
    )

    llm_model = settings.GEMINI_MODEL if settings.LLM_BACKEND == "gemini" else settings.OLLAMA_MODEL
    components["llm"] = ComponentStatus(
        status="ok",
        details={"backend": settings.LLM_BACKEND, "model": llm_model},
    )

    components["weather"] = ComponentStatus(
        status="ok" if settings.WEATHER_ENABLED else "disabled",
        details={"enabled": settings.WEATHER_ENABLED},
    )

    return DeepHealthResponse(
        status="ok" if overall_ok else "degraded",
        environment=settings.APP_ENV,
        components=components,
    )
