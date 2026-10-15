# Controller
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from backend.api.deps import ServicesDep, SessionId

router = APIRouter(prefix = "/api")

@router.delete("/session" , status_code = 204)
async def reset_session(session_id : SessionId, services : ServicesDep) -> None:
    await run_in_threadpool(services.search_service.reset , session_id)