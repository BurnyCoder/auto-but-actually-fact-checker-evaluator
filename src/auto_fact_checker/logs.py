"""Timestamped logging to a per-process log file and the terminal, plus optional per-run log files.

Local: configures the "afc" logger hierarchy once (file + stdout handlers, UTF-8, millisecond timestamps) and
provides log_block() for full, never-truncated prompt/output dumps.
Global context: every module logs through logging.getLogger("afc.<module>"); RunContext (context.py) attaches a
per-run file (runs/<id>/run.log) that the Gradio UI tails to show a live log. Python logging docs:
https://docs.python.org/3/library/logging.html and the cookbook on filters/contextual info:
https://docs.python.org/3/howto/logging-cookbook.html#using-filters-to-impart-contextual-information
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT_LOGGER = "afc"  # every project logger is a child: afc.pipeline, afc.backends.openai_api, ...
FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s"  # e.g. 2026-10-17 13:05:01.123 | INFO
DATEFMT = "%Y-%m-%d %H:%M:%S"
_state: dict[str, Path] = {}  # remembers the current process log file so setup is idempotent


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> Path:
    """Create logs_dir/<YYYYmmdd_HHMMSS>.log and log to it and to stdout; calling again reuses the same file
    unless a different directory is requested (tests use temporary directories)."""
    if _state.get("dir") == logs_dir:
        return _state["file"]
    logger = logging.getLogger(ROOT_LOGGER)
    for h in list(logger.handlers):  # replace handlers from a previous setup (e.g. another logs_dir)
        logger.removeHandler(h)
        h.close()
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter(FORMAT, DATEFMT)
    file_handler = logging.FileHandler(path, encoding="utf-8")  # UTF-8 so names like "Ramón y Cajal" survive
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    stream_handler = logging.StreamHandler(sys.stdout)  # realtime terminal output
    for h in (file_handler, stream_handler):
        h.setFormatter(fmt)
        logger.addHandler(h)
    logger.setLevel(level)
    logger.propagate = False  # avoid duplicate lines through the root logger (e.g. under Gradio/uvicorn)
    _state.update(dir=logs_dir, file=path)
    logger.info("Logging to %s", path)
    return path


def log_block(logger: logging.Logger | logging.LoggerAdapter, title: str, text: str) -> None:
    """Log a full multi-line block (prompt, model output, raw event) between clear delimiters, untruncated."""
    logger.info("===== BEGIN %s (%d chars) =====\n%s\n===== END %s =====", title, len(text), text, title)


class _RunFilter(logging.Filter):
    """Pass only records tagged with one run_id (set by run_logger's LoggerAdapter `extra`)."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "run_id", None) == self.run_id


def run_logger(run_id: str, name: str = "afc.run") -> logging.LoggerAdapter:
    """Logger whose records carry run_id, so per-run handlers can pick them out of the shared stream."""
    return logging.LoggerAdapter(logging.getLogger(name), {"run_id": run_id})


def attach_run_log(path: Path, run_id: str) -> logging.Handler:
    """Add a file handler that captures only this run's records (UI live-log source); returns it for detaching."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT, DATEFMT))
    handler.addFilter(_RunFilter(run_id))
    logger = logging.getLogger(ROOT_LOGGER)
    if logger.level == logging.NOTSET:  # without setup_logging (library use) INFO lines would fall to root's WARNING
        logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler


def detach_run_log(handler: logging.Handler) -> None:
    """Remove and close a per-run handler once the run's work is finished."""
    logging.getLogger(ROOT_LOGGER).removeHandler(handler)
    handler.close()
