import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from ..document import Document
from ..util import get_resource_path
from .qubes import Qubes

log = logging.getLogger(__name__)


class UnsafeConverter(Qubes):
    """Unsafe Isolation Provider (FOR TESTING ONLY)

    Unsafe converter - files are sanitized without any isolation
    """

    def __init__(self) -> None:
        super().__init__()
        # Sanity check
        if not getattr(sys, "dangerzone_dev", False):
            raise Exception(
                'The "Unsafe" isolation provider is UNSAFE as the name implies'
                + " and should never be called in a non-testing system."
            )

    def install(self) -> bool:
        return True

    def start_doc_to_pixels_proc(self) -> subprocess.Popen:
        return subprocess.Popen(
            # XXX The unsafe converter bypasses the isolation provider by calling
            # the Qubes server component directly
            [Path(__file__).parent.parent.parent / "qubes" / "dz.Convert"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def get_max_parallel_conversions(self) -> int:
        return 1
