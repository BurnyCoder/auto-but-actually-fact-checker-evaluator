"""HTML fragments for the Gradio UI: the status bar, the results overview (tiles + one card per claim) and word diffs.

Local: pure functions from a FactCheckRun to HTML strings that use the classes styled in ui.css. Every model-derived
string goes through esc(): gr.HTML has no sanitizer and renders its value through a JS template / Handlebars
template (gradio/components/html.py and its bundled frontend, Gradio 6.30), so besides <, >, &, and quotes the
template characters {, } and $ become entities as well. Numbers we format ourselves are inserted as they are.
Global context: ui.outputs_for() calls these on every one-second poll of a running fact-check; render.py stays the
Markdown/table renderer shared by the UI and the CLI. Scores are model-reported: the overview says so and bands them
against the user's own FactCheckConfig.accuracy_threshold, the number the iterate-until-accurate loop stops at.
Sources: html.escape https://docs.python.org/3/library/html.html#html.escape ; difflib.SequenceMatcher
https://docs.python.org/3/library/difflib.html#sequencematcher-objects ; status colours, the icon + label rule and the
stat-tile contract (label, value, sub-line) from the dataviz skill (references/palette.md, marks-and-anatomy.md);
colour is never the only cue: WCAG 2.2 SC 1.4.1 https://www.w3.org/WAI/WCAG22/Understanding/use-of-color
"""

import difflib
import html
import re

from . import render
from .results import FactCheckRun, IterationResult
from .schema import ClaimVerdict

ICONS = {"good": "✓", "warn": "!", "bad": "✕", "na": "–"}  # shown inside the band dot, so bands differ without colour
_TEMPLATE = str.maketrans({"{": "&#123;", "}": "&#125;", "$": "&#36;"})  # Handlebars {{ }} and JS ${ }
_TOKENS = re.compile(r"\s+|\S+")  # words and the whitespace between them, so a diff keeps the original spacing


def esc(text) -> str:
    """Escape any text for HTML content and attributes and neutralise Gradio's template syntax."""
    return html.escape("" if text is None else str(text), quote=True).translate(_TEMPLATE)


def band(score: float | None, threshold: float) -> str:
    """good: reaches the user's accuracy threshold; bad: below 50 % (or below a threshold under 50 %);
    warn: in between; na: the model returned no score."""
    if score is None:
        return "na"
    if score >= threshold:
        return "good"
    return "bad" if score < min(50, threshold) else "warn"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.0f}%"


def _segments(a: list[str], b: list[str]) -> list[list]:
    """Diff as [equal?, old text, new text] runs, with trivial equalities merged into the edits around them.

    A rewritten sentence shares spaces and filler words ("of", "the") with the old one, which would cut one edit
    into many. diff-match-patch's semantic cleanup drops an equality that is no longer than the edits on both of
    its sides (https://github.com/google/diff-match-patch/wiki/API#diff_cleanupsemanticdiffs--null); this applies
    that rule (an idea, not its code) until nothing changes.
    """
    segs: list[list] = []
    # autojunk=False: the heuristic would treat frequent tokens (spaces, "the") in texts over 200 tokens as junk.
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        old, new, equal = "".join(a[i1:i2]), "".join(b[j1:j2]), op == "equal"
        if segs and not equal and not segs[-1][0]:  # consecutive edits form one run
            segs[-1][1] += old
            segs[-1][2] += new
        else:
            segs.append([equal, old, new])
    merged = True
    while merged:
        merged = False
        for i in range(1, len(segs) - 1):
            before, eq, after = segs[i - 1], segs[i], segs[i + 1]
            if eq[0] and len(eq[1]) <= max(len(before[1]), len(before[2])) and \
                    len(eq[1]) <= max(len(after[1]), len(after[2])):
                segs[i - 1:i + 2] = [[False, before[1] + eq[1] + after[1], before[2] + eq[1] + after[2]]]
                merged = True
                break
    return segs


