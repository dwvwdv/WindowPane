from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
