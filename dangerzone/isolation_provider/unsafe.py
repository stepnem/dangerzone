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
        dev_mode = getattr(sys, "dangerzone_dev", False) == True
        if dev_mode:
            # Use dz.ConvertDev RPC call instead, if we are in development mode.
            # Basically, the change is that we also transfer the necessary Python
            # code as a zipfile, before sending the doc that the user requested.
            qrexec_policy = "dz.ConvertDev"
            stderr = subprocess.PIPE
        else:
            qrexec_policy = "dz.Convert"
            stderr = subprocess.DEVNULL

        p = subprocess.Popen(
            # XXX The unsafe converter bypasses the isolation provider by calling
            # the Qubes server component directly
            [Path(__file__).parent.parent.parent / "qubes" / qrexec_policy],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
        )

        if dev_mode:
            assert p.stdin is not None
            # Send the dangerzone module first.
            self.teleport_dz_module(p.stdin)

        return p

    def get_max_parallel_conversions(self) -> int:
        return 1
