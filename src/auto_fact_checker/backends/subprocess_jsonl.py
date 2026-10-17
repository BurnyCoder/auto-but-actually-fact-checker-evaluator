"""Windows-safe runner for agent CLIs that print JSON Lines (Claude Code stream-json, Codex --json).

Local: start the CLI without a shell, write the prompt to its stdin from a thread, read stdout line by line
(logging every line immediately), parse JSON lines into events, and kill the whole process tree on timeout or Stop.
Global context: claude_code.py and codex.py build the command line and interpret the events; this module is the
only place that spawns processes. References:
- subprocess (no shell, text/encoding, pipes): https://docs.python.org/3/library/subprocess.html
- Windows CreateProcess cannot run .cmd shims without cmd.exe, hence resolve_exe() insists on .exe files:
  https://docs.python.org/3/library/subprocess.html#converting-argument-sequence
- psutil process-tree kill: https://psutil.readthedocs.io/en/latest/#kill-process-tree
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
    """Full path of a CLI executable; prefers name.exe because .cmd/.bat shims need a shell on Windows."""
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


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the CLI and every child it spawned (agents start shells, subagents, search helpers)."""
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
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

    def watchdog():  # polls every 0.5 s: kill the tree on timeout or when the UI's Stop button sets `cancel`
        deadline = time.monotonic() + timeout_s
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                out.cancelled = True
                break
            if time.monotonic() > deadline:
                out.timed_out = True
                break
            time.sleep(0.5)
        if proc.poll() is None:
            log.warning("Killing %s (%s)", cmd[0], "cancelled" if out.cancelled else "timeout")
            _kill_tree(proc)  # closing the child's stdout ends the read loop below

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
    out.returncode = proc.wait()
    log.info("%s exited with code %s", Path(cmd[0]).stem, out.returncode)
    return out


URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}\\|^`]+")  # good-enough URL matcher for tool outputs


def urls_in(text: str) -> list[str]:
    """URLs mentioned in free text (agent tool results / messages), trailing punctuation stripped."""
    return [u.rstrip(".,;:") for u in URL_RE.findall(text)]


def run_agent(req, log, *, exe_name: str, exe_override: str | None, keys: dict, build, parse):
    """Shared agent flow: resolve the CLI, fresh temp workdir, auth env, run, parse, annotate errors, clean up.

    build(req, exe, workdir) -> argv ; parse(req, events, billed) -> LLMResult. A fresh empty directory keeps
    the agent away from this repo's AGENTS.md/CLAUDE.md and any project files.
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
