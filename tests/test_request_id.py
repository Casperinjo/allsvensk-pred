"""Tests for the request-ID correlation channel.

Three layers:
  * the middleware    — derives an ID and returns it as a header
  * the ContextVar    — carries it from middleware to formatter, per async task
  * the whole chain   — a log line emitted deep inside an endpoint carries the
                        same ID the caller got back
"""

import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient

import api.main as main
from src.logging_config import JsonFormatter, request_id_var

client = TestClient(main.app)

TRACE_HEADER = "X-Cloud-Trace-Context"


# ---------------------------------------------------------------------------
# Middleware: deriving the ID
# ---------------------------------------------------------------------------

def test_response_carries_a_request_id():
    resp = client.get("/health")

    assert resp.headers["X-Request-ID"]


def test_cloud_run_trace_header_is_reused():
    # Cloud Run sends "TRACE_ID/SPAN_ID;o=1". Reusing the trace ID (rather than
    # minting our own) is what lets these logs join Cloud Run's own request log.
    resp = client.get("/health", headers={TRACE_HEADER: "105445aa7843bc8bf2/1;o=1"})

    assert resp.headers["X-Request-ID"] == "105445aa7843bc8bf2"


def test_id_is_generated_when_header_is_absent():
    # Locally and in tests there is no Cloud Run front end, so the fallback is
    # what runs almost everywhere except production.
    resp = client.get("/health")
    rid = resp.headers["X-Request-ID"]

    assert len(rid) == 32
    int(rid, 16)  # uuid4().hex is valid hex; raises ValueError if not


def test_empty_trace_header_falls_back_to_a_generated_id():
    # "" is falsy, so the `if raw` guard must treat it like a missing header.
    # Without that, the request ID would be "" — set, but matching no filter.
    resp = client.get("/health", headers={TRACE_HEADER: ""})

    assert len(resp.headers["X-Request-ID"]) == 32


def test_trace_header_without_a_slash_is_used_whole():
    resp = client.get("/health", headers={TRACE_HEADER: "no-slash-here"})

    assert resp.headers["X-Request-ID"] == "no-slash-here"


def test_client_supplied_id_is_length_capped():
    # That header is attacker-controlled and gets stamped onto every log line of
    # the request, so its length must not be.
    resp = client.get("/health", headers={TRACE_HEADER: "a" * 500})

    assert len(resp.headers["X-Request-ID"]) == 64


def test_each_request_gets_a_distinct_id():
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]

    assert first != second


# ---------------------------------------------------------------------------
# Formatter: reading the ContextVar
# ---------------------------------------------------------------------------

def format_record(msg="hello"):
    record = logging.LogRecord("api.main", logging.INFO, "/app/api/main.py", 1,
                               msg, (), None, func="f")
    return json.loads(JsonFormatter().format(record))


def test_formatter_includes_request_id_when_set():
    # Regression test for a real bug: `if ird:` instead of `if rid:`. Every other
    # test formats records with NO request ID set, so the guard short-circuits
    # and the typo'd branch never runs — 37 tests passed over a dead formatter.
    token = request_id_var.set("abc-123")
    try:
        assert format_record()["request_id"] == "abc-123"
    finally:
        request_id_var.reset(token)


def test_formatter_omits_request_id_outside_a_request():
    # Startup and shutdown logs have no request. Emitting `"request_id": null`
    # would make every filter on that field match them.
    assert request_id_var.get() is None
    assert "request_id" not in format_record()


# ---------------------------------------------------------------------------
# ContextVar isolation — the property threading.local cannot provide
# ---------------------------------------------------------------------------

def test_concurrent_tasks_do_not_share_a_request_id():
    """Two overlapping requests must not see each other's ID.

    This is the test that would catch a threading.local regression: it passes
    trivially with one request at a time, and fails only under interleaving.
    """
    seen = []

    async def handle(rid, delay):
        token = request_id_var.set(rid)
        try:
            await asyncio.sleep(delay)      # force a suspension point
            seen.append((rid, request_id_var.get()))
        finally:
            request_id_var.reset(token)

    async def main_():
        # Deliberately staggered so the second finishes first.
        await asyncio.gather(handle("aaa", 0.02), handle("bbb", 0.01))

    asyncio.run(main_())

    assert sorted(seen) == [("aaa", "aaa"), ("bbb", "bbb")]


