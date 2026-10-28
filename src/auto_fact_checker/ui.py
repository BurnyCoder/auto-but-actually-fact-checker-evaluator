"""Gradio UI: every FactCheckConfig field (per step and global) as a widget, presets, run controls and outputs.

Local: widgets are generated from the pydantic field types (bool -> Checkbox, Literal -> Radio/Dropdown,
int/float with a RANGES entry -> Slider, list[str] -> CheckboxGroup (+ "extra items" Textbox), other -> Textbox).
A new StepConfig field appears in every Steps tab without UI code; a new FactCheckConfig field must be added to one
of the per-tab field tuples in build_ui (tests/test_ui.py checks that every field has a widget). Editing a COUPLED
setting runs config.fix_combination, which adjusts the conflicting settings, so the widgets can only reach valid
configurations. Run / One more iteration are generator handlers that run the pipeline in a
worker thread and stream progress (report, tables, live log) every second; Stop sets the run's cancel flag
(backend cancellation is cooperative); polling stays alive to show the terminal status.
Global context: the UI only builds a FactCheckConfig and calls pipeline.run_fact_check / run_perspective /
synthesize_perspectives; everything shown comes from render.py.
Gradio docs: Blocks https://www.gradio.app/docs/gradio/blocks ; streaming generators
https://www.gradio.app/guides/streaming-outputs ; State https://www.gradio.app/guides/state-in-blocks ;
dynamic render https://www.gradio.app/guides/dynamic-apps-with-render-decorator ; cancels
https://www.gradio.app/docs/gradio/button#event-listeners
"""

import json
import re
import time
import typing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import gradio as gr
import pandas as pd
from pydantic import ValidationError

from . import catalog, render, spend
from .config import (PRESETS_DIR, ROOT, STEPS, FactCheckConfig, StepConfig, fix_combination, get_settings,
                     list_presets, load_preset, options, save_preset, section_ids)
from .context import begin_batch, stop_run
from .pipeline import run_fact_check, run_perspective, synthesize_perspectives
from .prompts import build_agents, build_prompt, template_choices
from .results import RUNS, FactCheckRun, new_run

EXECUTOR = ThreadPoolExecutor(max_workers=8)  # pipeline work runs here; UI handlers only poll
WHOLE_TEXT = "Whole (current) text"
EXAMPLES = sorted(p for p in (ROOT / "examples").glob("*.md") if p.name != "README.md")
SHIPPED_PRESETS = {p for p in list_presets() if re.match(r"L\d_", p)}  # repo presets L0-L5 are read-only here
# Slider ranges (min, max, step) for numeric fields; max_turns 0 means "no limit".
RANGES = {"max_searches": (0, 50, 1), "max_subagents": (1, 30, 1), "max_turns": (0, 300, 1),
          "timeout_s": (60, 7200, 60), "max_claims": (1, 50, 1), "max_parallel": (1, 16, 1),
          "accuracy_threshold": (0, 100, 1), "max_iterations": (1, 20, 1), "max_cost_usd": (0.01, 10.0, 0.01)}
LABELS = {"kind": "Call type: API conversation turn or an agent (Codex / Claude Code)",
          "provider": "Provider (OpenAI preferred)", "effort": "Depth: reasoning effort",
          "web_search": "Allow web search",
          "allow_subagents": "Agent may spawn subagents (always on for the check step under a subagent strategy)",
          "prompt_template": "Prompt template (files in prompts/<step>/)",
          "prompt_override": "Prompt override (full Jinja prompt, use {{ text }}; empty = template)",
          "blocked_domains": "Blocked search domains (comma-separated)",
          "claim_strategy": "Claims: whole text / one subagent per claim (check step becomes an agent) / "
                            "one separate call per claim",
          "scientist_strategy": "Scientists: in-prompt only / one subagent each (check step becomes an agent) / "
                                "one separate call each",
          "sections": "Prompt parts that go in (01-20: the original prompt, sentence by sentence; 00, 21-23: added)",
          "conditions": "Scored conditions (score %, + confidence % while block 23 is on; only while their section is on)",
          "score_all_labels": "Score EVERY selected verdict label for every claim (else only applicable ones)",
          "score_each_scientist": "Add a scored condition per named scientist (long output!)",
          "iterate_until_accurate": "Repeat until model-reported scores reach the threshold",
          "accuracy_threshold": "Model-reported accuracy threshold (%)",
          "perspective_scientists": "Scientists for separate calls / subagents / perspective buttons"}