def word_diff_html(old: str, new: str) -> str:
    """`new` with the words removed from `old` in <del> and the added words in <ins> (both escaped).
    Whitespace stays outside the marks: added spacing and line breaks render as plain text (a highlighted blank
    line reads as a change), removed spacing is dropped because it is not part of `new`."""
    out = []
    for equal, a, b in _segments(_TOKENS.findall(old or ""), _TOKENS.findall(new or "")):
        if equal:
            out.append(esc(a))
            continue
        if a.strip():  # removed words (a delete, or the old half of a replace)
            out.append(f"<del>{esc(a.strip())}</del>")
        if b.strip():  # added words (an insert, or the new half of a replace)
            lead, core, trail = re.fullmatch(r"(\s*)(.*?)(\s*)", b, re.DOTALL).groups()
            out.append(f"{esc(lead)}<ins>{esc(core)}</ins>{esc(trail)}")
        elif b:  # only whitespace was added
            out.append(esc(b))
    return "".join(out)


def status_html(run: FactCheckRun, ledger: dict, limit: float) -> str:
    """Status pill, run id, then iteration, calls and both cost totals with their unknown-cost counts (a missing
    price must not look like a complete zero-dollar measurement), then the stop reason if any."""
    n = len(run.calls)
    meta = [f"iteration {len(run.iterations)}", f"{n} call{'' if n == 1 else 's'}",
            f"run known estimate ${run.total_cost_usd:.4f} ({run.unknown_cost_calls} unknown-cost calls)",
            f"known billed estimate ${ledger['known_billed_usd']:.4f} of ${limit:.2f} "
            f"({ledger['unknown_billed_calls']} unknown billed calls)"]
    reason = f'<span class="afc-reason">{esc(run.stop_reason)}</span>' if run.stop_reason else ""
    # Spaces between sibling spans keep the text readable for screen readers, copy-paste and Playwright's
    # get_by_text ("done run <id> iteration 1 ..."); the flex gap alone would render "donerun".
    return (f'<div class="afc-status afc-status-{esc(run.status)}"><span class="afc-pill">{esc(run.status)}</span> '
            f'<span>run <code>{esc(run.run_id)}</code></span> '
            f'<span class="afc-meta">{" ".join(f"<span>{m}</span>" for m in meta)}</span> {reason}</div>')


def _latest(run: FactCheckRun | None) -> IterationResult | None:
    """The newest iteration with a parsed summary (iteration 1 stays visible while iteration 2 runs)."""
    return next((it for it in reversed(run.iterations) if it.final and it.final.summary), None) if run else None


def _meter(score: float | None, what: str) -> str:
    """Thin bar whose fill is the score (0-100, clamped by schema._pct, so safe in the style attribute)."""
    if score is None:
        return ""
    return (f'<div class="afc-meter" role="img" aria-label="{what} {score:.0f}%">'
            f'<span style="width:{score:.0f}%"></span></div>')


def _tile(label: str, value: str, sub: str, meter: str = "", cls: str = "") -> str:
    return (f'<div class="afc-tile {cls}"><span class="afc-tile-label">{label}</span>'
            f'<span class="afc-tile-value">{value}</span>{meter}<span class="afc-tile-sub">{sub}</span></div>')


def _chips(title: str, items: list[str]) -> str:
    """A titled row of escaped chips (claim types, top verdict labels); nothing when the model gave none."""
    if not items:
        return ""
    return (f'<div class="afc-chips"><span class="afc-chips-title">{title}</span> '
            + " ".join(f'<span class="afc-chip">{esc(x)}</span>' for x in items) + "</div>")


