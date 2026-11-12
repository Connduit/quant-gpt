import logging
from datetime import date

import pytest

from quantlab.data.providers.base import DataRequest


@pytest.fixture(autouse=True)
def restore_logger():
    logger = logging.getLogger("quantlab")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    yield
    logger.handlers, logger.level, logger.propagate = handlers, level, propagate


@pytest.fixture
def request_range():
    return DataRequest("SYNTH", date(2024, 1, 2), date(2024, 1, 8))
