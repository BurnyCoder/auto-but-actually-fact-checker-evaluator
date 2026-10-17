# AGENTS.md — working on this repository

Guidance for coding agents (Codex, Claude Code) and contributors. User-facing documentation is in
[README.md](README.md); design details are in [docs/](docs).

## Commands

```bash
uv sync                         # install (Python 3.13, .venv in repo)
uv run pytest                   # offline suite (fake backend; must stay green, no network)
uv run pytest -m live           # real LLM/CLI calls (costs cents; needs .env keys, claude/codex logins)
uv run afc ui --no-browser      # Gradio UI on 127.0.0.1:7860
uv run afc check FILE --preset NAME [--set dotted.key=value ...] [--iterations N]
uv run afc bench --systems A.json B.json --n N --max-cost USD --out DIR [--exclude-from PILOT_DIR]
uv run afc correct-eval --items-from ITEMS.json --system LOOP.json --judges J1.json J2.json --out DIR --max-cost USD  # Exp07
uv run afc ai-errors build --out benchmarks/ai_errors_v1          # Exp08: fetch passages + inject errors (cents)
uv run afc ai-errors run --system ARM.json --judges J1.json J2.json --out DIR --max-cost USD    # Exp08 forced-pass loop
uv run afc spend                # billed spend so far vs SPEND_LIMIT_USD
uv run --group docs python docs/scripts/take_screenshots.py --channel msedge   # README screenshots, one paid call (~$0.03)
```

After a UI layout change, rerun the screenshot script. It drives the real UI: the left column's `elem_id="afc-io"`
and the widget labels it clicks are part of its contract.

## Architecture rules

- `pipeline.py` is the single wrapper. It calls the phases in `phases/` (extract, check, synthesize, iterate).
  New behaviour goes into a phase or a backend, not into the UI.
- Every LLM call goes through `context.RunContext.call()`. Never call a backend directly. That method is where
  logging, artifacts, the spend cap, the per-run budget and Stop are enforced.
- Backends follow one contract: `call(LLMRequest, logger) -> LLMResult`. Register each one in
  `backends/__init__.py:BACKENDS`. Agent CLIs must use `backends/subprocess_jsonl.run_agent`, which handles
  Windows-safe execution, stdin prompts, realtime logs, tree-kill and auth env.
- Settings belong in `FactCheckConfig` / `StepConfig` fields (`config.py`). The UI generates widgets from field
  types (`ui._widgets`), so a new field appears in the UI automatically. Add a slider range in `ui.RANGES` and a
  label in `ui.LABELS` when needed. Modes are presets in `configs/presets/*.json`; never hard-code a mode.
- Prompt text lives only in `prompts/`:
  - a new toggleable block is a new `sections/NN_name.md`
  - a new scored condition is an entry in `options.json["conditions"]`, tied to its section
  - a new template is a new `.md` in the step folder

  Templates are Jinja2 with `StrictUndefined`. `tests/test_prompts.py::test_every_template_renders` catches
  missing variables.
- Output parsing goes through `schema.parse_block`, which is tolerant. Keep new JSON fields optional.

## Conventions

- Use uv for everything (`uv add`, `uv run`). Configuration comes from `.env`; never commit it.
- Log through `logging.getLogger("afc.<module>")` or the run's `ctx.log`. Long text goes through
  `logs.log_block`, which never truncates.
- Comments: every module docstring states the local purpose and the global context, and links its sources (docs,
  papers). Line comments explain why.
- Tests come first, offline, using `tests/conftest.py::FakeBackend`. Live tests get `@pytest.mark.live`.
- Git: feature branch, then a PR, then `gh pr merge --merge --delete-branch`. One commit per functional unit.

## Budget rule for agents working here

The cumulative billed spend recorded in `logs/spend.jsonl` must stay at or below `SPEND_LIMIT_USD` (default $10).
For development and experiments, use only `gpt-6-luna` and `claude-haiku-5-5`. Check `uv run afc spend` before
any paid run.