def test_context_is_reset_after_a_request():
    # The finally/reset in the middleware: without it the last request's ID
    # would leak onto subsequent startup or background log lines.
    client.get("/health", headers={TRACE_HEADER: "leaky/1"})

    assert request_id_var.get() is None


# ---------------------------------------------------------------------------
# The whole chain
# ---------------------------------------------------------------------------

def test_log_line_from_inside_an_endpoint_carries_the_callers_id(monkeypatch, json_logs):
    """The point of the whole feature.

    `logger.exception` lives inside api.main's save-failure handler, several
    frames below the middleware and with no access to the request object. It
    must still emit the ID the caller was handed.
    """
    monkeypatch.setattr(main, "fetch_upcoming_fixtures", lambda: [
        {"home": "A", "away": "B", "date": "2026-09-20", "time": "15:00:00", "id": "999"},
    ])
    monkeypatch.setattr(main, "predict_fixtures", lambda pairs: [
        {"home_team": "A", "away_team": "B", "home_win": 0.5, "draw": 0.3, "away_win": 0.2},
    ])

    def boom(preds):
        raise RuntimeError("Firestore is down")
    monkeypatch.setattr(main, "save_predictions", boom)

    resp = client.get("/upcoming-round", headers={TRACE_HEADER: "trace-xyz-42/1;o=1"})

    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "trace-xyz-42"

    errors = [e for e in json_logs() if e["severity"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["request_id"] == "trace-xyz-42"
    assert "Firestore is down" in errors[0]["message"]


# ---------------------------------------------------------------------------
# Unhandled errors — the case where the ID matters most
# ---------------------------------------------------------------------------

def _stub_scoring(monkeypatch):
    """Keep /track-record off the network; it scores on view."""
    monkeypatch.setattr(main, "fetch_recent_results", lambda: [])
    monkeypatch.setattr(main, "score_predictions", lambda results: None)


def _exploding_load(monkeypatch, message="database is on fire"):
    """load_predictions is NOT wrapped in a try/except by the endpoint, so this
    raises for real — a genuinely unhandled error, not a caught one."""
    def boom():
        raise RuntimeError(message)
    monkeypatch.setattr(main, "load_predictions", boom)


def test_unhandled_error_reports_the_id_in_header_and_body(monkeypatch):
    # Without this, a 500 is the one response a user cannot report usefully:
    # the middleware's post-await line never runs when an exception escapes.
    _stub_scoring(monkeypatch)
    _exploding_load(monkeypatch)

    resp = client.get("/track-record", headers={TRACE_HEADER: "err-trace-7/1;o=1"})

    assert resp.status_code == 500
    assert resp.headers["X-Request-ID"] == "err-trace-7"
    assert resp.json()["request_id"] == "err-trace-7"


def test_unhandled_error_does_not_leak_the_exception_message(monkeypatch):
    # Exception text routinely contains paths, SQL and credentials. It belongs in
    # the logs, not in a response body.
    _stub_scoring(monkeypatch)
    _exploding_load(monkeypatch, "connect failed: postgres://user:hunter2@db")

    resp = client.get("/track-record")

    assert "postgres://" not in resp.text
    assert "hunter2" not in resp.text
    assert resp.json()["detail"] == "Internal server error"


def test_unhandled_error_is_logged_with_the_request_id(monkeypatch, json_logs):
    # The pairing that makes a bug report actionable: the user quotes the ID from
    # their 500, and that ID appears on the log line holding the real traceback.
    _stub_scoring(monkeypatch)
    _exploding_load(monkeypatch)

    client.get("/track-record", headers={TRACE_HEADER: "err-trace-9/1;o=1"})

    errors = [e for e in json_logs() if e["severity"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["request_id"] == "err-trace-9"
    assert "database is on fire" in errors[0]["message"]
    assert "Traceback" in errors[0]["message"]


def test_context_is_reset_even_when_the_request_fails(monkeypatch):
    # The reset lives in `finally`, so an exception must not leave the ID stuck
    # and bleeding onto later log lines.
    _stub_scoring(monkeypatch)
    _exploding_load(monkeypatch)

    client.get("/track-record", headers={TRACE_HEADER: "sticky/1"})

    assert request_id_var.get() is None
