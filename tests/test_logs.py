"""Tests for logs.py: timestamped log files + terminal output, full (never truncated) prompt/output blocks.

Global context: the user requires every LLM prompt and output to be visible in a timestamped log file and the
terminal in real time without truncation; logs.log_block() is the only function that writes those blocks.
"""

import logging

from auto_fact_checker import logs


def test_log_file_gets_full_unicode_blocks(tmp_path):
    path = logs.setup_logging(tmp_path)  # creates <tmp>/<YYYYmmdd_HHMMSS>.log
    assert path.parent == tmp_path and path.suffix == ".log"
    big = "Gödel ≥ " + "x" * 100_000 + " END"  # long, non-ASCII payload
    logs.log_block(logging.getLogger("afc.test"), "PROMPT test", big)
    for h in logging.getLogger("afc").handlers:
        h.flush()
    content = path.read_text(encoding="utf-8")
    assert big in content  # nothing truncated, UTF-8 preserved
    assert "PROMPT test" in content and content[:4].isdigit()  # each record starts with a timestamp (year)


def test_run_log_filter(tmp_path):
    logs.setup_logging(tmp_path)
    handler = logs.attach_run_log(tmp_path / "run.log", run_id="r1")  # per-run file, filtered by run_id
    logs.run_logger("r1").info("mine")
    logs.run_logger("r2").info("other run")
    handler.flush()
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    logs.detach_run_log(handler)
    assert "mine" in text and "other run" not in text
