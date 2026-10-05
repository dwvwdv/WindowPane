from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, Header, Query, Response, status

from .. import schemas
from ..domain import Device
from ..services import WorldService, etag_matches
from .deps import get_service, require_device

router = APIRouter(prefix="/api/v1")

AUTH_ERRORS = {401: {"model": schemas.ErrorResponse, "description": "Missing or invalid device token"}}


@router.get(
    "/world/state",
    response_model=schemas.WorldState,
    tags=["world"],
    summary="Current semantic state of the World this device is bound to",
    responses={
        304: {"description": "Not modified (If-None-Match matched the current ETag)"},
        **AUTH_ERRORS,
    },
)
def get_world_state(
    response: Response,
    if_none_match: str | None = Header(default=None),
    device: Device = Depends(require_device),
    service: WorldService = Depends(get_service),
):
    result = service.device_state(device.world_id)
    headers = {"ETag": result.etag, "Cache-Control": "no-cache"}
    if etag_matches(if_none_match, result.etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return result.state


@router.get(
    "/world/history",
    response_model=schemas.WorldHistory,
    tags=["world"],
    summary="Per-character event history for one World-local date",
    responses={422: {"description": "Malformed date or date in the future"}, **AUTH_ERRORS},
)
def get_world_history(
    date_: date = Query(alias="date", description="YYYY-MM-DD in the World's timezone"),
    device: Device = Depends(require_device),
    service: WorldService = Depends(get_service),
):
    return service.history(device.world_id, date_)


@router.post(
    "/device/input",
    response_model=schemas.DeviceInputAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["device"],
    summary="Button press / local interaction from the device",
    responses=AUTH_ERRORS,
)
def post_device_input(
    body: schemas.DeviceInputIn,
    device: Device = Depends(require_device),
    service: WorldService = Depends(get_service),
):
    return service.record_input(device, body)


@router.post(
    "/device/pair",
    response_model=schemas.DeviceCredentials,
    status_code=status.HTTP_201_CREATED,
    tags=["pairing"],
    summary="Bind a new device to a World using a pairing code (unauthenticated)",
    responses={400: {"model": schemas.ErrorResponse,
                     "description": "invalid_pairing_code | pairing_code_expired | pairing_code_exhausted"}},
)
def post_device_pair(body: schemas.PairIn, service: WorldService = Depends(get_service)):
    return service.pair(body.pairing_code, body.firmware_version)


@router.post(
    "/world",
    response_model=schemas.CreateWorldOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pairing"],
    summary="Create a World (first device flow): returns the creator's token and a pairing code",
)
def post_world(
    body: schemas.CreateWorldIn = Body(default_factory=schemas.CreateWorldIn),
    service: WorldService = Depends(get_service),
):
    return service.create_world(body)


@router.post(
    "/world/pairing-codes",
    response_model=schemas.PairingCodeOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pairing"],
    summary="Issue a new pairing code for this device's World (invite another device)",
    responses=AUTH_ERRORS,
)
def post_pairing_code(
    body: schemas.PairingCodeIn = Body(default_factory=schemas.PairingCodeIn),
    device: Device = Depends(require_device),
    service: WorldService = Depends(get_service),
):
    return service.issue_pairing_code(device.world_id, body.max_uses)
