from pathlib import Path

from PIL import Image, ImageOps

from tests.helpers import assert_similar, extract_page_image, save_exif_jpeg


def _expected_image(source: Path) -> Image.Image:
    with Image.open(source) as image:
        return ImageOps.exif_transpose(image).copy()


def test_tc_fr_004_a_exif_orientation_6_is_applied(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_exif_jpeg(tmp_path / "exif6.jpg", orientation=6)
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    assert_similar(extract_page_image(out, 0), _expected_image(source))


def test_tc_fr_004_b_exif_orientation_3_is_applied(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    source = save_exif_jpeg(tmp_path / "exif3.jpg", orientation=3)
    out = tmp_path / "out.pdf"

    build_pdf([source], out)

    assert_similar(extract_page_image(out, 0), _expected_image(source))
