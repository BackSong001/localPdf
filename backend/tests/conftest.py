import sys
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
TEST_DATA_DIR = ROOT_DIR / "test_data"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import create_app
from app.settings import Settings


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    return TEST_DATA_DIR


@pytest.fixture
def out_pdf(tmp_path: Path) -> Path:
    return tmp_path / "out.pdf"


@pytest.fixture
def base_settings(tmp_path: Path) -> Settings:
    return Settings(temp_dir=tmp_path, cleanup_interval_seconds=3600)


@pytest.fixture
def client(base_settings: Settings):
    with TestClient(create_app(base_settings)) as test_client:
        yield test_client


@pytest.fixture
def client_factory(base_settings: Settings):
    def _make(**overrides):
        settings = replace(base_settings, **overrides)
        return TestClient(create_app(settings))

    return _make


@pytest.fixture
def make_image():
    def _make(
        path: Path,
        size: tuple[int, int] = (100, 200),
        color=(255, 0, 0),
        image_format: str = "PNG",
        orientation: int | None = None,
    ) -> Path:
        image = Image.new("RGB", size, color)
        kwargs = {}
        if orientation is not None:
            exif = Image.Exif()
            exif[274] = orientation
            kwargs["exif"] = exif
        image.save(path, format=image_format, **kwargs)
        return path

    return _make


@pytest.fixture
def make_text_pdf():
    def _make(path: Path, pages: list[str]) -> Path:
        document = pymupdf.open()
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        document.save(str(path))
        document.close()
        return path

    return _make


@pytest.fixture
def make_image_only_pdf():
    def _make(path: Path, pages: int = 2) -> Path:
        document = pymupdf.open()
        for _ in range(pages):
            page = document.new_page()
            page.draw_rect(
                pymupdf.Rect(72, 72, 200, 200),
                color=(1, 0, 0),
                fill=(1, 0, 0),
            )
        document.save(str(path))
        document.close()
        return path

    return _make


@pytest.fixture
def make_mixed_pdf():
    def _make(path: Path) -> Path:
        document = pymupdf.open()
        text_page = document.new_page()
        text_page.insert_text((72, 72), "text page")
        image_page = document.new_page()
        image_page.draw_rect(
            pymupdf.Rect(72, 72, 200, 200),
            color=(1, 0, 0),
            fill=(1, 0, 0),
        )
        document.save(str(path))
        document.close()
        return path

    return _make


@pytest.fixture
def make_encrypted_pdf():
    def _make(path: Path) -> Path:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "secret")
        document.save(
            str(path),
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="user",
        )
        document.close()
        return path

    return _make
