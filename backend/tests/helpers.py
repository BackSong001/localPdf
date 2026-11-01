import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw

A4_PORTRAIT = (595.276, 841.89)
A4_LANDSCAPE = (841.89, 595.276)


def save_solid_png(path: Path, size: tuple[int, int] = (100, 100), color=(255, 0, 0)) -> Path:
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def save_exif_jpeg(
    path: Path,
    size: tuple[int, int] = (100, 200),
    top_color=(255, 0, 0),
    bottom_color=(0, 0, 255),
    orientation: int = 6,
) -> Path:
    image = Image.new("RGB", size, top_color)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, size[1] // 2, size[0], size[1]], fill=bottom_color)
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, format="JPEG", exif=exif, quality=95)
    return path


def save_alpha_png(
    path: Path,
    size: tuple[int, int] = (100, 100),
    background=(0, 0, 0, 0),
    fill=(255, 0, 0, 255),
    box: tuple[int, int, int, int] = (25, 25, 75, 75),
) -> Path:
    image = Image.new("RGBA", size, background)
    ImageDraw.Draw(image).rectangle(box, fill=fill)
    image.save(path, format="PNG")
    return path


def save_palette_transparency_png(
    path: Path,
    size: tuple[int, int] = (100, 100),
    box: tuple[int, int, int, int] = (25, 25, 75, 75),
) -> Path:
    image = Image.new("P", size, 0)
    palette = [255, 255, 255, 255, 0, 0] + [0, 0, 0] * 254
    image.putpalette(palette)
    image.paste(1, box)
    image.save(path, format="PNG", transparency=0)
    return path


def page_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def page_size(pdf_path: Path, page_index: int = 0) -> tuple[float, float]:
    with fitz.open(pdf_path) as doc:
        rect = doc[page_index].rect
        return rect.width, rect.height


def page_image_rect(pdf_path: Path, page_index: int = 0) -> fitz.Rect:
    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        images = page.get_images(full=True)
        assert images, f"page {page_index} contains no image"
        xref = max(images, key=lambda info: info[2] * info[3])[0]
        rects = page.get_image_rects(xref)
        assert rects, f"page {page_index} image has no placement rect"
        return rects[0]


def extract_page_image(pdf_path: Path, page_index: int = 0) -> Image.Image:
    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        images = page.get_images(full=True)
        assert images, f"page {page_index} contains no image"
        xref = max(images, key=lambda info: info[2] * info[3])[0]
        data = doc.extract_image(xref)
        return Image.open(io.BytesIO(data["image"])).copy()


def center_pixel(image: Image.Image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    return rgb.getpixel((rgb.width // 2, rgb.height // 2))


def fingerprint(image: Image.Image, size: tuple[int, int] = (32, 32)) -> list[int]:
    rgb = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    return list(rgb.tobytes())


def assert_similar(actual: Image.Image, expected: Image.Image, tolerance: float = 25.0) -> None:
    actual_fp = fingerprint(actual)
    expected_fp = fingerprint(expected)
    diff = sum(abs(a - b) for a, b in zip(actual_fp, expected_fp)) / len(actual_fp)
    assert diff <= tolerance, f"images differ: mean abs diff {diff:.2f} > {tolerance}"
