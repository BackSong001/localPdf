from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from app.errors import AppError
from app.services.pdf_builder import build_pdf
from app.services.uploads import remove_tree
from app.settings import Settings

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "converting", "done", "error"]
TERMINAL_STATUSES = {"done", "error"}


@dataclass(slots=True)
class JobError:
    code: str
    message: str


@dataclass(slots=True)
class Job:
    id: str
    status: JobStatus
    total: int
    processed: int
    error: JobError | None
    created_at: datetime
    completed_at: datetime | None
    dir: Path
    output_path: Path


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class JobManager:
    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
        builder: Callable[..., Path] | None = None,
    ) -> None:
        self.settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._builder = builder or build_pdf
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(
                self._worker(), name="localpdf-worker"
            )
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(), name="localpdf-cleanup"
            )

    async def stop(self) -> None:
        tasks = [task for task in (self._worker_task, self._cleanup_task) if task]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._worker_task = None
        self._cleanup_task = None
        self.cleanup_all()

    def create_job(self, job_id: str, job_dir: Path, total: int) -> Job:
        job = Job(
            id=job_id,
            status="queued",
            total=total,
            processed=0,
            error=None,
            created_at=self._clock(),
            completed_at=None,
            dir=job_dir,
            output_path=job_dir / "output.pdf",
        )
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put_nowait(job_id)
        return job

    def get_job(self, job_id: str) -> Job:
        expired_path: Path | None = None
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("JOB_NOT_FOUND")
            if self._is_expired(job):
                self._jobs.pop(job_id, None)
                expired_path = job.dir
            else:
                return job
        if expired_path is not None:
            remove_tree(expired_path)
        raise AppError("JOB_NOT_FOUND")

    def snapshot(self, job_id: str) -> dict:
        with self._lock:
            job = self.get_job(job_id)
            error = (
                {"code": job.error.code, "message": job.error.message}
                if job.error is not None
                else None
            )
            return {
                "job_id": job.id,
                "status": job.status,
                "total": job.total,
                "processed": job.processed,
                "error": error,
                "created_at": _iso_utc(job.created_at),
                "download_url": (
                    f"/api/jobs/{job.id}/download" if job.status == "done" else None
                ),
            }

    def download_path(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        if job.status != "done":
            raise AppError("JOB_NOT_READY")
        if not job.output_path.exists():
            raise AppError("JOB_NOT_FOUND")
        return job.output_path

    def cleanup_expired(self) -> list[str]:
        now = self._clock()
        expired: list[Job] = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if (
                    job.status in TERMINAL_STATUSES
                    and job.completed_at is not None
                    and now >= job.completed_at
                    + timedelta(seconds=self.settings.job_ttl_seconds)
                ):
                    expired.append(job)
                    self._jobs.pop(job_id, None)
        for job in expired:
            remove_tree(job.dir)
        return [job.id for job in expired]

    def cleanup_all(self) -> None:
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for job in jobs:
            remove_tree(job.dir)

    def _is_expired(self, job: Job) -> bool:
        if job.status not in TERMINAL_STATUSES or job.completed_at is None:
            return False
        return self._clock() >= job.completed_at + timedelta(
            seconds=self.settings.job_ttl_seconds
        )

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            allowed = {
                ("queued", "converting"),
                ("converting", "done"),
                ("converting", "error"),
            }
            if (job.status, status) not in allowed:
                raise ValueError(f"invalid transition {job.status} -> {status}")
            job.status = status
            if status in TERMINAL_STATUSES:
                job.completed_at = self._clock()

    def _set_processed(self, job_id: str, processed: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.processed = min(job.total, max(job.processed, processed))

    def _finish(
        self,
        job_id: str,
        status: Literal["done", "error"],
        error: JobError | None = None,
    ) -> None:
        self._set_status(job_id, status)
        if error is not None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.error = error

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("unexpected worker error job_id=%s", job_id)
            finally:
                self._queue.task_done()

    async def _process(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return
            uploads = sorted(job.dir.glob("uploads/*"), key=lambda path: path.name)
            output_path = job.output_path

        self._set_status(job_id, "converting")
        try:
            await asyncio.to_thread(
                self._builder,
                uploads,
                output_path,
                job.dir / "normalized",
                lambda count: self._set_processed(job_id, count),
            )
        except asyncio.CancelledError:
            output_path.unlink(missing_ok=True)
            raise
        except Exception:
            output_path.unlink(missing_ok=True)
            logger.exception("conversion failed job_id=%s", job_id)
            self._finish(
                job_id,
                "error",
                JobError("CONVERSION_FAILED", "이미지 변환 중 오류가 발생했습니다."),
            )
        else:
            self._finish(job_id, "done")

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval_seconds)
            try:
                self.cleanup_expired()
            except Exception:
                logger.exception("cleanup failed")
