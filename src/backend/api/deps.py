# FastAPI dependencies: shared services and the anonymous session cookie
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request, Response

from backend.gate import Gate
from backend.api.presenter import DishPresenter
from backend.limits import HashGate , RateLimiter
from backend.services.search_service import SearchService

from backend.ports import UnauthenticatedError, User
from backend.services.auth_service import AuthService

SESSION_COOKIE = "anon_id"
AUTH_COOKIE = "auth"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
_VALID_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class Services:
    search_service: SearchService
    presenter: DishPresenter
    gate: Gate = field(default_factory=Gate)
    # name -> check that raises when that dependency is unhealthy (used by /ready)
    health_checks: Mapping[str, Callable[[], None]] = field(default_factory=dict)
    auth_service: AuthService | None = None
    hash_gate : HashGate = field(default_factory = HashGate)
    auth_limiter : RateLimiter | None = None


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_session_id(request: Request, response: Response) -> str:
    current = request.cookies.get(SESSION_COOKIE)
    # The cookie is untrusted input: accept only the exact shape we issue
    if current and _VALID_ID.fullmatch(current):
        return current
    new_id = uuid4().hex
    response.set_cookie(
        SESSION_COOKIE,
        new_id,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.cookie_secure,
    )
    return new_id


SessionId = Annotated[str, Depends(get_session_id)]
ServicesDep = Annotated[Services, Depends(get_services)]

class OriginNotAllowedError(Exception):
    ...
    
async def require_allowed_origin(request : Request) -> None:
    # Browsers always send Origin on POST/PUT. No header means not a browser
    origin = request.headers.get("origin")
    if origin is not None and origin not in request.app.state.settings.cors_origins:
        raise OriginNotAllowedError
        
def client_ip(request : Request) -> str : 
    if request.app.state.settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for" , "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
        
    return request.client.host if request.client else "unknown"
    
async def limit_auth_attempts(request : Request , services : ServicesDep) -> None:
    if services.auth_limiter is not None:
        services.auth_limiter.hit(client_ip(request))
            
def get_hash_gate(services : ServicesDep) -> HashGate:
    return services.hash_gate

HashGateDep = Annotated[HashGate , Depends(get_hash_gate)]
    
    

def get_auth_service(services: ServicesDep) -> AuthService:
    if services.auth_service is None:
        # A server misconfiguration, not "the user is signed out": must not look like a 401
        raise NotImplementedError("auth is not configured in this app")
    return services.auth_service

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

# A plain `def`: FastAPI runs it in a thread so database readnever blocks the llop
def get_current_user(request : Request , auth : AuthServiceDep) -> User:
    user = auth.authenticate(request.cookies.get(AUTH_COOKIE))
    
    if user is None:
        raise UnauthenticatedError
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

def set_auth_cookie(request : Request , response : Response , token : str) -> None:
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age = 60 * 60 * 24 * request.app.state.settings.auth_session_days,
        httponly = True,
        samesite = "lax",
        secure = request.app.state.settings.cookie_secure,
        path = "/"
    )
    
def clear_auth_cookie(response : Response) -> None:
    response.delete_cookie(
        AUTH_COOKIE,
        path = "/",
        httponly = True,
        samesite = "lax",
    )
