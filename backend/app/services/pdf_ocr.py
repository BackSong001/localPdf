from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pymupdf

from app.errors import AppError

try:
    from pdf2image import convert_from_path
except ImportError:  # pragma: no cover - exercised through the API error path
    convert_from_path = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - exercised through the API error path
    pytesseract = None


OCR_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
)


def _font() -> tuple[str, str | None]:
    for path in OCR_FONT_CANDIDATES:
        if path.exists():
            return "ocr_font", str(path)
    return "helv", None


def _require_ocr() -> None:
    if convert_from_path is None or pytesseract is None:
        raise AppError("OCR_NOT_CONFIGURED")


def add_pdf_text_layer(
    input_path: Path,
    output_path: Path,
    max_pages: int,
    dpi: int = 200,
    lang: str = "kor",
    on_progress: Callable[[int], None] | None = None,
) -> Path:
    """Copy a PDF while adding invisible Tesseract text at detected positions."""
    _require_ocr()

    try:
        document = pymupdf.open(str(input_path))
    except Exception as exc:
        raise AppError("INVALID_PDF") from exc

    try:
        if document.needs_pass or document.page_count == 0:
            raise AppError("INVALID_PDF")
        if document.page_count > max_pages:
            raise AppError("PDF_TOO_MANY_PAGES")

        font_name, font_file = _font()
        for page_number, page in enumerate(document, start=1):
            try:
                rendered = convert_from_path(
                    str(input_path),
                    dpi=dpi,
                    first_page=page_number,
                    last_page=page_number,
                    fmt="png",
                    thread_count=1,
                )
                if not rendered:
                    raise RuntimeError("PDF page rendering returned no image")
                image = rendered[0]
                data = pytesseract.image_to_data(
                    image,
                    lang=lang,
                    output_type=pytesseract.Output.DICT,
                )
            except AppError:
                raise
            except Exception as exc:
                if pytesseract is not None and isinstance(
                    exc, getattr(pytesseract, "TesseractNotFoundError", ())
                ):
                    raise AppError("OCR_NOT_CONFIGURED") from exc
                raise AppError("INVALID_PDF", "PDF OCR 처리에 실패했습니다.") from exc

            if font_file:
                page.insert_font(fontname=font_name, fontfile=font_file)
            x_scale = page.rect.width / image.width
            y_scale = page.rect.height / image.height

            for index, text in enumerate(data.get("text", [])):
                text = str(text).strip()
                if not text:
                    continue
                left = float(data["left"][index]) * x_scale
                top = float(data["top"][index]) * y_scale
                height = max(1.0, float(data["height"][index]) * y_scale)
                try:
                    page.insert_text(
                        pymupdf.Point(left, top + height),
                        text,
                        fontname=font_name,
                        fontfile=font_file,
                        fontsize=max(6.0, min(height * 0.85, 36.0)),
                        render_mode=3,
                    )
                except Exception:  # noqa: BLE001
                    page.insert_text(
                        pymupdf.Point(left, top + height),
                        text,
                        fontname="helv",
                        fontsize=max(6.0, min(height * 0.85, 36.0)),
                        render_mode=3,
                    )

            if on_progress is not None:
                on_progress(page_number)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(output_path))
    finally:
        document.close()

    return output_path
