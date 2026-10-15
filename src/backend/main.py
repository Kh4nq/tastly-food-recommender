# App factory. Dependencies are passed in, so tests and production wire different parts
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from backend.api.deps import Services
from backend.settings import Settings, load_environment
from backend.api.routes_auth import router as auth_router
from backend.api.routes_health import router as health_router
from backend.api.routes_search import router as search_router
from backend.api.routes_session import router as session_router
from backend.api.routes_recommendations import router as recommendations_router
from backend.api.errors import register_error_handlers, unexpected_error_response

def _production_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from backend.wiring import build_services  # heavy imports stay out of tests

        # Loads datasets and models: keep it off the event loop
        built = await run_in_threadpool(build_services, settings)
        app.state.services = built.services
        try:
            yield
        finally:
            built.close()

    return lifespan


def create_app(services: Services | None = None, settings: Settings | None = None) -> FastAPI:
    """Pass services for tests. Without them the app builds the real ones at startup."""
    settings = settings or Settings()
    app = FastAPI(title="Tastly API", lifespan=None if services else _production_lifespan(settings))
    app.state.settings = settings
    if services:
        app.state.services = services

    @app.middleware("http")
    async def request_id_and_last_resort(request: Request, call_next):
        request.state.request_id = uuid4().hex
        try:
            response = await call_next(request)
        except Exception as exc:
            # Answered here, inside the CORS layer, so browsers can read the 500
            response = unexpected_error_response(request, exc)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_error_handlers(app)
    app.include_router(search_router)
    app.include_router(health_router)
    app.include_router(session_router)
    app.include_router(auth_router)
    app.include_router(recommendations_router)
    # Added last, so it is the outermost layer and also decorates error responses
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,  # the session cookie travels cross-origin
        allow_methods=["GET", "PUT", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    return app


def create_production_app() -> FastAPI:
    """uvicorn entry point: uvicorn backend.main:create_production_app --factory"""
    load_environment()
    return create_app(settings=Settings.from_env())
