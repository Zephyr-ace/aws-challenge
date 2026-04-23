"""find_areas – Identify potential data center sites in German industrial areas."""

import logging

logger = logging.getLogger("find_areas")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.DEBUG)
    _formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)

from find_areas.pipeline import find_areas  # noqa: E402
