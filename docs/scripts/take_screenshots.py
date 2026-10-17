"""Screenshots of the Gradio UI for README.md: the whole app, then one real run on an example text.

Local: starts the real app in this process (`ui.launch(block=False)`), drives it with headless Playwright like a
user would (pick an example text, pick a preset, Load preset, Run fact-check), waits for the run to finish and saves
PNGs to docs/images/.
Global context: the run goes through pipeline.run_fact_check and RunContext.call like any UI run, so its prompt and
output are logged in full to logs/ and runs/<id>/, billed to logs/spend.jsonl and capped by SPEND_LIMIT_USD. With
the default preset it is one gpt-6-luna call with web search, about $0.03.
Usage: uv run --group docs python docs/scripts/take_screenshots.py [--channel msedge]
(without --channel, run `uv run --group docs playwright install chromium` once).
Sources: Playwright screenshots https://playwright.dev/python/docs/screenshots ; locators
https://playwright.dev/python/docs/locators ; installed Edge/Chrome via `channel`
https://playwright.dev/python/docs/browsers#google-chrome--microsoft-edge ; Gradio launch(prevent_thread_lock)
https://www.gradio.app/docs/gradio/blocks#blocks-launch ; elem_id
https://www.gradio.app/guides/custom-CSS-and-JS#the-elem_id-and-elem_classes-arguments
"""

import argparse
import logging
import re

from playwright.sync_api import expect, sync_playwright

from auto_fact_checker import spend
from auto_fact_checker.config import ROOT, get_settings
from auto_fact_checker.logs import setup_logging
from auto_fact_checker.ui import launch

log = logging.getLogger("afc.screenshots")
FINISHED = re.compile(r"^(done|stopped|error) — run ")  # ui.outputs_for status line: "**done** — run `<id>` — …"


def pick(page, combobox: str, option: str) -> None:
    """Choose a Gradio Dropdown option by clicking, so its `.input` event fires as for a user."""
    page.get_by_role("combobox", name=combobox).click()
    page.get_by_role("option", name=option, exact=True).click()


def save(page, path, tab: str | None = None, max_height: int | None = None) -> None:
    """Whole page (tab=None), or the text-and-results column `#afc-io` with `tab` open, cut to max_height px."""
    if tab is None:
        page.screenshot(path=path, full_page=True)
    else:
        page.get_by_role("tab", name=tab, exact=True).click()
        page.evaluate("window.scrollTo(0, 0)")  # bounding_box() is viewport-relative; at scroll 0 it is page-relative
        box = page.locator("#afc-io").bounding_box()
        box["height"] = min(box["height"], max_height or box["height"])
        page.screenshot(path=path, full_page=True, clip=box)  # full_page so the clip may extend below the viewport
    log.info("Saved %s", path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--example", default="ai_research", help="examples/<name>.md")
    p.add_argument("--preset", default="L1_single_call_search", help="configs/presets/<name>.json")
    p.add_argument("--channel", default=None, help="installed browser, e.g. msedge or chrome (default: bundled)")
    p.add_argument("--port", type=int, default=7861, help="7860 is left free for a running `afc ui`")
    p.add_argument("--timeout", type=int, default=900, help="seconds to wait for the run to finish")
    p.add_argument("--out", default=str(ROOT / "docs" / "images"))
    args = p.parse_args()
    s = get_settings()
    setup_logging(s.logs_dir)
    log.info("Billed spend before: $%.4f of $%.2f", spend.total_billed(s.ledger), s.spend_limit_usd)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    demo = launch(port=args.port, inbrowser=False, block=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=args.channel)
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="light")
            page.goto(f"http://127.0.0.1:{args.port}/")
            pick(page, "Load an example text", args.example)
            expect(page.get_by_label("Text to fact-check")).not_to_have_value("")  # example.input filled the box
            pick(page, "Preset (fills every setting below)", args.preset)
            page.get_by_role("button", name="Load preset").click()
            page.wait_for_timeout(2000)  # Gradio keeps a stream open (no "networkidle"); the preset event takes <1 s
            save(page, out / "app.png")
            page.set_viewport_size({"width": 2400, "height": 1000})  # wider results column: 7-column Claims table
            page.get_by_role("button", name="Run fact-check").click()
            status = page.get_by_text(FINISHED).first
            status.wait_for(timeout=args.timeout * 1000)
            log.info("Run finished: %s", status.inner_text())
            if not status.inner_text().startswith("done"):
                raise RuntimeError(f"Run did not finish cleanly: {status.inner_text()}")
            save(page, out / "example_claims.png", tab="Claims")
            save(page, out / "example_corrected.png", tab="Corrected text")
            save(page, out / "example_report.png", tab="Report", max_height=1600)
            browser.close()
    finally:
        demo.close()
    log.info("Billed spend after: $%.4f", spend.total_billed(s.ledger))


if __name__ == "__main__":
    main()