# Claims table (render.claims_rows: #, claim, accuracy, confidence, types, top labels, corrected claim). Fixed widths
# with wrap=True keep every column visible; without them the wrapped claim text takes the whole width.
CLAIM_WIDTHS = ["3%", "22%", "7%", "8%", "17%", "21%", "22%"]
# Settings whose edits can conflict with another setting; config.fix_combination resolves them.
COUPLED = [("claim_strategy",), ("scientist_strategy",), ("perspective_scientists",), ("steps", "check", "kind"),
           ("steps", "check", "enabled"), ("steps", "perspective", "enabled"),
           *[("steps", s, f) for s in STEPS for f in ("provider", "model")]]
LIST_CHOICES = {"degrees": "degrees", "verdict_labels": "verdict_labels", "styles": "styles",
                "claim_types": "claim_types", "scientists": "scientists", "perspective_scientists": "scientists"}


@dataclass
class Knob:
    """One widget bound to a config path; `extra` marks the free-text companion of a list CheckboxGroup."""

    path: tuple
    comp: gr.components.Component
    extra: bool = False


def _section_choices() -> list[tuple[str, str]]:
    """(label, id) pairs: section id plus the start of its text so users see what each block says."""
    texts = {s: (ROOT / "prompts" / "sections" / f"{s}.md").read_text(encoding="utf-8") for s in section_ids()}
    return [(f"{s}: {t[:90].strip()}{'…' if len(t) > 90 else ''}", s) for s, t in texts.items()]


def _list_choices(name: str) -> list:
    if name == "sections":
        return _section_choices()
    if name == "conditions":
        return [c["name"] for c in options()["conditions"]]
    return list(options()[LIST_CHOICES[name]]) if name in LIST_CHOICES else []


def _widgets(name: str, annotation, value, step: str | None, knobs: list[Knob], path: tuple) -> None:
    """Create the widget(s) for one field from its type and register them in `knobs`."""
    label = LABELS.get(name, name.replace("_", " "))
    args = typing.get_args(annotation)
    if annotation is bool:
        knobs.append(Knob(path, gr.Checkbox(value=value, label=label)))
    elif name == "model":
        knobs.append(Knob(path, gr.Dropdown(choices=catalog.choices("openai") + catalog.choices("anthropic"),
                                            value=value, label="Model (price per 1M in/out tokens)",
                                            allow_custom_value=True)))
    elif name == "prompt_template":
        knobs.append(Knob(path, gr.Dropdown(choices=template_choices(step), value=value, label=label)))
    elif typing.get_origin(annotation) is typing.Literal:
        widget = gr.Radio if len(args) <= 4 else gr.Dropdown
        knobs.append(Knob(path, widget(choices=list(args), value=value, label=label)))
    elif name in RANGES:
        lo, hi, st = RANGES[name]
        knobs.append(Knob(path, gr.Slider(lo, hi, value=value or 0, step=st, label=label)))
    elif name == "blocked_domains":
        knobs.append(Knob(path, gr.Textbox(value=", ".join(value), label=label)))
    elif typing.get_origin(annotation) is list:
        choices = _list_choices(name)
        knobs.append(Knob(path, gr.CheckboxGroup(choices=choices, value=[v for v in value if v in _ids(choices)],
                                                 label=label, show_select_all=True)))
        if name not in ("sections", "conditions"):
            knobs.append(Knob(path, gr.Textbox(value="; ".join(v for v in value if v not in _ids(choices)),
                                               label=f"Extra {name.replace('_', ' ')} (separate with ;)"),
                              extra=True))
    else:
        lines = 6 if name in ("prompt_override", "custom_instructions") else 1
        knobs.append(Knob(path, gr.Textbox(value=value, label=label, lines=lines)))


def _ids(choices) -> list:
    return [c[1] if isinstance(c, tuple) else c for c in choices]


