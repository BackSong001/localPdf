from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from app.errors import AppError

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}
JPEG_SOURCE_FORMATS = {"JPEG", "WEBP"}
EXIF_ORIENTATION = 274


@dataclass(frozen=True, slots=True)
class PreparedImage:
    width: int
    height: int
    data: bytes
    extension: str
    direct: bool


def _natural_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.name)
    ]


def natural_sort_paths(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=_natural_key)


def collect_images(directory: Path) -> list[Path]:
    return natural_sort_paths(
        path
        for path in Path(directory).iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    )


def validate_image_file(path: Path) -> None:
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise AppError(
            "UNSUPPORTED_IMAGE",
            f"지원하지 않는 이미지 형식입니다: {path.name}",
        )
    try:
        with Image.open(path) as image:
            image.load()
            if image.format not in SUPPORTED_IMAGE_FORMATS:
                raise AppError(
                    "UNSUPPORTED_IMAGE",
                    f"지원하지 않는 이미지 형식입니다: {path.name}",
                )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "INVALID_IMAGE",
            f"이미지 파일이 손상되었거나 읽을 수 없습니다: {path.name}",
        ) from exc


def normalize_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        transposed = ImageOps.exif_transpose(image)
        if transposed.mode in ("RGBA", "LA") or (
            transposed.mode == "P" and "transparency" in transposed.info
        ):
            rgba = transposed.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            transposed = Image.alpha_composite(background, rgba)
        return transposed.convert("RGB")


def prepare_image(path: Path) -> PreparedImage:
    with Image.open(path) as image:
        orientation = image.getexif().get(EXIF_ORIENTATION, 1)
        if image.format == "JPEG" and image.mode == "RGB" and orientation in (None, 1):
            return PreparedImage(
                width=image.width,
                height=image.height,
                data=path.read_bytes(),
                extension="jpg",
                direct=True,
            )

        source_format = image.format
        transposed = ImageOps.exif_transpose(image)
        if transposed.mode in ("RGBA", "LA") or (
            transposed.mode == "P" and "transparency" in transposed.info
        ):
            rgba = transposed.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            transposed = Image.alpha_composite(background, rgba)

        rgb = transposed.convert("RGB")
        buffer = io.BytesIO()
        if source_format in JPEG_SOURCE_FORMATS:
            rgb.save(buffer, format="JPEG", quality=90)
            extension = "jpg"
        else:
            rgb.save(buffer, format="PNG")
            extension = "png"

        return PreparedImage(
            width=rgb.width,
            height=rgb.height,
            data=buffer.getvalue(),
            extension=extension,
            direct=False,
        )
