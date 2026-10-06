from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..admin import AdminService
from ..domain import Device
from ..services import WorldService
from ..supabase_auth import AuthUnavailable, SupabaseAuth

bearer = HTTPBearer(auto_error=False, description="Device token from /device/pair or POST /world")


def get_service(request: Request) -> WorldService:
    return request.app.state.service


def require_device(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    service: WorldService = Depends(get_service),
) -> Device:
    unauthorized = HTTPException(
        status_code=401,
        detail={"code": "unauthorized", "message": "Missing or invalid device token"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise unauthorized
    device = service.authenticate(creds.credentials)
    if device is None:
        raise unauthorized
    return device


admin_bearer = HTTPBearer(auto_error=False, description="Supabase Auth access token, or WORLDPANE_ADMIN_TOKEN")


@dataclass(frozen=True)
class AdminPrincipal:
    via: str  # "supabase" | "token"
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None


def get_admin(request: Request) -> AdminService:
    return request.app.state.admin


def _admin_error(status: int, code: str, message: str) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return HTTPException(status_code=status, detail={"code": code, "message": message}, headers=headers)


def require_admin(request: Request,
                  creds: HTTPAuthorizationCredentials | None = Depends(admin_bearer)) -> AdminPrincipal:
    settings = request.app.state.settings
    supabase: SupabaseAuth | None = request.app.state.supabase_auth
    if not settings.admin_token and supabase is None:
        raise _admin_error(503, "admin_disabled",
                           "Set WORLDPANE_SUPABASE_URL / WORLDPANE_SUPABASE_ANON_KEY "
                           "(or WORLDPANE_ADMIN_TOKEN) to enable the admin API")
    given = creds.credentials if creds is not None and creds.scheme.lower() == "bearer" else ""
    if not given:
        raise _admin_error(401, "unauthorized", "Sign in to use the dashboard")
    if settings.admin_token and hmac.compare_digest(given.encode(), settings.admin_token.encode()):
        return AdminPrincipal(via="token")
    if supabase is None:
        raise _admin_error(401, "unauthorized", "Missing or invalid admin token")
    try:
        user = supabase.verify(given)
    except AuthUnavailable as exc:
        raise _admin_error(503, "auth_unavailable", "Supabase Auth is unreachable, retry") from exc
    if user is None:
        raise _admin_error(401, "unauthorized", "Session expired or invalid, sign in again")
    name = request.app.state.service.repo.get_admin_name(user.id)
    if name is None:
        raise _admin_error(403, "not_admin", "This account is not a WorldPane dashboard admin")
    return AdminPrincipal(via="supabase", user_id=user.id, email=user.email, display_name=name)
