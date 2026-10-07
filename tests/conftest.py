"""Shared fixtures.

Logging is global mutable state: `setup_logging()` clears root's handlers, which
would tear down pytest's own log capture and leak into unrelated tests. Anything
that touches logging config takes `restore_logging`.
"""

import io
import json
import logging

import pytest

from src.logging_config import JsonFormatter

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture
def restore_logging():
    """Snapshot and restore global logging state around a test."""
    root = logging.getLogger()
    saved_root = (root.handlers[:], root.level)
    saved_uvicorn = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in UVICORN_LOGGERS
    }

    yield

    root.handlers[:] = saved_root[0]
    root.setLevel(saved_root[1])
    for name, (handlers, propagate) in saved_uvicorn.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.propagate = propagate


@pytest.fixture
def json_logs(restore_logging):
    """Capture log output as parsed JSON entries.

    Installs a real JsonFormatter over a StringIO, so these tests exercise the
    actual formatter rather than a stand-in. Returns a callable that parses
    whatever has been logged so far.
    """
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)

    def entries():
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]

    return entries
