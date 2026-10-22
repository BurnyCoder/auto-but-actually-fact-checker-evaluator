"""Verify documentation screenshots cannot reach paid backends when offline mode is selected.

Global context: offline UI fixtures exercise RunContext without contaminating the real ledger.
The registry seam follows https://docs.pytest.org/en/stable/how-to/monkeypatch.html .
"""

import importlib.util
import logging

from auto_fact_checker import backends, config
from auto_fact_checker.backends.base import LLMRequest


def test_offline_registry_isolated_and_clearly_marked(monkeypatch):
    """Every registered backend becomes an explicit fixture and settings move under .cache."""
    spec = importlib.util.spec_from_file_location("offline_ui", config.ROOT / "docs/scripts/offline_ui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(backends, "BACKENDS", dict(backends.BACKENDS))
    for key in ("LOGS_DIR", "RUNS_DIR", "GRADIO_ANALYTICS_ENABLED"):
        monkeypatch.setenv(key, "fixture-before")  # Restore the calling process environment after the test.
    settings = module.configure_offline()
    try:
        assert settings.runs_dir.is_relative_to(config.ROOT / ".cache")
        assert set(backends.BACKENDS.values()) == {module.response}
        result = module.response(LLMRequest(backend="openai_api", model="fixture", prompt="example"),
                                 logging.getLogger("afc.test"))
        assert "OFFLINE UI FIXTURE" in result.text and result.cost_usd == 0 and not result.billed
    finally:
        config.get_settings.cache_clear()