def cfg_from(knobs: list[Knob], values) -> FactCheckConfig:
    """Rebuild a FactCheckConfig from widget values (raises gr.Error with the validation message)."""
    return _validated(_data_from(knobs, values))


def fix_values(knobs: list[Knob], changed: tuple, values) -> tuple[list, list[str]]:
    """Widget values after config.fix_combination adjusted the settings coupled to the edited one, plus notes."""
    data = _data_from(knobs, values)
    notes = fix_combination(data, changed)
    return values_from(knobs, _validated(data)), notes


def _validated(data: dict) -> FactCheckConfig:
    try:
        return FactCheckConfig.model_validate(data)
    except ValidationError as e:
        raise gr.Error(f"Invalid configuration: {e.errors()[0]['msg']}")


def _data_from(knobs: list[Knob], values) -> dict:
    """Config dump with the widget values written in (list extras, domains, max_turns 0 -> None, int sliders)."""
    data = FactCheckConfig().model_dump()
    for knob, v in zip(knobs, values):
        *parents, leaf = knob.path
        node = data
        for p in parents:
            node = node[p]
        if knob.extra:
            node[leaf] = list(node[leaf]) + [x.strip() for x in (v or "").split(";") if x.strip()]
        elif leaf == "blocked_domains":
            node[leaf] = [x.strip() for x in (v or "").split(",") if x.strip()]
        elif leaf == "max_turns":
            node[leaf] = int(v) or None
        elif leaf in RANGES and isinstance(node[leaf], int):
            node[leaf] = int(v)
        else:
            node[leaf] = v
    return data


def values_from(knobs: list[Knob], cfg: FactCheckConfig) -> list:
    """Widget values for a configuration (preset loading); list fields split into selected + extras."""
    data, out = cfg.model_dump(), []
    for knob in knobs:
        node = data
        for p in knob.path:
            node = node[p]
        if isinstance(knob.comp, gr.CheckboxGroup):
            out.append([v for v in node if v in _ids(knob.comp.choices)])
        elif knob.extra:
            prev = [k for k in knobs if k.path == knob.path and not k.extra][0].comp
            out.append("; ".join(v for v in node if v not in _ids(prev.choices)))
        elif knob.path[-1] == "blocked_domains":
            out.append(", ".join(node))
        elif knob.path[-1] == "max_turns":
            out.append(node or 0)
        else:
            out.append(node)
    return out


def preview(cfg: FactCheckConfig, text: str) -> str:
    """Preview selected prompts; extracted-claim prompts are illustrative until extraction returns."""
    text = text or "<your text>"
    parts = []
    if cfg.claim_strategy == "separate_call_per_claim" and cfg.steps["extract"].enabled:
        parts.append(("EXTRACT", build_prompt(cfg, "extract", text)))
        target, context = "<one extracted claim>", text
    else:
        target, context = text, None
    if cfg.steps["check"].enabled:
        parts.append(("CHECK", build_prompt(cfg, "check", target, context=context)))
    if cfg.uses_subagents:
        parts.append(("SUBAGENTS (--agents JSON)", json.dumps(build_agents(cfg), indent=1, ensure_ascii=False)))
    if (cfg.scientist_strategy == "separate_call_per_scientist" and cfg.perspective_scientists
            and cfg.steps["perspective"].enabled):  # same condition as pipeline.run_iteration
        parts.append((f"PERSPECTIVE ({cfg.perspective_scientists[0]})",
                      build_prompt(cfg, "perspective", target, context=context,
                                   persona=cfg.perspective_scientists[0])))
    note = ("Illustrative check/perspective prompts: the extracted claim and its context depend on extraction.\n\n"
            if cfg.claim_strategy == "separate_call_per_claim" and cfg.steps["extract"].enabled else "")
    return note + "\n\n".join(f"########## {title} ##########\n{body}" for title, body in parts)


