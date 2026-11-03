from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.errors import AppError
from app.services.images import SUPPORTED_IMAGE_EXTENSIONS, validate_image_file
from app.services.uploads import create_job_dir, remove_tree, save_upload

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", status_code=202)
async def create_job(
    request: Request,
    files: Annotated[list[UploadFile] | None, File()] = None,
    ocr: bool = Form(True),
) -> JSONResponse:
    settings = request.app.state.settings
    manager = request.app.state.manager

    if not files:
        raise AppError("EMPTY_UPLOAD")
    if len(files) > settings.max_files:
        raise AppError("TOO_MANY_FILES")

    job_id = uuid4().hex
    job_dir = create_job_dir(settings, job_id)
    uploads_dir = job_dir / "uploads"
    uploads_dir.mkdir(mode=0o700)
    total_bytes = 0
    created = False

    try:
        for index, upload in enumerate(files):
            filename = upload.filename or f"image-{index}"
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                raise AppError(
                    "UNSUPPORTED_IMAGE",
                    f"지원하지 않는 이미지 형식입니다: {filename}",
                )

            destination = uploads_dir / f"{index:04d}{suffix}"
            size = await save_upload(
                upload,
                destination,
                settings.max_image_bytes,
                "FILE_TOO_LARGE",
            )
            if size == 0:
                raise AppError(
                    "INVALID_IMAGE",
                    f"이미지 파일이 비어 있습니다: {filename}",
                )
            total_bytes += size
            if total_bytes > settings.max_total_bytes:
                raise AppError("TOTAL_SIZE_EXCEEDED")

            await asyncio.to_thread(validate_image_file, destination)

        try:
            job = manager.create_job(job_id, job_dir, len(files), ocr=ocr)
        except Exception as exc:
            # Convert unexpected errors to INTERNAL_ERROR without leaking details
            raise AppError("INTERNAL_ERROR") from exc
        created = True
        return JSONResponse(status_code=202, content=manager.snapshot(job.id))
    finally:
        if not created:
            remove_tree(job_dir)


@router.get("/{job_id}")
def get_job(request: Request, job_id: str) -> dict:
    return request.app.state.manager.snapshot(job_id)


@router.get("/{job_id}/download")
def download_job(request: Request, job_id: str) -> FileResponse:
    path = request.app.state.manager.download_path(job_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"localpdf-{job_id}.pdf",
    )


@router.get("/{job_id}/markdown")
def download_job_markdown(request: Request, job_id: str) -> FileResponse:
    path = request.app.state.manager.download_markdown_path(job_id)
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=f"localpdf-{job_id}.md",
    )


@router.post("/{job_id}/summarize")
async def summarize_job(request: Request, job_id: str) -> dict:
    from app.services.llm import summarize_text
    path = request.app.state.manager.download_markdown_path(job_id)
    text = path.read_text(encoding="utf-8")
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    provider = body.get("provider") if isinstance(body, dict) else None
    return summarize_text(text, request.app.state.settings, provider=provider)