def _card(i: int, c: ClaimVerdict, threshold: float) -> str:
    """One claim: band icon + accuracy, confidence, the claim, a meter, type and label chips, and the
    suggested correction as a word diff against the claim."""
    b = band(c.accuracy_pct, threshold)
    types = [f"{t.type} {_pct(t.confidence_pct)}" if t.confidence_pct is not None else t.type for t in c.claim_types]
    labels = [f"{lab.degree + ' ' if lab.degree else ''}{lab.label} {_pct(lab.score_pct)}" for lab in render.top_labels(c)]
    fix = ""
    if (c.corrected_claim or "").strip() and c.corrected_claim.strip() != c.claim.strip():
        fix = (f'<div class="afc-fix"><p class="afc-fix-label">Suggested correction</p>'
               f'<p>{word_diff_html(c.claim, c.corrected_claim)}</p></div>')
    return (f'<div class="afc-card afc-band-{b}"><div class="afc-card-head"><span class="afc-num">#{i}</span> '
            f'<span class="afc-score"><span class="afc-icon">{ICONS[b]}</span> Accuracy {_pct(c.accuracy_pct)}</span> '
            f'<span class="afc-muted">Confidence {_pct(c.confidence_pct)}</span></div>'
            f'<p class="afc-claim">{esc(c.claim)}</p>{_meter(c.accuracy_pct, "accuracy")}'
            f'{_chips("Type", types)}{_chips("Labels", labels)}{fix}</div>')


def _legend(threshold: float) -> str:
    """What the colours mean; the middle band disappears when the threshold is 50 % or lower."""
    lo = min(50, threshold)
    items = [("good", f"≥ {threshold:g}% (accuracy threshold)")]
    if threshold > 50:
        items.append(("warn", f"{lo:g}% to < {threshold:g}%"))
    items += [("bad", f"< {lo:g}%"), ("na", "no score")]
    return '<div class="afc-legend">' + "".join(
        f'<span class="afc-band-{b}"><span class="afc-icon">{ICONS[b]}</span> {text}</span> ' for b, text in items) + "</div>"


def overview_html(run: FactCheckRun | None) -> str:
    """At-a-glance results of the newest parsed iteration: caveat, tiles, legend, claim cards, issues."""
    it = _latest(run)
    if it is None:
        msg = ("Checking — results appear here when the first iteration finishes." if run and run.status == "running"
               else "No parsed results; see the Report and Live log tabs." if run and run.iterations
               else "Run a fact-check to see the overview.")
        return f'<p class="afc-empty">{msg}</p>'
    s, thr = it.final.summary, run.config.accuracy_threshold
    acc = s.accuracy()
    reach = sum(band(c.accuracy_pct, thr) == "good" for c in s.claims)
    tiles = "".join([
        _tile("Overall accuracy", _pct(acc), "model-reported", _meter(acc, "overall accuracy"), f"afc-band-{band(acc, thr)}"),
        _tile("Overall confidence", _pct(s.overall_confidence_pct), "model-reported"),
        _tile("Claims", str(len(s.claims)), f"{reach} reach {thr:g}%"),
        _tile("Issues", str(len(s.issues)), "listed below" if s.issues else "none listed"),
        _tile("Known cost", f"${run.total_cost_usd:.4f}", f"{run.unknown_cost_calls} unknown-cost calls")])
    cards = "".join(_card(i, c, thr) for i, c in enumerate(s.claims, 1))
    issues = ("" if not s.issues else '<div><p class="afc-section-title">Issues</p><ul class="afc-issues">'
              + "".join(f"<li>{esc(x)}</li>" for x in s.issues) + "</ul></div>")
    more = (f'<p class="afc-note">{len(run.perspectives)} perspective call result(s) are in the Report tab.</p>'
            if run.perspectives else "")
    return (f'<div class="afc-overview"><p class="afc-caveat">Iteration {it.index}. Scores and confidence are '
            f'model-reported assessments, not verified correctness.</p><div class="afc-tiles">{tiles}</div>'
            f'{_legend(thr)}<div class="afc-cards">{cards}</div>{issues}{more}</div>')


def changes_html(run: FactCheckRun | None) -> str:
    """Word diff between the newest parsed iteration's input and its corrected text."""
    it = _latest(run)
    corrected = (it.final.summary.corrected_text or "").strip() if it else ""
    if not corrected:
        return '<p class="afc-empty">No corrected text yet.</p>'
    return (f'<div class="afc-changes"><p class="afc-section-title">Changes in iteration {it.index}: struck-through '
            f'words were removed, underlined words added</p>'
            f'<p class="afc-diff">{word_diff_html(it.input_text, corrected)}</p></div>')
