from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse

from app.errors import AppError
from app.services.pdf_ocr_jobs import PdfOcrJobManager
from app.services.text import extract_pdf_text
from app.services.uploads import create_job_dir, make_temp_file, remove_tree, save_upload

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


@router.post("/text")
async def extract_text(
    request: Request,
    file: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    settings = request.app.state.settings
    if not file:
        raise AppError("EMPTY_UPLOAD")

    upload = file[0]
    for extra in file[1:]:
        await extra.close()

    path: Path = make_temp_file(settings, ".pdf")
    try:
        await save_upload(upload, path, settings.max_pdf_bytes, "PDF_TOO_LARGE")
        result = await asyncio.to_thread(
            extract_pdf_text,
            path,
            settings.max_pdf_pages,
        )
        return result.as_dict()
    finally:
        path.unlink(missing_ok=True)


@router.post("/ocr", status_code=202)
async def add_ocr_text_layer(
    request: Request,
    file: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    settings = request.app.state.settings
    if not file:
        raise AppError("EMPTY_UPLOAD")

    upload = file[0]
    for extra in file[1:]:
        await extra.close()

    directory = create_job_dir(settings, uuid4().hex)
    input_path = directory / "input.pdf"
    created = False
    try:
        await save_upload(upload, input_path, settings.max_pdf_bytes, "PDF_TOO_LARGE")
        result = await asyncio.to_thread(
            extract_pdf_text, input_path, settings.max_pdf_pages
        )
        manager: PdfOcrJobManager = request.app.state.pdf_ocr_manager
        job = manager.create(directory, result.page_count)
        created = True
        return manager.snapshot(job.id)
    finally:
        if not created:
            remove_tree(directory)


@router.get("/ocr/{job_id}")
def get_ocr_job(request: Request, job_id: str) -> dict:
    manager: PdfOcrJobManager = request.app.state.pdf_ocr_manager
    return manager.snapshot(job_id)


@router.get("/ocr/{job_id}/download")
def download_ocr_job(request: Request, job_id: str) -> FileResponse:
    manager: PdfOcrJobManager = request.app.state.pdf_ocr_manager
    output_path = manager.output(job_id)
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename="searchable.pdf",
    )
