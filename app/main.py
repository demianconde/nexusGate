"""Ponto de entrada da API do NexusGate (FastAPI app factory)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import admin, health, proxy
from app.config import get_settings
from app.logging_config import configure_logging, get_logger

PUBLIC_DIR = Path(__file__).parent / "public"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    log = get_logger("nexusgate")
    log.info("startup", version=__version__, env=settings.env)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NexusGate",
        version=__version__,
        description="LLM Gateway & Multi-Agent Proxy BYOK",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Injeta um request_id no contexto de log de cada requisição."""
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(proxy.router)

    @app.get("/", include_in_schema=False)
    async def landing() -> FileResponse:
        return FileResponse(PUBLIC_DIR / "landing.html")

    # Assets estáticos futuros (css/js/imagens) em app/public/.
    app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static")

    return app


app = create_app()
