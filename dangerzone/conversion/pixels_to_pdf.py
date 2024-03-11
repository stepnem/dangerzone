#!/usr/bin/env python3
"""
Here are the steps, with progress bar percentages:

- 50%-95%: Convert each page of pixels into a PDF (each page takes 45/n%, where n is the number of pages)
- 95%-100%: Compress the final PDF
"""
import fitz
from typing import Optional

from .common import DEFAULT_DPI, DangerzoneConverter, get_tessdata_dir, running_on_qubes


class PixelsToPDF(DangerzoneConverter):
    def convert_start(self):
        self.safe_doc = fitz.Document()

    def convert_finalize(self, safe_pdf_path: str):
        self.safe_doc.save(safe_pdf_path)

    def convert_next_page(
        self,
        untrusted_data: bytes,
        untrusted_width: int,
        untrusted_height: int,
        ocr_lang: Optional[str],
    ) -> None:
        pixmap = fitz.Pixmap(
            fitz.Colorspace(fitz.CS_RGB),
            untrusted_width,
            untrusted_height,
            untrusted_data,
            False,
        )
        pixmap.set_dpi(DEFAULT_DPI, DEFAULT_DPI)

        if ocr_lang:  # OCR the document
            page_pdf_bytes = pixmap.pdfocr_tobytes(
                compress=True,
                language=ocr_lang,
                tessdata=get_tessdata_dir(),
            )
        else:  # Don't OCR
            page_doc = fitz.Document()
            page_doc.insert_file(pixmap)
            page_pdf_bytes = page_doc.tobytes(deflate_images=True)

        page_pdf = fitz.open("pdf", page_pdf_bytes)
        self.safe_doc.insert_pdf(page_pdf)
