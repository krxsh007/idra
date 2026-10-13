import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import Point

from app.core.config import settings
from app.core.errors import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.logging import logger, request_id_ctx, setup_logging
from app.routers.agents import router as agents_router
from app.routers.assistant import router as assistant_router
from app.routers.auth import router as auth_router
from app.routers.events import router as events_router
from app.routers.facilities import router as facilities_router
from app.routers.hazards import router as hazards_router
from app.routers.health import router as health_router
from app.routers.metrics import router as metrics_router
from app.routers.recommendations import router as recommendations_router
from app.routers.reports import router as reports_router
from app.routers.runs import router as runs_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(settings.LOG_LEVEL)
    logger.info(
        "idra_startup",
        app_env=settings.APP_ENV,
        llm_backend=settings.LLM_BACKEND,
        study_area_bbox=settings.STUDY_AREA_BBOX,
    )
    # Load road graph and validate manifest
    from app.gis.graph import road_graph_manager

    road_graph_manager.load_graph()
    # Build the street-geometry index used to match roads against hazard polygons.
    await asyncio.to_thread(road_graph_manager.edges_intersecting, Point(80.2, 13.0))
    await asyncio.to_thread(road_graph_manager.node_arrays)

    # Load the embedding model up front: a cold load can exceed the citizen agent's timeout.
    from app.rag.embeddings import EmbeddingService

    await asyncio.to_thread(EmbeddingService.get_instance().embed_text, "warmup")
    yield
    logger.info("idra_shutdown")


app = FastAPI(
    title="Intelligent Disaster Response Agents (IDRA)",
    description=(
        "Multi-agent emergency decision support platform "
        "grounded in RAG and PostGIS spatial intelligence."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx.set(req_id)
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        process_time_ms = int((time.perf_counter() - start_time) * 1000)
        response.headers["X-Request-ID"] = req_id
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=process_time_ms,
        )
        return response
    except Exception as exc:
        process_time_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(
            "http_request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=process_time_ms,
            error=str(exc),
        )
        raise
    finally:
        request_id_ctx.reset(token)


# Mount routers
app.include_router(health_router, prefix="")
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(hazards_router, prefix="/api/v1")
app.include_router(facilities_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")
app.include_router(recommendations_router, prefix="/api/v1")
app.include_router(runs_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
