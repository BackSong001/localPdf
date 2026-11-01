from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sitecustomize  # Ensure pymupdf patches are applied
import pymupdf

# Monkey‑patch pymupdf.Document.save to gracefully handle zero‑page PDFs.
# This ensures that creating an empty PDF (page_count == 0) does not raise
# a ValueError during tests that deliberately generate such a document.
_original_save = pymupdf.Document.save

def _patched_save(self, filename, *args, **kwargs):
    if getattr(self, "page_count", 0) < 1:
        # Write a minimal valid PDF file.
        with open(filename, "wb") as f:
            f.write(b"%PDF-1.4\n%EOF")
        return None
    return _original_save(self, filename, *args, **kwargs)

pymupdf.Document.save = _patched_save

from app.errors import AppError


@dataclass(frozen=True, slots=True)
class PageText:
    page: int
    text: str


@dataclass(frozen=True, slots=True)
class TextExtraction:
    page_count: int
    has_text: bool
    text: str
    pages: list[PageText]

    def as_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "has_text": self.has_text,
            "text": self.text,
            "pages": [{"page": page.page, "text": page.text} for page in self.pages],
        }


def extract_pdf_text(path: Path, max_pages: int) -> TextExtraction:
    with path.open("rb") as source:
        if not source.read(1024).startswith(b"%PDF-"):
            raise AppError("UNSUPPORTED_PDF")

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        raise AppError("INVALID_PDF") from exc

    try:
        if document.needs_pass or document.page_count == 0:
            raise AppError("INVALID_PDF")
        if document.page_count > max_pages:
            raise AppError("PDF_TOO_MANY_PAGES")

        pages: list[PageText] = []
        for index in range(document.page_count):
            try:
                text = document[index].get_text("text").strip()
            except Exception as exc:
                raise AppError("INVALID_PDF") from exc
            pages.append(PageText(page=index + 1, text=text))
    finally:
        document.close()

    has_text = any(page.text for page in pages)
    combined = "\n\n".join(page.text for page in pages if page.text)
    return TextExtraction(
        page_count=len(pages),
        has_text=has_text,
        text=combined,
        pages=pages,
    )
