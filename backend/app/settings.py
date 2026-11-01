from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _as_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _as_csv(env: Mapping[str, str], name: str, default: str) -> tuple[str, ...]:
    raw = env.get(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _api_keys(env: Mapping[str, str], base_name: str) -> tuple[str, ...]:
    keys: list[str] = []
    base = env.get(base_name, "").strip()
    if base:
        keys.append(base)

    numbered: list[tuple[int, str]] = []
    prefix = f"{base_name}_"
    for name, value in env.items():
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix) :]
        if not suffix.isdigit():
            continue
        key = value.strip()
        if key:
            numbered.append((int(suffix), key))

    for _, key in sorted(numbered):
        if key not in keys:
            keys.append(key)
    return tuple(keys)


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    temp_dir: Path | None = None
    max_files: int = 1000
    max_image_bytes: int = 50 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_pdf_bytes: int = 100 * 1024 * 1024
    max_pdf_pages: int = 2000
    job_ttl_seconds: int = 3600
    cleanup_interval_seconds: int = 600
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    version: str = VERSION
    llm_provider: str = "gemini"
    gemini_api_keys: tuple[str, ...] = ()
    gemini_model: str = "gemini-3.1-flash-lite"
    nvidia_api_keys: tuple[str, ...] = ()
    nvidia_model: str = "deepseek-ai/deepseek-v4.1-flash"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_timeout_seconds: float = 30.0
    llm_max_chunk_chars: int = 12000


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv(PROJECT_ROOT / ".env")
        env = os.environ

    temp_dir_raw = env.get("LOCALPDF_TEMP_DIR", "").strip()
    return Settings(
        host=env.get("LOCALPDF_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_as_int(env, "LOCALPDF_PORT", 8000),
        temp_dir=Path(temp_dir_raw) if temp_dir_raw else None,
        max_files=_as_int(env, "LOCALPDF_MAX_FILES", 1000),
        max_image_bytes=_as_int(env, "LOCALPDF_MAX_IMAGE_BYTES", 50 * 1024 * 1024),
        max_total_bytes=_as_int(env, "LOCALPDF_MAX_TOTAL_BYTES", 2 * 1024 * 1024 * 1024),
        max_pdf_bytes=_as_int(env, "LOCALPDF_MAX_PDF_BYTES", 100 * 1024 * 1024),
        max_pdf_pages=_as_int(env, "LOCALPDF_MAX_PDF_PAGES", 2000),
        job_ttl_seconds=_as_int(env, "LOCALPDF_JOB_TTL_SECONDS", 3600),
        cleanup_interval_seconds=_as_int(env, "LOCALPDF_CLEANUP_INTERVAL_SECONDS", 600),
        cors_origins=_as_csv(
            env,
            "LOCALPDF_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ),
        version=env.get("LOCALPDF_VERSION", VERSION).strip() or VERSION,
        llm_provider=env.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini",
        gemini_api_keys=_api_keys(env, "GEMINI_API_KEY"),
        gemini_model=env.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
        or "gemini-3.1-flash-lite",
        nvidia_api_keys=_api_keys(env, "NVIDIA_API_KEY"),
        nvidia_model=env.get("NVIDIA_MODEL", "deepseek-ai/deepseek-v4.1-flash").strip()
        or "deepseek-ai/deepseek-v4.1-flash",
        nvidia_base_url=env.get(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        ).strip()
        or "https://integrate.api.nvidia.com/v1",
        llm_timeout_seconds=_as_float(env, "LLM_TIMEOUT_SECONDS", 30.0),
        llm_max_chunk_chars=_as_int(env, "LLM_MAX_CHUNK_CHARS", 12000),
    )
