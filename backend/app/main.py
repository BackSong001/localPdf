from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import health, jobs, pdf, summarize
from app.errors import AppError
from app.services.jobs import JobManager
from app.services.pdf_ocr_jobs import PdfOcrJobManager
from app.settings import PROJECT_ROOT, Settings, load_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    manager = JobManager(settings)
    pdf_ocr_manager = PdfOcrJobManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()
            await pdf_ocr_manager.stop()

    app = FastAPI(
        title="localPdf",
        version=settings.version,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.manager = manager
    app.state.pdf_ocr_manager = pdf_ocr_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(pdf.router)
    app.include_router(summarize.router)

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": exc.detail()},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        missing_upload = any(
            error.get("type") == "missing"
            and tuple(error.get("loc", []))[-1:] in (("files",), ("file",))
            for error in exc.errors()
        )
        code = "EMPTY_UPLOAD" if missing_upload else "INVALID_REQUEST"
        error = AppError(code)
        return JSONResponse(
            status_code=error.http_status,
            content={"detail": error.detail()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Preserve AppError if somehow not caught by the specific handler
        if isinstance(exc, AppError):
            return JSONResponse(status_code=exc.http_status, content={"detail": exc.detail()})
        # Log a generic error without exception details to avoid leaking secrets
        logger.error("unhandled error: %s", type(exc).__name__)
        # Return a generic internal error response
        error = AppError("INTERNAL_ERROR")
        return JSONResponse(status_code=error.http_status, content={"detail": error.detail()})

    dist = PROJECT_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = create_app()
