from pathlib import Path

from tests.helpers import (
    center_pixel,
    extract_page_image,
    save_alpha_png,
    save_palette_transparency_png,
)


def test_tc_fr_005_a_transparent_png_is_flattened_on_white(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_alpha_png(tmp_path / "alpha.png")
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    image = extract_page_image(out, 0)
    assert image.mode in ("RGB", "L"), image.mode
    corner = image.convert("RGB").getpixel((0, 0))
    assert all(channel >= 250 for channel in corner), corner
    center = center_pixel(image)
    assert center[0] > 200 and center[1] < 60 and center[2] < 60, center


def test_tc_fr_005_b_palette_transparency_is_flattened_on_white(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_palette_transparency_png(tmp_path / "palette.png")
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    image = extract_page_image(out, 0)
    assert image.mode in ("RGB", "L"), image.mode
    corner = image.convert("RGB").getpixel((0, 0))
    assert all(channel >= 250 for channel in corner), corner
    center = center_pixel(image)
    assert center[0] > 200 and center[1] < 60 and center[2] < 60, center


def test_tc_fr_005_c_semi_transparent_red_is_composited_on_white(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_alpha_png(
        tmp_path / "semi.png",
        background=(255, 0, 0, 128),
        fill=(255, 0, 0, 128),
        box=(0, 0, 100, 100),
    )
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    image = extract_page_image(out, 0)
    assert image.mode in ("RGB", "L"), image.mode
    center = center_pixel(image)
    assert abs(center[0] - 255) <= 8, center
    assert abs(center[1] - 127) <= 8, center
    assert abs(center[2] - 127) <= 8, center
