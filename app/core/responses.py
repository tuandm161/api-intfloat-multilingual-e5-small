"""Stable response contracts shared by every API endpoint."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.enums import ErrorCode

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    details: Any = None


class ApiResponse(BaseModel, Generic[DataT]):
    success: bool
    data: DataT | None
    error: ErrorDetail | None


def success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def error_response(
    code: ErrorCode,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code.value,
            "message": message,
            "details": details,
        },
    }
