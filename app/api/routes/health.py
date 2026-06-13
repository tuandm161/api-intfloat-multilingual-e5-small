"""Service health endpoint."""

from fastapi import APIRouter

from app.core.responses import ApiResponse, success_response

router = APIRouter(tags=["system"])


@router.get("/health", response_model=ApiResponse[dict[str, str]])
async def health_check() -> dict:
    return success_response(
        {"status": "ok", "service": "question-paraphrase-demo"}
    )
