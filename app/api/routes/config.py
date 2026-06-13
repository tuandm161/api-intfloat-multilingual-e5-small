"""Safe public configuration endpoint."""

from fastapi import APIRouter

from app.api.dependencies import SettingsDependency
from app.core.responses import ApiResponse, success_response

router = APIRouter(tags=["system"])


@router.get("/config/public", response_model=ApiResponse[dict[str, str | int]])
async def public_config(settings: SettingsDependency) -> dict:
    return success_response(settings.public_config())
