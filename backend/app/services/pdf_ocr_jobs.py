from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.errors import AppError
from app.services.pdf_ocr import add_pdf_text_layer
from app.services.uploads import remove_tree


@dataclass(slots=True)
class PdfOcrJob:
    id: str
    status: str
    total: int
    processed: int
    error: dict[str, str] | None
    created_at: datetime
    directory: Path
    input_path: Path
    output_path: Path


class PdfOcrJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, PdfOcrJob] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = threading.RLock()

    def create(self, directory: Path, total: int) -> PdfOcrJob:
        job_id = uuid4().hex
        job = PdfOcrJob(
            id=job_id,
            status="queued",
            total=total,
            processed=0,
            error=None,
            created_at=datetime.now(UTC),
            directory=directory,
            input_path=directory / "input.pdf",
            output_path=directory / "searchable.pdf",
        )
        with self._lock:
            self._jobs[job_id] = job
        task = asyncio.create_task(self._process(job), name=f"pdf-ocr-{job_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str) -> PdfOcrJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND")
        return job

    def snapshot(self, job_id: str) -> dict:
        job = self.get(job_id)
        return {
            "job_id": job.id,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "error": job.error,
            "created_at": job.created_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "download_url": (
                f"/api/pdf/ocr/{job.id}/download" if job.status == "done" else None
            ),
        }

    def output(self, job_id: str) -> Path:
        job = self.get(job_id)
        if job.status != "done":
            raise AppError("JOB_NOT_READY")
        return job.output_path

    async def stop(self) -> None:
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for job in jobs:
            remove_tree(job.directory)

    async def _process(self, job: PdfOcrJob) -> None:
        with self._lock:
            job.status = "converting"

        def progress(processed: int) -> None:
            with self._lock:
                job.processed = processed

        try:
            await asyncio.to_thread(
                add_pdf_text_layer,
                job.input_path,
                job.output_path,
                job.total,
                on_progress=progress,
            )
        except asyncio.CancelledError:
            raise
        except AppError as exc:
            with self._lock:
                job.status = "error"
                job.error = exc.detail()
        except Exception:  # noqa: BLE001
            with self._lock:
                job.status = "error"
                job.error = AppError("CONVERSION_FAILED").detail()
        else:
            with self._lock:
                job.status = "done"
                job.processed = job.total
