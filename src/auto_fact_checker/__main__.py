"""Command-line entry point: `uv run afc ui | check | spend | bench`.

Global context: thin argparse layer over pipeline.run_fact_check (check), ui.launch (ui), the spend ledger (spend)
and bench.run (bench). argparse docs: https://docs.python.org/3/library/argparse.html#sub-commands
"""

import argparse
import sys
from pathlib import Path

from . import spend
from .config import FactCheckConfig, apply_overrides, get_settings, load_preset
from .logs import setup_logging


def _config(preset: str | None, overrides: list[str]) -> FactCheckConfig:
    """Preset (name or path) + dotted overrides, e.g. --set steps.check.model=gpt-6.1-sol."""
    return apply_overrides(load_preset(preset) if preset else FactCheckConfig(), overrides)


def cmd_check(args) -> int:
    """Fact-check a file (or stdin) and write runs/<id>/report.md."""
    from .pipeline import run_fact_check
    from .render import run_markdown

    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    cfg = _config(args.preset, args.set)
    if args.iterations:
        cfg = cfg.model_copy(update={"iterate_until_accurate": True, "max_iterations": args.iterations})
    run = run_fact_check(text, cfg)
    report = get_settings().runs_dir / run.run_id / "report.md"
    report.write_text(run_markdown(run), encoding="utf-8")
    print(f"\nRun {run.run_id}: {run.status} ({run.stop_reason}); cost ${run.total_cost_usd:.4f}; report: {report}")
    return 0 if run.status == "done" else 1


def cmd_spend(_args) -> int:
    """Print the cumulative billed spend against the cap."""
    s = get_settings()
    print(f"Billed spend: ${spend.total_billed(s.ledger):.4f} of SPEND_LIMIT_USD=${s.spend_limit_usd:.2f} ({s.ledger})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="afc", description="Configurable rigorous LLM fact-checker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ui = sub.add_parser("ui", help="launch the Gradio UI on 127.0.0.1")
    ui.add_argument("--port", type=int, default=7860)
    ui.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    chk = sub.add_parser("check", help="fact-check a text file ('-' = stdin)")
    chk.add_argument("file")
    chk.add_argument("--preset", help="preset name in configs/presets or a JSON path")
    chk.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="dotted config override")
    chk.add_argument("--iterations", type=int, help="iterate until accurate, at most N passes")
    sub.add_parser("spend", help="show cumulative billed API spend")
    bench = sub.add_parser("bench", help="run a benchmark (see docs/benchmark.md)")
    bench.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    setup_logging(get_settings().logs_dir)
    if args.cmd == "ui":
        from .ui import launch
        launch(port=args.port, inbrowser=not args.no_browser)
        return 0
    if args.cmd == "bench":
        from .bench.run import main as bench_main
        return bench_main(args.args)
    return {"check": cmd_check, "spend": cmd_spend}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
