import logging
import os
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO, Callable, Optional

from colorama import Fore, Style
import fitz

from ..conversion import errors
from ..conversion.common import INT_BYTES, DEFAULT_DPI
from ..document import Document
from ..util import replace_control_chars, get_tessdata_dir

log = logging.getLogger(__name__)

MAX_CONVERSION_LOG_CHARS = 150 * 50  # up to ~150 lines of 50 characters
DOC_TO_PIXELS_LOG_START = "----- DOC TO PIXELS LOG START -----"
DOC_TO_PIXELS_LOG_END = "----- DOC TO PIXELS LOG END -----"
PIXELS_TO_PDF_LOG_START = "----- PIXELS TO PDF LOG START -----"
PIXELS_TO_PDF_LOG_END = "----- PIXELS TO PDF LOG END -----"


def read_bytes(f: IO[bytes], size: int, exact: bool = True) -> bytes:
    """Read bytes from a file-like object."""
    buf = f.read(size)
    if exact and len(buf) != size:
        raise errors.ConverterProcException()
    return buf


def read_int(f: IO[bytes]) -> int:
    """Read 2 bytes from a file-like object, and decode them as int."""
    untrusted_int = f.read(INT_BYTES)
    if len(untrusted_int) != INT_BYTES:
        raise errors.ConverterProcException()
    return int.from_bytes(untrusted_int, "big", signed=False)


def read_debug_text(f: IO[bytes], size: int) -> str:
    """Read arbitrarily long text (for debug purposes)"""
    untrusted_text = f.read(size).decode("ascii", errors="replace")
    return replace_control_chars(untrusted_text)


class IsolationProvider(ABC):
    """
    Abstracts an isolation provider
    """

    def __init__(self) -> None:
        if getattr(sys, "dangerzone_dev", False) == True:
            self.proc_stderr = subprocess.PIPE
        else:
            self.proc_stderr = subprocess.DEVNULL

    @abstractmethod
    def install(self) -> bool:
        pass

    def convert(
        self,
        document: Document,
        ocr_lang: Optional[str],
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.progress_callback = progress_callback
        document.mark_as_converting()
        try:
            conversion_proc = self.start_doc_to_pixels_proc()
            with tempfile.TemporaryDirectory() as t:
                Path(f"{t}/pixels").mkdir()
                try:
                    self._convert(document, t, ocr_lang, conversion_proc)
                finally:
                    if getattr(sys, "dangerzone_dev", False):
                        assert conversion_proc.stderr
                        try:
                            conversion_proc.wait(3)
                        except subprocess.TimeoutExpired:
                            log.debug("Conversion command is still running")
                            raise

                        untrusted_log = read_debug_text(conversion_proc.stderr, MAX_CONVERSION_LOG_CHARS)
                        conversion_proc.stderr.close()
                        log.info(
                            f"Conversion output (doc to pixels)\n{self.sanitize_conversion_str(untrusted_log)}"
                        )
            document.mark_as_safe()
            if document.archive_after_conversion:
                document.archive()
        except errors.ConverterProcException as e:
            exception = self.get_proc_exception(conversion_proc)
            self.print_progress(document, True, str(exception), 0)
            document.mark_as_failed()
        except errors.ConversionException as e:
            self.print_progress(document, True, str(e), 0)
            document.mark_as_failed()
        except Exception as e:
            log.exception(
                f"An exception occurred while converting document '{document.id}'"
            )
            self.print_progress(document, True, str(e), 0)
            document.mark_as_failed()

    def _pixels_to_pdf(
        self,
        untrusted_data: bytes,
        untrusted_width: int,
        untrusted_height: int,
        ocr_lang: Optional[str],
    ) -> None:
        """Convert a byte array of RGB pixels into a PDF page, optionally with OCR."""
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

        return fitz.open("pdf", page_pdf_bytes)

    def _convert(
        self,
        document: Document,
        tempdir: str,
        ocr_lang: Optional[str],
        p: subprocess.Popen,
    ) -> None:
        percentage = 0.0
        with open(document.input_filename, "rb") as f:
            try:
                assert p.stdin is not None
                p.stdin.write(f.read())
                p.stdin.close()
            except BrokenPipeError as e:
                raise errors.ConverterProcException()

            assert p.stdout
            n_pages = read_int(p.stdout)
            if n_pages == 0 or n_pages > errors.MAX_PAGES:
                raise errors.MaxPagesException()
            step = 100 / n_pages / 2

            safe_doc = fitz.Document()

            for page in range(1, n_pages + 1):
                text = f"Converting page {page}/{n_pages} to pixels"
                percentage += step
                self.print_progress(document, False, text, percentage)

                width = read_int(p.stdout)
                height = read_int(p.stdout)
                if not (1 <= width <= errors.MAX_PAGE_WIDTH):
                    raise errors.MaxPageWidthException()
                if not (1 <= height <= errors.MAX_PAGE_HEIGHT):
                    raise errors.MaxPageHeightException()

                num_pixels = width * height * 3  # three color channels
                untrusted_pixels = read_bytes(
                    p.stdout,
                    num_pixels,
                )

                if ocr_lang:
                    text = (
                        f"Converting page {page}/{n_pages} from pixels to"
                        " searchable PDF"
                    )
                else:
                    text = f"Converting page {page}/{n_pages} from pixels to PDF"
                percentage += step
                self.print_progress(document, False, text, percentage)

                page_pdf = self._pixels_to_pdf(
                    untrusted_pixels,
                    width,
                    height,
                    ocr_lang,
                )
                safe_doc.insert_pdf(page_pdf)

        # Ensure nothing else is read after all bitmaps are obtained
        p.stdout.close()

        safe_doc.save(document.output_filename)

        # TODO handle leftover code input
        text = "Converted document"
        self.print_progress(document, False, text, percentage)

    def print_progress(
        self, document: Document, error: bool, text: str, percentage: float
    ) -> None:
        s = Style.BRIGHT + Fore.YELLOW + f"[doc {document.id}] "
        s += Fore.CYAN + f"{int(percentage)}% " + Style.RESET_ALL
        if error:
            s += Fore.RED + text + Style.RESET_ALL
            log.error(s)
        else:
            s += text
            log.info(s)

        if self.progress_callback:
            self.progress_callback(error, text, percentage)

    def get_proc_exception(self, p: subprocess.Popen) -> Exception:
        """Returns an exception associated with a process exit code"""
        error_code = p.wait(3)
        return errors.exception_from_error_code(error_code)

    @abstractmethod
    def get_max_parallel_conversions(self) -> int:
        pass

    def sanitize_conversion_str(self, untrusted_conversion_str: str) -> str:
        conversion_string = replace_control_chars(untrusted_conversion_str)

        # Add armor (gpg-style)
        armor_start = f"{DOC_TO_PIXELS_LOG_START}\n"
        armor_end = DOC_TO_PIXELS_LOG_END
        return armor_start + conversion_string + armor_end

    @abstractmethod
    def start_doc_to_pixels_proc(self) -> subprocess.Popen:
        pass
