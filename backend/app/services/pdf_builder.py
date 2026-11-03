from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import pymupdf

from app.services.images import prepare_image

logger = logging.getLogger(__name__)

A4_PORTRAIT = (595.276, 841.89)
A4_LANDSCAPE = (841.89, 595.276)

_ocr_engine = None

CANDIDATE_FONTS = (
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
)


def _get_font_path() -> Path | None:
    for candidate in CANDIDATE_FONTS:
        if candidate.exists():
            return candidate
    return None


def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RapidOCR 초기화 실패: %s", exc)
            _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None


def build_pdf(
    image_paths: Sequence[Path],
    output_path: Path,
    normalized_dir: Path | None = None,
    on_progress: Callable[[int], None] | None = None,
    ocr: bool = True,
    markdown_path: Path | None = None,
) -> Path:
    document = pymupdf.open()
    ocr_engine = get_ocr_engine() if ocr else None
    font_path = _get_font_path()
    font_name = "custom_font" if font_path else "helv"
    font_file_str = str(font_path) if font_path else None

    markdown_pages: list[str] = []

    try:
        for index, image_path in enumerate(image_paths, start=1):
            prepared = prepare_image(image_path)
            page_width, page_height = (
                A4_PORTRAIT
                if prepared.height >= prepared.width
                else A4_LANDSCAPE
            )
            scale = min(
                page_width / prepared.width,
                page_height / prepared.height,
            )
            draw_width = prepared.width * scale
            draw_height = prepared.height * scale
            x0 = (page_width - draw_width) / 2
            y0 = (page_height - draw_height) / 2

            if normalized_dir is not None and not prepared.direct:
                normalized_dir.mkdir(parents=True, exist_ok=True)
                normalized_path = (
                    normalized_dir / f"{index - 1:04d}.{prepared.extension}"
                )
                normalized_path.write_bytes(prepared.data)

            page = document.new_page(width=page_width, height=page_height)
            page.insert_image(
                pymupdf.Rect(x0, y0, x0 + draw_width, y0 + draw_height),
                stream=prepared.data,
                keep_proportion=True,
            )

            page_texts: list[str] = []
            if ocr_engine is not None:
                try:
                    ocr_results, _ = ocr_engine(str(image_path))
                    if ocr_results:
                        if font_file_str:
                            try:
                                page.insert_font(fontname=font_name, fontfile=font_file_str)
                            except Exception:  # noqa: BLE001, S110
                                pass

                        for item in ocr_results:
                            box = item[0]
                            text = str(item[1]).strip()
                            if not text:
                                continue
                            page_texts.append(text)

                            xs = [pt[0] for pt in box]
                            ys = [pt[1] for pt in box]
                            min_x = min(xs)
                            min_y, max_y = min(ys), max(ys)

                            pdf_x = x0 + (min_x * scale)
                            pdf_y = y0 + (max_y * scale)
                            box_height = max(1.0, (max_y - min_y) * scale)
                            font_size = max(6.0, min(box_height * 0.85, 36.0))

                            try:
                                page.insert_text(
                                    pymupdf.Point(pdf_x, pdf_y),
                                    text,
                                    fontname=font_name,
                                    fontfile=font_file_str,
                                    fontsize=font_size,
                                    render_mode=3,
                                )
                            except Exception:  # noqa: BLE001
                                try:
                                    page.insert_text(
                                        pymupdf.Point(pdf_x, pdf_y),
                                        text,
                                        fontname="helv",
                                        fontsize=font_size,
                                        render_mode=3,
                                    )
                                except Exception:  # noqa: BLE001, S110
                                    pass
                except Exception as exc:  # noqa: BLE001
                    logger.warning("OCR 처리 중 오류 (페이지 %d): %s", index, exc)

            markdown_pages.append(f"## Page {index}\n\n" + ("\n".join(page_texts) if page_texts else "_텍스트 없음_"))

            if on_progress is not None:
                on_progress(index)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(output_path))

        if markdown_path is not None:
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text("\n\n".join(markdown_pages), encoding="utf-8")

    finally:
        document.close()

    return output_path
