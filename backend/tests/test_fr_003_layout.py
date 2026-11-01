from pathlib import Path

import pytest

from tests.helpers import (
    A4_LANDSCAPE,
    A4_PORTRAIT,
    page_count,
    page_image_rect,
    page_size,
    save_solid_png,
)


def test_tc_fr_003_a_portrait_image_uses_a4_portrait(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_solid_png(tmp_path / "portrait.png", size=(100, 200))
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    width, height = page_size(out)
    assert width == pytest.approx(A4_PORTRAIT[0], abs=0.5)
    assert height == pytest.approx(A4_PORTRAIT[1], abs=0.5)


def test_tc_fr_003_b_landscape_image_uses_a4_landscape(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_solid_png(tmp_path / "landscape.png", size=(200, 100))
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    width, height = page_size(out)
    assert width == pytest.approx(A4_LANDSCAPE[0], abs=0.5)
    assert height == pytest.approx(A4_LANDSCAPE[1], abs=0.5)


def test_tc_fr_003_c_square_image_uses_a4_portrait(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_solid_png(tmp_path / "square.png", size=(150, 150))
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    width, height = page_size(out)
    assert width == pytest.approx(A4_PORTRAIT[0], abs=0.5)
    assert height == pytest.approx(A4_PORTRAIT[1], abs=0.5)


def test_tc_fr_003_d_page_count_matches_image_count(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    sources = [
        save_solid_png(tmp_path / f"{index}.png", color=(index * 40, 0, 0))
        for index in range(3)
    ]
    out = tmp_path / "out.pdf"

    build_pdf(sources, out)

    assert page_count(out) == 3


def test_tc_fr_003_e_image_is_centered_and_keeps_aspect_ratio(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source_width, source_height = 300, 200
    source = save_solid_png(
        tmp_path / "rect.png",
        size=(source_width, source_height),
    )
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    page_width, page_height = page_size(out)
    rect = page_image_rect(out)
    assert rect.x0 == pytest.approx((page_width - rect.width) / 2, abs=0.5)
    assert rect.y0 == pytest.approx((page_height - rect.height) / 2, abs=0.5)
    assert rect.width / rect.height == pytest.approx(
        source_width / source_height,
        rel=0.01,
    )
    assert rect.x0 >= 0 and rect.y0 >= 0
    assert rect.x1 <= page_width and rect.y1 <= page_height


def test_tc_fr_003_f_small_image_is_upscaled_to_fit(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_solid_png(tmp_path / "tiny.png", size=(10, 10))
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    rect = page_image_rect(out)
    assert rect.width == pytest.approx(A4_PORTRAIT[0], abs=0.5)
    assert rect.height == pytest.approx(A4_PORTRAIT[0], abs=0.5)
