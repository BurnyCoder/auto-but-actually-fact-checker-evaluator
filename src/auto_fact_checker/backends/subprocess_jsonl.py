"""Windows-safe runner for agent CLIs that print JSON Lines (Claude Code stream-json, Codex --json).

Local: start the CLI without a shell, write the prompt to its stdin from a thread, read stdout line by line
(logging every line immediately), parse JSON lines into events, and kill the whole process tree on timeout or Stop.
Global context: claude_code.py and codex.py build the command line and interpret the events; this module is the
only place that spawns processes. References:
- subprocess (no shell, text/encoding, pipes): https://docs.python.org/3/library/subprocess.html
- Windows may launch .bat/.cmd files in a system shell whatever the arguments, which then re-parses them by shell
  rules without escaping, so resolve_exe() prefers name.exe and rejects batch shims:
  https://docs.python.org/3/library/subprocess.html#security-considerations
- psutil process-tree kill ("Kill a process tree" recipe): https://psutil.io/recipes/#controlling-processes
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..config import get_settings

KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY")


@dataclass
class ProcOutput:
    """Everything a CLI run produced: parsed events, all raw stdout/stderr lines, exit status."""

    events: list[dict] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)
    returncode: int | None = None
    timed_out: bool = False
    cancelled: bool = False


def resolve_exe(name: str, override: str | None = None) -> str:
    """Full path of a CLI executable; prefers name.exe and rejects .cmd/.bat shims, which Windows runs via cmd.exe."""
    path = override or shutil.which(f"{name}.exe") or shutil.which(name)
    if not path:
        raise FileNotFoundError(f"'{name}' CLI not found on PATH; install it or set {name.upper()}_BIN in .env")
    if path.lower().endswith((".cmd", ".bat")):
        raise RuntimeError(f"{path} is a batch shim; point {name.upper()}_BIN at the real executable")
    return path


def agent_env(agent_auth: str, keys: dict[str, str | None]) -> dict[str, str]:
    """Child environment: 'subscription' removes all API keys (CLI uses its login); 'api_key' injects `keys`."""
    env = {k: v for k, v in os.environ.items() if k not in KEY_VARS}
    if agent_auth == "api_key":
        env |= {k: v for k, v in keys.items() if v}
    env["PYTHONIOENCODING"] = "utf-8"  # harmless for non-Python children, avoids cp1252 in Python ones
    return env


def _descendants(pid: int) -> set[int]:
    """PIDs of all current descendants of pid (empty once it has exited)."""
    try:
        return {c.pid for c in psutil.Process(pid).children(recursive=True)}
    except psutil.NoSuchProcess:
        return set()


def _kill(pids) -> None:
    """Kill every listed process that still exists (agents start shells, subagents, search helpers)."""
    for pid in pids:
        try:
            psutil.Process(pid).kill()
        except psutil.NoSuchProcess:
            pass


def run_jsonl(cmd: list[str], stdin_text: str, env: dict | None, cwd: Path, timeout_s: int,
              log: logging.Logger | logging.LoggerAdapter, on_event=None,
              cancel: threading.Event | None = None) -> ProcOutput:
    """Run cmd, feed stdin_text, stream and log every output line; JSON lines become events (on_event callback)."""
    out = ProcOutput()
    log.info("Spawning: %s (cwd=%s, timeout=%ss)", " ".join(cmd), cwd, timeout_s)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env, bufsize=1)

    def feed():  # writing from a thread avoids a pipe deadlock when the child fills stdout first
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    reading_done = threading.Event()

    def watchdog():  # polls every 0.5 s until stdout is drained; kills the tree on timeout or UI Stop
        deadline, seen = time.monotonic() + timeout_s, set()
        while not reading_done.is_set():
            seen |= _descendants(proc.pid)  # remembered, so orphans still holding the pipe can be killed
            if cancel is not None and cancel.is_set():
                out.cancelled = True
                break
            if time.monotonic() > deadline:
                out.timed_out = True
                break
            time.sleep(0.5)
        if not reading_done.is_set():
            log.warning("Killing %s (%s)", cmd[0], "cancelled" if out.cancelled else "timeout")
            _kill(seen | _descendants(proc.pid) | {proc.pid})  # closing every writer ends the read loop

    threading.Thread(target=feed, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    for line in proc.stdout:  # yields lines as soon as the child flushes them -> realtime logs
        line = line.rstrip("\r\n")
        if not line:
            continue
        out.raw_lines.append(line)
        log.info("[%s] %s", Path(cmd[0]).stem, line)  # full line, never truncated
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # stderr noise / progress text stays in raw_lines and the log
        if isinstance(event, dict):
            out.events.append(event)
            if on_event:
                on_event(event)
    reading_done.set()
    out.returncode = proc.wait()
    log.info("%s exited with code %s", Path(cmd[0]).stem, out.returncode)
    return out


URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}\\|^`]+")  # good-enough URL matcher for tool outputs


def urls_in(text: str) -> list[str]:
    """URLs mentioned in free text (agent tool results / messages), trailing punctuation stripped."""
    return [u.rstrip(".,;:") for u in URL_RE.findall(text)]


def run_agent(req, log, *, exe_name: str, exe_override: str | None, keys: dict, build, parse):
    """Shared agent flow: resolve the CLI, fresh temp workdir, auth env, run, parse, annotate errors, clean up.

    build(req, exe, workdir) -> argv ; parse(req, events, billed) -> LLMResult. A fresh empty directory changes
    the agent's starting location; it does not prevent access to project files or provide a sandbox.
    """
    settings = get_settings()
    exe = resolve_exe(exe_name, exe_override)
    workdir = req.workdir or Path(tempfile.mkdtemp(prefix=f"afc_{exe_name}_"))
    t0 = time.monotonic()
    try:
        out = run_jsonl(build(req, exe, workdir), req.prompt, agent_env(settings.agent_auth, keys), workdir,
                        req.timeout_s, log, cancel=req.cancel)
    finally:
        if req.workdir is None:
            shutil.rmtree(workdir, ignore_errors=True)
    result = parse(req, out.events, billed=settings.agent_auth == "api_key")
    result.duration_s = time.monotonic() - t0
    if out.timed_out or out.cancelled:
        result.error = "timeout" if out.timed_out else "cancelled"
    elif out.returncode and not result.error:
        result.error = f"exit code {out.returncode}: " + " | ".join(out.raw_lines[-3:])
    return result
