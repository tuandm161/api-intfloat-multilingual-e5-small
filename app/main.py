"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    audit,
    candidates,
    config,
    demo,
    embeddings,
    exams,
    exports,
    health,
    pages,
    paraphrase_jobs,
    questions,
)
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.bootstrap import initialize_demo
from app.db.session import SessionLocal

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        initialize_demo(db, get_settings())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Demo diễn đạt lại câu hỏi",
        description="Ứng dụng đánh giá câu hỏi y khoa và điều dưỡng được diễn đạt lại.",
        version="0.1.0",
        debug=settings.app_env == "development",
        lifespan=lifespan,
    )

    application.mount(
        "/static",
        StaticFiles(directory=str(APP_DIR / "static")),
        name="static",
    )
    application.include_router(health.router)
    application.include_router(config.router)
    application.include_router(questions.router)
    application.include_router(paraphrase_jobs.router)
    application.include_router(candidates.router)
    application.include_router(embeddings.router)
    application.include_router(exams.router)
    application.include_router(audit.router)
    application.include_router(exports.router)
    application.include_router(demo.router)
    application.include_router(pages.router)
    register_exception_handlers(application)
    return application


app = create_app()
