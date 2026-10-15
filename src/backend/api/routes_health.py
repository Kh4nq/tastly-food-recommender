# Liveness and readiness probes for load balancers and humans
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.api.deps import Services, ServicesDep

log = logging.getLogger(__name__)
router = APIRouter()


def _failed_checks(services: Services) -> list[str]:
    failed = []
    for name, check in services.health_checks.items():
        try:
            check()
        except Exception:
            log.warning("readiness check failed: %s", name, exc_info=True)
            failed.append(name)
    return failed


@router.get("/health")
def health() -> dict[str, str]:
    # Alive means the process answers. It says nothing about dependencies
    return {"status": "ok"}


@router.get("/ready")
async def ready(services: ServicesDep):
    failed = await run_in_threadpool(_failed_checks, services)
    if failed:
        return JSONResponse(status_code=503, content={"status": "not_ready", "failed": failed})
    return {"status": "ready"}