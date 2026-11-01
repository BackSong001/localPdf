from pathlib import Path

from tests.helpers import center_pixel, extract_page_image, page_count, save_solid_png


def test_tc_fr_002_a_natural_sort() -> None:
    from app.services.images import natural_sort_paths

    paths = [Path("img10.jpg"), Path("img2.jpg"), Path("img1.jpg")]

    assert natural_sort_paths(paths) == [
        Path("img1.jpg"),
        Path("img2.jpg"),
        Path("img10.jpg"),
    ]


def test_tc_fr_002_b_order_preserved(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    paths = [
        save_solid_png(tmp_path / f"{index}.png", color=color)
        for index, color in enumerate(colors)
    ]
    out = tmp_path / "out.pdf"

    build_pdf(paths, out)

    assert page_count(out) == 3
    for index, expected in enumerate(colors):
        actual = center_pixel(extract_page_image(out, index))
        assert all(abs(actual[channel] - expected[channel]) <= 8 for channel in range(3)), (
            index,
            actual,
            expected,
        )


def test_tc_fr_002_c_duplicate_filenames_preserve_input_order(tmp_path: Path) -> None:
    from app.services.pdf_builder import build_pdf

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = save_solid_png(first_dir / "same.png", color=(255, 0, 0))
    second = save_solid_png(second_dir / "same.png", color=(0, 0, 255))
    out = tmp_path / "out.pdf"

    build_pdf([first, second], out)

    assert page_count(out) == 2
    assert center_pixel(extract_page_image(out, 0))[0] > 200
    assert center_pixel(extract_page_image(out, 1))[2] > 200
