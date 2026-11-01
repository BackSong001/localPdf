from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from app.errors import AppError
from app.services.text import extract_pdf_text
from app.services.uploads import make_temp_file, save_upload

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
