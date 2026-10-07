"""Tests for src.logging_config — the JSON formatter and logging setup.

The formatter is a pure function of a LogRecord, so most of these build a record
by hand and assert on the parsed JSON. No server, no mocking.

`setup_logging` mutates global logging state, so every test that calls it uses the
`restore_logging` fixture — without it, clearing root's handlers would tear down
pytest's own log capture and leak into unrelated tests.
"""

import json
import logging
import sys

import pytest

from src.logging_config import JsonFormatter, setup_logging

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


def make_record(msg="hello %s", args=("world",), level=logging.INFO, exc_info=None):
    """Build a LogRecord the way logging itself would."""
    return logging.LogRecord(
        name="api.main",
        level=level,
        pathname="/app/api/main.py",
        lineno=42,
        msg=msg,
        args=args,
        exc_info=exc_info,
        func="save_predictions",
    )


def format_record(record) -> dict:
    return json.loads(JsonFormatter().format(record))


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------

def test_severity_and_message():
    entry = format_record(make_record())

    # Python's levelname values are already valid Cloud Logging severities, so
    # this is a passthrough rather than a lookup table.
    assert entry["severity"] == "INFO"
    # getMessage() must have done the %-substitution — record.msg would have
    # left the raw "hello %s" template here.
    assert entry["message"] == "hello world"
    assert entry["logger"] == "api.main"


def test_source_location_key_is_spelled_exactly():
    # This key is only useful because Cloud Logging treats it as special. A typo
    # degrades it to an ordinary field with NO error at all, so the exact string
    # is pinned here on purpose.
    entry = format_record(make_record())

    assert "logging.googleapis.com/sourceLocation" in entry
    assert entry["logging.googleapis.com/sourceLocation"] == {
        "file": "/app/api/main.py",
        "line": 42,
        "function": "save_predictions",
    }


def test_output_is_a_single_line():
    # One line == one Cloud Logging entry. The invariant that silently breaks
    # everything if violated: a literal newline splits one event into two
    # unrelated entries.
    formatted = JsonFormatter().format(make_record())

    assert "\n" not in formatted


def test_exception_traceback_goes_into_the_message():
    try:
        raise ZeroDivisionError("division by zero")
    except ZeroDivisionError:
        record = make_record(
            msg="Failed to save predictions to Firestore",
            args=(),
            level=logging.ERROR,
            exc_info=sys.exc_info(),
        )

    entry = format_record(record)

    assert entry["severity"] == "ERROR"
    # The traceback must live INSIDE message, not in a sibling key: Error
    # Reporting finds crashes by locating a stack trace in the message field.
    assert "Traceback (most recent call last)" in entry["message"]
    assert "ZeroDivisionError: division by zero" in entry["message"]
    assert entry["message"].startswith("Failed to save predictions to Firestore")


def test_exception_entry_is_still_one_line():
    # A traceback is inherently multi-line; json.dumps has to escape it. This is
    # the case where the single-line rule is actually at risk.
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record(msg="exploded", args=(), level=logging.ERROR,
                             exc_info=sys.exc_info())

    formatted = JsonFormatter().format(record)

    assert "\n" not in formatted
    assert "\\n" in formatted  # escaped, not stripped
    assert "Traceback" in json.loads(formatted)["message"]


def test_unserializable_values_do_not_raise():
    # default=str is a safety net: a formatter that throws loses logs exactly
    # when something is already going wrong.
    class Opaque:
        def __repr__(self):
            return "<opaque>"

    entry = format_record(make_record(msg="got %s", args=(Opaque(),)))

    assert entry["message"] == "got <opaque>"


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

def test_json_formatter_used_when_running_on_cloud_run(monkeypatch, restore_logging):
    # Cloud Run always sets K_SERVICE; its presence is the production signal.
    monkeypatch.setenv("K_SERVICE", "allsvensk-pred")

    setup_logging()

    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)


def test_plain_formatter_used_locally(monkeypatch, restore_logging):
    monkeypatch.delenv("K_SERVICE", raising=False)

    setup_logging()

    handler = logging.getLogger().handlers[0]
    assert not isinstance(handler.formatter, JsonFormatter)


def test_logs_go_to_stdout(monkeypatch, restore_logging):
    # stdout, not stderr: Cloud Run infers ERROR severity from stderr, which
    # would fight the explicit severity field.
    monkeypatch.setenv("K_SERVICE", "allsvensk-pred")

    setup_logging()

    assert logging.getLogger().handlers[0].stream is sys.stdout


def test_level_defaults_to_info(restore_logging):
    setup_logging()

    assert logging.getLogger().level == logging.INFO


def test_calling_setup_twice_does_not_duplicate_handlers(restore_logging):
    # Each call adding a handler would mean every line printed twice, then three
    # times. The handlers.clear() in setup_logging is what prevents it.
    setup_logging()
    setup_logging()

    assert len(logging.getLogger().handlers) == 1


def test_uvicorn_loggers_are_taken_over(restore_logging):
    # uvicorn attaches its own handlers to these named loggers at boot. Named
    # loggers are untouched by root config, so without this the stream would be
    # half JSON (our code) and half plain text (uvicorn's access log).
    for name in UVICORN_LOGGERS:
        logging.getLogger(name).addHandler(logging.StreamHandler())

    setup_logging()

    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.handlers == [], f"{name} kept its own handler"
        assert logger.propagate is True, f"{name} will not reach root"
