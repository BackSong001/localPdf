from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pymupdf

from app.services.images import prepare_image

A4_PORTRAIT = (595.276, 841.89)
A4_LANDSCAPE = (841.89, 595.276)


def build_pdf(
    image_paths: Sequence[Path],
    output_path: Path,
    normalized_dir: Path | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Path:
    document = pymupdf.open()
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
            if on_progress is not None:
                on_progress(index)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(output_path))
    finally:
        document.close()

    return output_path
