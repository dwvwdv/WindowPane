"""Admin API behind the /dashboard page (``Authorization: Bearer $WORLDPANE_ADMIN_TOKEN``).

Kept out of openapi.json: that file is the device contract for the ESP32 firmware.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status

from .. import schemas
from ..admin import AdminService
from .deps import get_admin, require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)],
                   include_in_schema=False)


@router.get("/profiles", response_model=list[schemas.AdminProfile])
def list_profiles(admin: AdminService = Depends(get_admin)):
    return admin.profiles()


@router.get("/worlds", response_model=list[schemas.AdminWorldSummary])
def list_worlds(admin: AdminService = Depends(get_admin)):
    return admin.list_worlds()


@router.post("/worlds", response_model=schemas.AdminCreateWorldOut, status_code=status.HTTP_201_CREATED)
def create_world(body: schemas.AdminCreateWorldIn = Body(default_factory=schemas.AdminCreateWorldIn),
                 admin: AdminService = Depends(get_admin)):
    return admin.create_world(body)


@router.get("/worlds/{world_id}", response_model=schemas.AdminWorld)
def get_world(world_id: UUID, admin: AdminService = Depends(get_admin)):
    return admin.world(str(world_id))


@router.patch("/worlds/{world_id}", response_model=schemas.AdminWorld)
def patch_world(world_id: UUID, body: schemas.AdminWorldPatch, admin: AdminService = Depends(get_admin)):
    return admin.update_world(str(world_id), body)


@router.post("/worlds/{world_id}/characters", response_model=schemas.AdminWorld,
             status_code=status.HTTP_201_CREATED)
def add_character(world_id: UUID, body: schemas.AdminCharacterIn, admin: AdminService = Depends(get_admin)):
    return admin.add_character(str(world_id), body)


@router.patch("/worlds/{world_id}/characters/{character_id}", response_model=schemas.AdminWorld)
def patch_character(world_id: UUID, character_id: UUID, body: schemas.AdminCharacterPatch,
                    admin: AdminService = Depends(get_admin)):
    return admin.update_character(str(world_id), str(character_id), body)


@router.delete("/worlds/{world_id}/characters/{character_id}", response_model=schemas.AdminWorld)
def archive_character(world_id: UUID, character_id: UUID, admin: AdminService = Depends(get_admin)):
    """Soft delete (archive): the character keeps its history."""
    return admin.archive_character(str(world_id), str(character_id))


@router.post("/worlds/{world_id}/pairing-codes", response_model=schemas.PairingCodeOut,
             status_code=status.HTTP_201_CREATED)
def issue_pairing_code(world_id: UUID,
                       body: schemas.PairingCodeIn = Body(default_factory=schemas.PairingCodeIn),
                       admin: AdminService = Depends(get_admin)):
    return admin.service.issue_pairing_code(str(world_id), body.max_uses)


@router.get("/worlds/{world_id}/history", response_model=schemas.WorldHistory)
def world_history(world_id: UUID, date_: date = Query(alias="date"), admin: AdminService = Depends(get_admin)):
    return admin.service.history(str(world_id), date_)


@router.get("/monitor", response_model=schemas.Monitor)
def monitor(world_id: list[UUID] = Query(default=[], description="Worlds to show; all when omitted"),
            admin: AdminService = Depends(get_admin)):
    return admin.monitor([str(w) for w in world_id])
