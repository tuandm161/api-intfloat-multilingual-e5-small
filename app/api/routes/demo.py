"""Development-only demo reset endpoint."""

from fastapi import APIRouter

from app.api.dependencies import DbSession, SettingsDependency
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.core.responses import success_response
from app.db.bootstrap import reset_demo

router = APIRouter(tags=["demo"])


@router.post("/demo/reset")
def reset(db: DbSession, settings: SettingsDependency) -> dict:
    if settings.app_env != "development":
        raise AppError(ErrorCode.NOT_FOUND, "Không tìm thấy tài nguyên", status_code=404)
    return success_response(reset_demo(db, settings))
