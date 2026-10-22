# AGENTS.md — working on this repository

Guidance for coding agents (Codex, Claude Code) and contributors. User-facing documentation is in
[README.md](README.md); design details are in [docs/](docs).

## Commands

```bash
uv sync                         # install (Python 3.13, .venv in repo)
uv run pytest                   # offline suite (fake backend, no LLM/network call; must stay green)
uv run pytest -m live           # paid LLM/CLI calls (variable cost; needs .env keys, claude/codex logins)
uv run afc ui --no-browser      # Gradio UI on 127.0.0.1:7860
uv run afc check FILE --preset NAME [--set dotted.key=value ...] [--iterations N]
uv run afc bench --systems A.json B.json --n N --max-cost USD --out DIR [--exclude-from PILOT_DIR]
uv run afc correct-eval --items-from ITEMS.json --system LOOP.json --judges J1.json J2.json --out DIR --max-cost USD  # Exp07
uv run afc ai-errors build --out SCRATCH_DIR   # Exp08: paid fetch + inject; never overwrite frozen benchmarks/ai_errors_v1
uv run afc ai-errors run --system ARM.json --judges J1.json J2.json --out DIR --max-cost USD    # Exp08 forced-pass loop
uv run afc spend                # recorded billed cost estimates vs SPEND_LIMIT_USD
uv run --group docs python docs/scripts/take_screenshots.py --offline --channel msedge   # synthetic UI fixtures, no paid call
```

After a UI layout change, rerun the screenshot script in offline mode. It drives the real UI with synthetic
responses; screenshot scores are not experimental evidence. The left column's `elem_id="afc-io"` and the widget
labels it clicks are part of its contract.

## Architecture rules

- `pipeline.py` is the single wrapper. It calls the phases in `phases/` (extract, check, synthesize, iterate).
  New behaviour goes into a phase or a backend, not into the UI.
- Every LLM call in production code goes through `context.RunContext.call()`. Never call a backend directly (only
  `tests/test_live.py` does, with its own budget check). That method handles logging, artifacts, soft budget checks
  and cancellation. Do not describe recorded cost checks as a guarantee against overspending.
- Backends follow one contract: `call(LLMRequest, logger) -> LLMResult`. Register each one in
  `backends/__init__.py:BACKENDS` and map it in `config.py` (`Kind` / `Provider` literals and the `(kind, provider)`
  `BACKENDS` table), or no step can select it. Agent CLIs must use `backends/subprocess_jsonl.run_agent`, which
  handles Windows-safe execution, stdin prompts, realtime logs, tree-kill and auth env.
- Settings belong in `FactCheckConfig` / `StepConfig` fields (`config.py`). The UI generates widgets from field
  types (`ui._widgets`): a new `StepConfig` field appears automatically; a new `FactCheckConfig` field must be added
  to one of the per-tab field tuples in `ui.build_ui` (`tests/test_ui.py` fails until it is). Numbers become
  sliders only with a `ui.RANGES` entry; add a label in `ui.LABELS` when needed. Modes are presets in
  `configs/presets/*.json`; never hard-code a mode.
- Prompt text lives in `prompts/`. The exceptions are short generated instructions: the agent search note and
  subagent descriptions in `prompts.py`, `codex.DEVELOPER_NOTE` and the per-scientist condition in
  `config.active_conditions`. For new prompt text:
  - a new toggleable block is a new `sections/NN_name.md`
  - a new scored condition is an entry in `options.json["conditions"]`, tied to its section
  - a new template is a new `.md` in the step folder

  Templates are Jinja2 with `StrictUndefined`. `tests/test_prompts.py::test_every_template_renders` catches
  missing variables in the five step folders; the subagent, judge and bench templates are rendered by other tests.
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

Keep paid development within `SPEND_LIMIT_USD` (default $10), using only `gpt-6-luna` and `claude-haiku-5-5`.
Check `uv run afc spend` before any paid run and leave headroom: estimates are recorded after calls, sequential
and parallel calls can overshoot, and unknown costs contribute zero to totals. Subscription fees are excluded.
Prefer offline tests for verification; see [cost controls](README.md#costs-and-safety) and the
[independent verification record](reports/verification_2026-10-22.md).
