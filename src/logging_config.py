
import json
import logging
import os
import sys
import traceback

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + "".join(traceback.format_exception(*record.exc_info))
        entry = {
            "severity" : record.levelname,
            "message" : message,
            "logger" : record.name,
            "logging.googleapis.com/sourceLocation" : {
                "file" : record.pathname,
                "line" : record.lineno,
                "function" : record.funcName,
            },
        }

        rid = request_id_var.get()
        if rid:
            entry["request_id"] = rid

        return json.dumps(entry, default=str)

def setup_logging(level=logging.INFO):
    if os.getenv("K_SERVICE"):
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(levelname)s %(name)s: %(message)s")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its own handlers on these named loggers when the server
    # boots, and named loggers are not touched by the root config above — so
    # without this the log stream would be half JSON (our code) and half plain
    # text (uvicorn's access log). Dropping their handlers and letting them
    # propagate sends them through root instead, so everything gets one shape.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


