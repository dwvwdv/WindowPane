from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..admin import AdminService
from ..domain import Device
from ..services import WorldService

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


admin_bearer = HTTPBearer(auto_error=False, description="WORLDPANE_ADMIN_TOKEN")


def get_admin(request: Request) -> AdminService:
    return request.app.state.admin


def require_admin(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(admin_bearer)) -> None:
    expected = request.app.state.settings.admin_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={"code": "admin_disabled", "message": "Set WORLDPANE_ADMIN_TOKEN to enable the admin API"},
        )
    given = creds.credentials if creds is not None and creds.scheme.lower() == "bearer" else ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "Missing or invalid admin token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
