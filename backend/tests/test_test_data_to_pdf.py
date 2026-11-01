from pathlib import Path

import pytest
from PIL import Image, ImageOps

from tests.helpers import A4_PORTRAIT, assert_similar, extract_page_image, page_count, page_size


def test_tc_fr_003_d_test_data_images_to_pdf(test_data_dir: Path, tmp_path: Path) -> None:
    from app.services.images import collect_images
    from app.services.pdf_builder import build_pdf

    sources = collect_images(test_data_dir)
    assert [source.name for source in sources] == [f"{index}.jpg" for index in range(1, 11)]

    out = tmp_path / "test_data.pdf"
    build_pdf(sources, out)

    assert out.exists()
    assert out.stat().st_size > 0
    assert page_count(out) == 10

    for index, source in enumerate(sources):
        width, height = page_size(out, index)
        assert width == pytest.approx(A4_PORTRAIT[0], abs=0.5)
        assert height == pytest.approx(A4_PORTRAIT[1], abs=0.5)

        with Image.open(source) as image:
            expected = ImageOps.exif_transpose(image).copy()
        assert_similar(extract_page_image(out, index), expected)
