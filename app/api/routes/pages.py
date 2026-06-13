"""Server-rendered frontend shell routes for Phase 01."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.templates import templates

router = APIRouter(include_in_schema=False)
@router.get("/", response_class=RedirectResponse)
async def home() -> RedirectResponse:
    return RedirectResponse(url="/questions", status_code=307)


@router.get("/demo-guide", response_class=HTMLResponse)
async def demo_guide(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="demo_guide.html",
        context={"title": "Hướng dẫn demo", "active_page": "guide"},
    )