def outputs_for(run: FactCheckRun | None):
    """Values for every output component, in OUTPUT order."""
    if run is None:
        return [None, "", "", None, None, None, "", "", None, None, "", {}, gr.Dropdown(choices=[WHOLE_TEXT])]
    final = run.iterations[-1].final if run.iterations else None
    s = final.summary if final else None
    log_path = get_settings().runs_dir / run.run_id / "run.log"
    log = log_path.read_text(encoding="utf-8", errors="replace")[-80_000:] if log_path.exists() else ""
    ledger = spend.summary(get_settings().ledger)
    status = (f"**{run.status}** — run `{run.run_id}` — iteration {len(run.iterations)} — "
              f"{len(run.calls)} calls — run known estimate ${run.total_cost_usd:.4f} "
              f"({run.unknown_cost_calls} unknown-cost calls) — known billed estimate "
              f"${ledger['known_billed_usd']:.4f} of ${get_settings().spend_limit_usd:.2f} "
              f"({ledger['unknown_billed_calls']} unknown billed calls)"
              + (f" — {run.stop_reason}" if run.stop_reason else ""))
    claims = [c.claim for c in s.claims] if s else []
    return [run.run_id, status, render.run_markdown(run), pd.DataFrame(render.claims_rows(s)),
            pd.DataFrame(render.labels_rows(s)), pd.DataFrame(render.conditions_rows(s)),
            (s.corrected_text or "") if s else "", "\n".join(f"- {i}" for i in (s.issues if s else [])),
            pd.DataFrame(render.iterations_rows(run)), pd.DataFrame(render.calls_rows(run)), log,
            s.model_dump() if s else {}, gr.Dropdown(choices=[WHOLE_TEXT] + claims)]


def _stream(run: FactCheckRun, *futures):
    """Yield refreshed outputs every second until all worker futures finish (then re-raise their errors)."""
    yield outputs_for(run)
    while not all(f.done() for f in futures):
        time.sleep(1.0)
        yield outputs_for(run)
    for f in futures:
        f.result()
    yield outputs_for(run)


