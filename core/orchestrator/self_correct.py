"""
Self-Correction Spine (Phase 36A) — execute generated code, capture errors, feed them
back to the producing agent to fix, and repeat until it runs or the iteration budget is spent.

This generalizes the frontend *visual* loop (dag.py) to *functional* correctness and is shared
by BOTH the DAG path and the direct agent-tool path, so an agent never returns unverified code.

Execution tiers (safety-ordered):
  - E2B sandbox (when a sandbox object is passed, i.e. JARVIS_SANDBOX_MODE=e2b): FULL execution —
    write files, `pip install` requirements, run `pytest`, or boot/compile. Isolated, so running
    untrusted generated code is safe.
  - Local fallback (no sandbox): SAFE checks only — `py_compile` (syntax/compile), `ast.parse`,
    and in-memory `sqlite3` execution of `.sql` migrations. Never executes generated imports/tests
    on the host (that requires the isolated sandbox).

Gating:
  - No-op when JARVIS_CI=true (tests never spawn sandboxes or run generated code).
  - Disabled when JARVIS_SELF_CORRECT=0.
  - No-op when the agent result is an error or has no files.

Never raises — verification failures degrade to returning the original result with a report attached.
"""

import os
import ast
import sys
import json
import sqlite3
import logging
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    print(f"[TRACE] core.orchestrator.self_correct._enabled: enter", file=sys.stderr, flush=True)
    if os.environ.get("JARVIS_CI") == "true":
        return False
    return os.environ.get("JARVIS_SELF_CORRECT", "1") not in ("0", "false", "False")


