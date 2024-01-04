import itertools
import json
from typing import Any, Dict

import pytest
from pytest_mock import MockerFixture

from dangerzone.document import Document
from dangerzone.isolation_provider.container import Container

# XXX Fixtures used in abstract Test class need to be imported regardless
from .. import pdf_11k_pages, sanitized_text, uncommon_text
from .base import IsolationProviderTest


@pytest.fixture
def provider() -> Container:
    return Container(enable_timeouts=False)


class TestContainer(IsolationProviderTest):
    pass
