from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile

from app.errors import AppError
from app.settings import Settings

CHUNK_SIZE = 1024 * 1024


async def save_upload(
    upload: UploadFile,
    dest: Path,
    max_bytes: int,
    too_large_code: str,
) -> int:
    total = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("wb") as output:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise AppError(too_large_code)
                output.write(chunk)
    finally:
        await upload.close()
    return total


def create_job_dir(settings: Settings, job_id: str) -> Path:
    base = settings.temp_dir or Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    job_dir = base / f"localpdf-{job_id}"
    job_dir.mkdir(mode=0o700, exist_ok=False)
    return job_dir


def make_temp_file(settings: Settings, suffix: str) -> Path:
    base = settings.temp_dir
    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix="localpdf-",
        suffix=suffix,
        dir=str(base) if base is not None else None,
    )
    os.close(fd)
    path = Path(name)
    path.chmod(0o600)
    return path


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