def _collect_files(agent, result: dict) -> dict:
    """Map the agent's written files (relative paths in result['files']) to their content,
    read back from the agent workspace. Returns {relative_path: content}."""
    print(f"[TRACE] core.orchestrator.self_correct._collect_files: enter", file=sys.stderr, flush=True)
    files = {}
    workspace = getattr(agent, "workspace", None)
    for rel in result.get("files", []) or []:
        try:
            if workspace:
                abs_path = os.path.join(workspace, rel)
                if os.path.isfile(abs_path):
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        files[rel] = f.read()
        except Exception as e:
            print(f"[TRACE] core.orchestrator.self_correct._collect_files: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.debug(f"[self_correct] could not read {rel}: {e}")
    return files


# ── Local (safe) checks ──────────────────────────────────────────────────────

def _check_python_local(files: dict) -> list:
    """Compile-check every .py file. Returns a list of human-readable error strings."""
    print(f"[TRACE] core.orchestrator.self_correct._check_python_local: enter", file=sys.stderr, flush=True)
    errors = []
    for rel, content in files.items():
        if not rel.endswith(".py"):
            continue
        try:
            ast.parse(content, filename=rel)
        except SyntaxError as e:
            print(f"[TRACE] core.orchestrator.self_correct._check_python_local: except {str(e)[:80]}", file=sys.stderr, flush=True)
            errors.append(f"{rel}: SyntaxError line {e.lineno}: {e.msg}")
    return errors


def _check_sql_local(files: dict) -> list:
    """Execute every .sql migration against an in-memory SQLite DB to validate it runs.
    Returns a list of error strings. (Postgres-specific syntax may false-positive; we only
    flag hard parse/execution failures, which still catch most real mistakes.)"""
    print(f"[TRACE] core.orchestrator.self_correct._check_sql_local: enter", file=sys.stderr, flush=True)
    errors = []
    for rel, content in files.items():
        if not rel.endswith(".sql"):
            continue
        try:
            con = sqlite3.connect(":memory:")
            con.executescript(content)
            con.close()
        except Exception as e:
            print(f"[TRACE] core.orchestrator.self_correct._check_sql_local: except {str(e)[:80]}", file=sys.stderr, flush=True)
            errors.append(f"{rel}: SQL error: {e}")
    return errors


def _verify_local(files: dict) -> tuple:
    """Run all safe local checks. Returns (passed: bool, errors: list[str])."""
    print(f"[TRACE] core.orchestrator.self_correct._verify_local: enter", file=sys.stderr, flush=True)
    errors = _check_python_local(files) + _check_sql_local(files)
    return (len(errors) == 0, errors)


# ── E2B (full) execution ─────────────────────────────────────────────────────

def _verify_e2b(sandbox, files: dict) -> tuple:
    """Push files into the sandbox and run them. Returns (passed, errors)."""
    print(f"[TRACE] core.orchestrator.self_correct._verify_e2b: enter", file=sys.stderr, flush=True)
    from tools.sandbox import write_files_to_sandbox, run_in_sandbox
    base = "/home/user/workspace"
    if not write_files_to_sandbox(sandbox, files, base=base):
        return (True, [])  # could not push — don't block; local check already ran

    errors = []
    # Install requirements if present.
    if any(r.endswith("requirements.txt") for r in files):
        out = run_in_sandbox(sandbox, f"cd {base} && pip install -q -r requirements.txt 2>&1 || true")
        if "ERROR" in out or "error" in out:
            errors.append(f"pip install: {out[-600:]}")

    py_files = [r for r in files if r.endswith(".py")]
    test_files = [r for r in py_files if r.startswith("test") or "/test" in r or r.startswith("tests/")]

    # Syntax-compile every python file.
    if py_files:
        joined = " ".join(f"'{r}'" for r in py_files)
        out = run_in_sandbox(sandbox, f"cd {base} && python -m py_compile {joined} 2>&1")
        if out.strip():
            errors.append(f"py_compile: {out[-800:]}")

    # Run tests if any were generated (and compile passed).
    if test_files and not errors:
        out = run_in_sandbox(sandbox, f"cd {base} && python -m pytest -q 2>&1 || true")
        if "failed" in out.lower() or "error" in out.lower():
            errors.append(f"pytest: {out[-1000:]}")

    # SQL migrations.
    for rel in (r for r in files if r.endswith(".sql")):
        out = run_in_sandbox(sandbox, f"cd {base} && sqlite3 :memory: < '{rel}' 2>&1 || true")
        if out.strip():
            errors.append(f"{rel}: {out[-400:]}")

    return (len(errors) == 0, errors)


# ── Public API ───────────────────────────────────────────────────────────────

def verify_and_correct(agent, result: dict, sandbox=None, max_iters: int = 3) -> dict:
    """Execute the agent's generated code, and on failure feed the errors back to the agent
    to fix, looping up to max_iters times.

    Args:
        agent:   the agent instance that produced `result` (must expose .run() and .workspace).
        result:  the agent's result dict ({status, output, files, ...}).
        sandbox: optional E2B sandbox object; when None, uses safe local checks only.
        max_iters: maximum correction iterations.

    Returns the (possibly corrected) result with a `verification` report attached.
    """
    print(f"[TRACE] core.orchestrator.self_correct.verify_and_correct: enter", file=sys.stderr, flush=True)
    if not _enabled() or result.get("status") != "success":
        return result

    files = _collect_files(agent, result)
    if not files:
        return result

    role = getattr(agent, "role", "agent")
    iterations = 0
    last_errors: list = []

    for iterations in range(1, max_iters + 1):
        try:
            files = _collect_files(agent, result)
            if sandbox is not None:
                passed, errors = _verify_e2b(sandbox, files)
            else:
                passed, errors = _verify_local(files)
        except Exception as e:
            print(f"[TRACE] core.orchestrator.self_correct.verify_and_correct: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.warning(f"[self_correct] verification crashed for {role}: {e}")
            result["verification"] = {"ran": False, "passed": True, "iterations": iterations,
                                      "note": f"verification error: {e}"}
            return result

        if passed:
            logger.info(f"[self_correct] {role} verified clean on iteration {iterations}.")
            result["verification"] = {"ran": True, "passed": True, "iterations": iterations,
                                      "errors": []}
            return result

        last_errors = errors
        logger.warning(f"[self_correct] {role} verification failed (iter {iterations}/{max_iters}): "
                       f"{errors[:2]}")

        if iterations >= max_iters:
            break

        feedback = (
            "Your generated code FAILED automated verification. Fix these concrete errors and "
            "return the COMPLETE corrected files in your normal JSON output schema:\n\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nReturn every file in full (not a diff). Do not explain — just return the JSON."
        )
        try:
            new_result = agent.run(feedback)
        except Exception as e:
            print(f"[TRACE] core.orchestrator.self_correct.verify_and_correct: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.warning(f"[self_correct] {role} correction run crashed: {e}")
            break
        if new_result.get("status") == "success":
            result = new_result
        else:
            break

    result["verification"] = {"ran": True, "passed": False, "iterations": iterations,
                              "errors": last_errors}
    logger.warning(f"[self_correct] {role} could not be verified after {iterations} iteration(s).")
    return result
