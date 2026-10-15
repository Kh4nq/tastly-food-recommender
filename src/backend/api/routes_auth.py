# Controler for accounts : HTTP in HTTP out 
from fastapi import APIRouter, Request, Response, Depends
from starlette.concurrency import run_in_threadpool

from backend.api.deps import (
    AUTH_COOKIE,
    AuthServiceDep,
    CurrentUser,
    HashGateDep,
    clear_auth_cookie,
    limit_auth_attempts,
    require_allowed_origin,
    set_auth_cookie,
)

from backend.api.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserOut,
)

router = APIRouter(prefix="/api/auth" , dependencies = [Depends(require_allowed_origin)])

# Per-IP limit, applied only to the routes
attempt_limit = [Depends(limit_auth_attempts)]

@router.post(
    "/register", status_code=201, 
    response_model=AuthResponse , dependencies=attempt_limit
)
async def register(
    body: RegisterRequest, 
    request: Request, 
    response: Response, 
    auth: AuthServiceDep,
    gate: HashGateDep
) -> AuthResponse:
    result = await gate.run(auth.register, body.to_registration())
    set_auth_cookie(request, response, result.token)
    return AuthResponse(user = UserOut.from_user(result.user))

@router.post("/login", response_model = AuthResponse , dependencies = attempt_limit)
async def login(
    body: LoginRequest, 
    request: Request, 
    response: Response, 
    auth: AuthServiceDep,
    gate : HashGateDep
) -> AuthResponse:
    result = await gate.run(auth.login, body.email, body.password)
    set_auth_cookie(request, response, result.token)
    return AuthResponse(user = UserOut.from_user(result.user))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, auth: AuthServiceDep) -> None:
    # Idempotent: no cookie, or a dead one, is still a successful logout
    await run_in_threadpool(auth.logout, request.cookies.get(AUTH_COOKIE))
    clear_auth_cookie(response)


@router.get("/me", response_model=AuthResponse)
async def me(user: CurrentUser) -> AuthResponse:
    return AuthResponse(user=UserOut.from_user(user))


@router.put("/me", response_model=AuthResponse)
async def update_me(
    body: UpdateProfileRequest, user: CurrentUser, auth: AuthServiceDep
) -> AuthResponse:
    updated = await run_in_threadpool(
        auth.update_profile,
        user,
        full_name=body.full_name,
        phone=body.phone,
        shop_name=body.shop_name,
    )
    return AuthResponse(user=UserOut.from_user(updated))


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    auth: AuthServiceDep,
    gate : HashGateDep
) -> None:
    result = await gate.run(
        auth.change_password, user, body.current_password, body.new_password
    )
    set_auth_cookie(request, response, result.token)  # every old session is revoked