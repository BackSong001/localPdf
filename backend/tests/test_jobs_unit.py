import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.errors import AppError
from app.services.jobs import JobManager
from app.settings import Settings


def _job_dir(root: Path, name: str = "job") -> Path:
    path = root / name
    (path / "uploads").mkdir(parents=True)
    (path / "uploads" / "0000.png").write_bytes(b"x")
    return path


def test_tc_fr_006_a_status_transitions(tmp_path: Path) -> None:
    manager = JobManager(Settings(temp_dir=tmp_path))
    job = manager.create_job("abc", _job_dir(tmp_path), 1)

    manager._set_status(job.id, "converting")
    with pytest.raises(ValueError):
        manager._set_status(job.id, "queued")
    manager._set_status(job.id, "done")
    with pytest.raises(ValueError):
        manager._set_status(job.id, "converting")


def test_tc_fr_012_a_expired_done_job_is_removed(tmp_path: Path) -> None:
    current = [datetime(2026, 1, 1, tzinfo=UTC)]
    settings = Settings(
        temp_dir=tmp_path,
        job_ttl_seconds=10,
        cleanup_interval_seconds=3600,
    )
    manager = JobManager(settings, clock=lambda: current[0])
    job = manager.create_job("abc", _job_dir(tmp_path), 1)
    manager._set_status(job.id, "converting")
    manager._set_status(job.id, "done")

    current[0] += timedelta(seconds=11)
    removed = manager.cleanup_expired()

    assert removed == [job.id]
    assert not job.dir.exists()
    with pytest.raises(AppError) as error:
        manager.get_job(job.id)
    assert error.value.code == "JOB_NOT_FOUND"


def test_tc_fr_012_d_active_job_is_not_cleaned(tmp_path: Path) -> None:
    current = [datetime(2026, 1, 1, tzinfo=UTC)]
    settings = Settings(
        temp_dir=tmp_path,
        job_ttl_seconds=0,
        cleanup_interval_seconds=3600,
    )
    manager = JobManager(settings, clock=lambda: current[0])
    job = manager.create_job("abc", _job_dir(tmp_path), 1)

    current[0] += timedelta(days=1)

    assert manager.cleanup_expired() == []
    assert job.dir.exists()
    assert manager.get_job(job.id).status == "queued"


def test_tc_fr_012_b_failed_job_removes_partial_output(tmp_path: Path) -> None:
    def failing_builder(uploads, output, normalized_dir, on_progress):
        on_progress(1)
        output.write_bytes(b"partial")
        raise RuntimeError("boom")

    async def scenario() -> None:
        settings = Settings(temp_dir=tmp_path, cleanup_interval_seconds=3600)
        manager = JobManager(settings, builder=failing_builder)
        await manager.start()
        job = manager.create_job("abc", _job_dir(tmp_path), 2)
        for _ in range(100):
            snapshot = manager.snapshot(job.id)
            if snapshot["status"] == "error":
                break
            await asyncio.sleep(0.01)
        assert snapshot["status"] == "error"
        assert snapshot["error"]["code"] == "CONVERSION_FAILED"
        assert snapshot["processed"] == 1
        assert not job.output_path.exists()
        assert job.dir.exists()
        await manager.stop()

    asyncio.run(scenario())


def test_tc_fr_012_c_shutdown_removes_all_job_dirs(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = Settings(temp_dir=tmp_path, cleanup_interval_seconds=3600)
        manager = JobManager(settings)
        await manager.start()
        job = manager.create_job("abc", _job_dir(tmp_path), 1)
        assert job.dir.exists()
        await manager.stop()
        assert not job.dir.exists()

    asyncio.run(scenario())


def test_tc_fr_006_c_worker_marks_error_on_builder_failure(tmp_path: Path) -> None:
    def failing_builder(*_args, **_kwargs):
        raise RuntimeError("boom")

    async def scenario() -> None:
        settings = Settings(temp_dir=tmp_path, cleanup_interval_seconds=3600)
        manager = JobManager(settings, builder=failing_builder)
        await manager.start()
        job = manager.create_job("abc", _job_dir(tmp_path), 1)
        for _ in range(100):
            snapshot = manager.snapshot(job.id)
            if snapshot["status"] == "error":
                break
            await asyncio.sleep(0.01)
        assert snapshot["status"] == "error"
        assert snapshot["processed"] == 0
        await manager.stop()

    asyncio.run(scenario())