def build_ui() -> gr.Blocks:
    """Construct the Blocks app (separate from launch() so tests can build it)."""
    knobs: list[Knob] = []
    with gr.Blocks(title="Auto Fact-Checker") as demo:
        gr.Markdown("# Auto Fact-Checker\nRigorous, configurable LLM fact-checking: choose per step whether to "
                    "use an API call or an agent, the model, depth, web search, subagents and every prompt block. "
                    "Scores and confidence are model-reported assessments; they do not certify factual correctness.")
        run_id = gr.State(None)
        with gr.Row():
            with gr.Column(scale=5, elem_id="afc-io"):  # text + results; the id lets scripts screenshot it
                example =gr.Dropdown(choices=[p.stem for p in EXAMPLES], value=None, label="Load an example text")
                text = gr.Textbox(lines=10, label="Text to fact-check")
                with gr.Row():
                    run_btn = gr.Button("Run fact-check", variant="primary")
                    more_btn = gr.Button("One more iteration")
                    stop_btn = gr.Button("Stop", variant="stop")
                    preview_btn = gr.Button("Preview prompts")
                status = gr.Markdown()
                with gr.Tabs():
                    with gr.Tab("Report"):
                        report = gr.Markdown()
                    with gr.Tab("Claims"):
                        claims_df = gr.Dataframe(label="Claims (model-reported accuracy, confidence, types, labels)",
                                                 wrap=True, max_height=2000, column_widths=CLAIM_WIDTHS)
                    with gr.Tab("Labels"):
                        labels_df = gr.Dataframe(label="Every scored verdict label per claim")
                    with gr.Tab("Conditions"):
                        cond_df = gr.Dataframe(label="Every scored condition per claim", wrap=True)
                    with gr.Tab("Corrected text"):
                        corrected = gr.Textbox(lines=10, label="Corrected whole text (input of the next iteration)")
                    with gr.Tab("Issues"):
                        issues = gr.Markdown()
                    with gr.Tab("Iterations"):
                        iter_df = gr.Dataframe()
                    with gr.Tab("Perspectives"):
                        gr.Markdown("Each scientist button (Strategy tab, under *Scientists for separate calls / "
                                    "subagents / perspective buttons*) makes one independent call with the "
                                    "Perspective step's settings; results are appended to the Report tab.")
                        target = gr.Dropdown(choices=[WHOLE_TEXT], value=WHOLE_TEXT, label="Evaluate",
                                             allow_custom_value=True)
                        with gr.Row():
                            all_btn = gr.Button("Run all selected scientists")
                            synth_btn = gr.Button("Synthesize perspectives")
                    with gr.Tab("Calls & cost"):
                        calls_df = gr.Dataframe()
                    with gr.Tab("Live log"):
                        log_box = gr.Textbox(lines=25, max_lines=25, autoscroll=True, label="runs/<id>/run.log")
                    with gr.Tab("Prompt preview"):
                        prompt_box = gr.Code(language="markdown", label="Prompt preview (extracted claims are illustrative)")
                    with gr.Tab("Raw JSON"):
                        raw = gr.JSON()
            with gr.Column(scale=4):
                with gr.Row():
                    preset = gr.Dropdown(choices=list_presets(), value=None, label="Preset (fills every setting below)")
                    load_btn = gr.Button("Load preset")
                with gr.Row():
                    preset_name = gr.Textbox(label="Save current settings as preset", placeholder="my_preset")
                    save_btn = gr.Button("Save preset")
                    reset_btn = gr.Button("Reset to defaults")
                defaults = FactCheckConfig()
                fields = FactCheckConfig.model_fields
                with gr.Tabs():
                    with gr.Tab("Strategy"):
                        for f in ("claim_strategy", "scientist_strategy", "max_claims", "max_parallel",
                                  "perspective_scientists"):
                            _widgets(f, fields[f].annotation, getattr(defaults, f), None, knobs, (f,))
                        sci_knob = next(k.comp for k in knobs if k.path == ("perspective_scientists",)
                                        and not k.extra)
                        gr.Markdown("**Perspective calls** — one independent call per button:")

                        @gr.render(inputs=[sci_knob])  # re-rendered whenever the selection changes
                        def scientist_buttons(names):
                            with gr.Row():
                                for name in names or []:
                                    gr.Button(name, size="sm").click(
                                        partial(on_perspective, [name]), [run_id, target, text, *comps], outputs,
                                        concurrency_limit=None)  # independent calls may run concurrently
                    with gr.Tab("Steps"):
                        with gr.Tabs():
                            for step in STEPS:
                                with gr.Tab(step.capitalize()):
                                    sc = defaults.steps[step]
                                    for f, info in StepConfig.model_fields.items():
                                        _widgets(f, info.annotation, getattr(sc, f), step, knobs, ("steps", step, f))
                    with gr.Tab("Prompt parts"):
                        for f in ("sections", "score_all_labels", "conditions", "score_each_scientist",
                                  "custom_instructions"):
                            _widgets(f, fields[f].annotation, getattr(defaults, f), None, knobs, (f,))
                    with gr.Tab("Lists"):
                        for f in ("verdict_labels", "degrees", "styles", "claim_types", "scientists"):
                            _widgets(f, fields[f].annotation, getattr(defaults, f), None, knobs, (f,))
                    with gr.Tab("Iteration & budget"):
                        for f in ("iterate_until_accurate", "accuracy_threshold", "max_iterations",
                                  "stop_on_fixed_point", "max_cost_usd"):
                            _widgets(f, fields[f].annotation, getattr(defaults, f), None, knobs, (f,))
        comps = [k.comp for k in knobs]
        outputs = [run_id, status, report, claims_df, labels_df, cond_df, corrected, issues, iter_df, calls_df,
                   log_box, raw, target]

        # Editing a coupled setting adjusts the others so every reachable widget state is a valid configuration
        # (.input fires only on user edits, not on these programmatic updates or preset loads, so it cannot loop).
        def on_coupled(changed, *vals):
            new, notes = fix_values(knobs, changed, vals)
            for note in notes:
                gr.Info(note)
            return new

        for path in COUPLED:
            comp = next(k.comp for k in knobs if k.path == path and not k.extra)
            comp.input(partial(on_coupled, path), comps, comps)

        example.input(lambda name: (ROOT / "examples" / f"{name}.md").read_text(encoding="utf-8"), example, text)

        def on_run(txt, *vals):
            if not (txt or "").strip():
                raise gr.Error("Enter a text to fact-check")
            cfg = cfg_from(knobs, vals)
            run = new_run(txt, cfg)
            cancel = begin_batch(run.run_id)  # Capture before submission so Stop also reaches queued workers.
            yield from _stream(run, EXECUTOR.submit(run_fact_check, txt, cfg, run, cancel=cancel))

        def on_more(rid, *vals):
            run = RUNS.get(rid)
            if run is None:
                raise gr.Error("Run a fact-check first")
            if run.status == "running":
                raise gr.Error("This run is still in progress; wait for it or press Stop")
            cfg = cfg_from(knobs, vals)
            cancel = begin_batch(run.run_id)
            yield from _stream(run, EXECUTOR.submit(run_fact_check, run.current_text, cfg, run, 1, cancel=cancel))

        run_btn.click(on_run, [text, *comps], outputs)
        more_btn.click(on_more, [run_id, *comps], outputs)
        # Keep _stream polling: Gradio cancels would otherwise discard the final stopped frame.
        stop_btn.click(lambda rid: stop_run(rid) if rid else None, run_id, None, queue=False)
        preview_btn.click(lambda txt, *vals: preview(cfg_from(knobs, vals), txt), [text, *comps], prompt_box)

        def on_load(name):
            if not name:
                raise gr.Error("Choose a preset")
            return values_from(knobs, load_preset(name))

        def on_save(name, *vals):
            name = (name or "").strip()
            if not re.fullmatch(r"[\w-]+", name):
                raise gr.Error("Preset names may contain only letters, digits, _ and -")
            if name in SHIPPED_PRESETS:
                raise gr.Error(f"{name} is a shipped preset; choose another name")
            path = save_preset(cfg_from(knobs, vals), PRESETS_DIR / f"{name}.json")
            gr.Info(f"Saved {path.name}")
            return gr.Dropdown(choices=list_presets(), value=name)

        load_btn.click(on_load, preset, comps)
        save_btn.click(on_save, [preset_name, *comps], preset)
        reset_btn.click(lambda: values_from(knobs, FactCheckConfig()), None, comps)

        # Perspective calls: one independent call per scientist, results appended to the run.
        def ensure_run(rid, txt, cfg) -> FactCheckRun:
            if rid in RUNS:
                return RUNS[rid]
            if not (txt or "").strip():
                raise gr.Error("Enter a text first")
            return new_run(txt, cfg)

        def on_perspective(names, rid, tgt, txt, *vals):
            cfg = cfg_from(knobs, vals)
            run = ensure_run(rid, txt, cfg)
            goal = run.current_text if tgt in (None, WHOLE_TEXT) else tgt
            cancel = begin_batch(run.run_id)
            yield from _stream(run, *[EXECUTOR.submit(run_perspective, run, n, goal, cfg, cancel=cancel)
                                     for n in names])

        def on_all(rid, tgt, txt, *vals):
            yield from on_perspective(cfg_from(knobs, vals).perspective_scientists, rid, tgt, txt, *vals)

        def on_synth(rid, *vals):
            run = RUNS.get(rid)
            if run is None or not run.perspectives:
                raise gr.Error("Run some perspective calls first")
            cancel = begin_batch(run.run_id)
            yield from _stream(run, EXECUTOR.submit(synthesize_perspectives, run, cfg_from(knobs, vals), cancel=cancel))

        all_btn.click(on_all, [run_id, target, text, *comps], outputs)
        synth_btn.click(on_synth, [run_id, *comps], outputs)
    demo.afc_knobs = knobs  # exposed for tests (config <-> widget round trip)
    return demo


def launch(port: int = 7860, inbrowser: bool = True, block: bool = True) -> gr.Blocks:
    """Serve on localhost only: agents run without a sandbox, so the UI must not be exposed to a network.
    block=False returns at once (Gradio `prevent_thread_lock`) so a script can drive the app and then `close()` it,
    see docs/scripts/take_screenshots.py and https://www.gradio.app/docs/gradio/blocks#blocks-launch"""
    demo = build_ui().queue(default_concurrency_limit=4)
    demo.launch(server_name="127.0.0.1", server_port=port, inbrowser=inbrowser, prevent_thread_lock=not block)
    return demo
