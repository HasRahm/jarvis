"""
Architect (Phase 36C) — produce a verifiable SPEC artifact BEFORE any coding, so every agent
builds against one coherent blueprint instead of improvising in isolation.

This is the "Artifacts / Implementation Plan" pattern the leading agentic IDEs (Antigravity) use:
an upfront, reviewable plan (architecture, data model, API contract, design system, file plan, and
acceptance criteria) that grounds decomposition and feeds the self-correction loop's "what does
working mean" bar.

`produce_spec()` writes SPEC.md (sibling of AGENTS.md) and returns the structured dict. CI-safe:
returns a deterministic mock and writes a mock SPEC.md when JARVIS_CI=true. Never raises — on any
failure it returns a minimal spec so the DAG can still proceed.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC_MD_PATH = os.path.join(_PROJECT_ROOT, "SPEC.md")

ARCHITECT_PROMPT = """You are a principal software architect. Given a build request, produce a concise
but complete implementation SPEC that frontend, backend, and QA agents will build against.

Return ONLY this JSON object (no markdown fences, no prose outside the JSON):
{
  "title": "short project title",
  "summary": "1-2 sentence description of what is being built",
  "stack": {"frontend": "...", "backend": "...", "database": "..."},
  "data_model": [
    {"table": "users", "columns": ["id PK", "email unique", "created_at"], "notes": "..."}
  ],
  "api_contract": [
    {"method": "POST", "path": "/api/users", "body": {"email": "string"}, "response": {"id": 1, "email": "string"}}
  ],
  "design": {"theme": "aurora|warmsand|mono", "notes": "key UI screens and aesthetic direction"},
  "files": ["index.html", "app/main.py", "migrations/001_init.sql", "..."],
  "acceptance_criteria": [
    "Concrete, checkable statements of what 'done and working' means — e.g. 'POST /api/users returns 201 and persists a row'"
  ],
  "assignments": [
    {"id": "sub_1", "agent": "database", "depends_on": [], "scope": "what this agent builds",
     "acceptance": "verifiable success condition"},
    {"id": "sub_2", "agent": "backend", "depends_on": ["sub_1"], "scope": "...", "acceptance": "..."},
    {"id": "sub_3", "agent": "frontend", "depends_on": ["sub_1"], "scope": "...", "acceptance": "..."},
    {"id": "sub_4", "agent": "qa", "depends_on": ["sub_2", "sub_3"], "scope": "...", "acceptance": "..."}
  ]
}

Rules:
- The api_contract and data_model MUST be internally consistent (every endpoint's fields exist in the model).
- agent in each assignment MUST be one of: database, backend, frontend, qa, research.
- Order assignments so dependencies are correct: database → backend/frontend (parallel) → qa.
  Omit roles the task doesn't need (e.g. no database for a static page).
- Pick a design.theme from the three allowed values that best fits the product.
- acceptance_criteria must be concrete and verifiable (these drive automated checks).
- Keep it tight — only what's needed to build this request. Return ONLY the JSON object."""


def _mock_spec(user_task: str) -> dict:
    return {
        "title": "Mock Project",
        "summary": user_task[:120],
        "stack": {"frontend": "HTML/CSS/JS", "backend": "FastAPI", "database": "SQLite"},
        "data_model": [{"table": "users", "columns": ["id PK", "email unique", "created_at"], "notes": ""}],
        "api_contract": [{"method": "POST", "path": "/api/users", "body": {"email": "string"},
                          "response": {"id": 1, "email": "string"}}],
        "design": {"theme": "aurora", "notes": "single page"},
        "files": ["index.html", "app/main.py", "migrations/001_init.sql"],
        "acceptance_criteria": ["POST /api/users returns 201 and persists a row"],
        "assignments": [
            {"id": "sub_1", "agent": "database", "depends_on": [],
             "scope": "users table migration", "acceptance": "migration runs in sqlite"},
            {"id": "sub_2", "agent": "backend", "depends_on": ["sub_1"],
             "scope": "POST /api/users", "acceptance": "returns 201"},
            {"id": "sub_3", "agent": "frontend", "depends_on": ["sub_1"],
             "scope": "signup UI", "acceptance": "renders and calls the API"},
            {"id": "sub_4", "agent": "qa", "depends_on": ["sub_2", "sub_3"],
             "scope": "integration test", "acceptance": "all checks pass"},
        ],
    }


_BUILD_AGENTS = {"database", "backend", "frontend", "qa", "research"}


def _finalize_assignments(spec: dict) -> list:
    """Return the spec's agent assignments — validated, synthesized when absent, each tagged with
    the cost-optimized model for its role (via model_router). This is the "office meeting" output
    the DAG executes from."""
    from agents.model_router import get_model

    raw = spec.get("assignments")
    assignments = []
    if isinstance(raw, list) and raw:
        for i, a in enumerate(raw, 1):
            if not isinstance(a, dict):
                continue
            agent = str(a.get("agent", "")).lower().strip()
            if agent not in _BUILD_AGENTS:
                continue
            assignments.append({
                "id": a.get("id") or f"sub_{i}",
                "agent": agent,
                "depends_on": a.get("depends_on") or [],
                "scope": a.get("scope", ""),
                "acceptance": a.get("acceptance", ""),
            })

    if not assignments:
        # Synthesize a sensible default chain from the spec shape.
        has_db = bool(spec.get("data_model"))
        has_api = bool(spec.get("api_contract"))
        n = 0
        db_id = be_id = fe_id = None
        if has_db:
            n += 1; db_id = f"sub_{n}"
            assignments.append({"id": db_id, "agent": "database", "depends_on": [],
                                "scope": "data schema + migrations", "acceptance": "migration runs"})
        if has_api:
            n += 1; be_id = f"sub_{n}"
            assignments.append({"id": be_id, "agent": "backend",
                                "depends_on": [db_id] if db_id else [],
                                "scope": "API + business logic", "acceptance": "endpoints respond"})
        n += 1; fe_id = f"sub_{n}"
        assignments.append({"id": fe_id, "agent": "frontend",
                            "depends_on": [db_id] if db_id else [],
                            "scope": "UI wired to the contract", "acceptance": "renders + calls API"})
        n += 1
        assignments.append({"id": f"sub_{n}", "agent": "qa",
                            "depends_on": [x for x in (be_id, fe_id) if x],
                            "scope": "integration test + visual check", "acceptance": "all checks pass"})

    # Tag each with its cost-optimized model.
    for a in assignments:
        a["model"] = get_model(a["agent"])
    return assignments


def _render_markdown(spec: dict) -> str:
    """Render the spec dict as a human-reviewable SPEC.md artifact."""
    lines = [f"# SPEC — {spec.get('title', 'Project')}", "",
             spec.get("summary", ""), "", "## Stack"]
    for k, v in (spec.get("stack") or {}).items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Data Model"]
    for t in spec.get("data_model") or []:
        cols = ", ".join(t.get("columns", []))
        lines.append(f"- **{t.get('table')}** ({cols}) {('— ' + t['notes']) if t.get('notes') else ''}")
    lines += ["", "## API Contract"]
    for e in spec.get("api_contract") or []:
        lines.append(f"- `{e.get('method')} {e.get('path')}` body={json.dumps(e.get('body', {}))} "
                     f"→ {json.dumps(e.get('response', {}))}")
    d = spec.get("design") or {}
    lines += ["", "## Design", f"- Theme: **{d.get('theme', 'aurora')}** — {d.get('notes', '')}"]
    lines += ["", "## Files"]
    for f in spec.get("files") or []:
        lines.append(f"- `{f}`")
    lines += ["", "## Acceptance Criteria"]
    for c in spec.get("acceptance_criteria") or []:
        lines.append(f"- [ ] {c}")
    if spec.get("assignments"):
        lines += ["", "## Office Brief — Agent Assignments"]
        for a in spec["assignments"]:
            deps = ", ".join(a.get("depends_on", [])) or "none"
            lines.append(f"- **{a.get('id')}** [{a.get('agent')} · `{a.get('model','?')}`] "
                         f"depends on: {deps} — {a.get('scope','')}")
    lines.append("")
    return "\n".join(lines)


def _write_spec_md(spec: dict) -> None:
    try:
        with open(SPEC_MD_PATH, "w", encoding="utf-8") as f:
            f.write(_render_markdown(spec))
    except Exception as e:
        logger.warning(f"[architect] could not write SPEC.md: {e}")


def produce_spec(user_task: str, user_id: str | None = None) -> dict:
    """Produce and persist a SPEC artifact for the user task. Returns the spec dict."""
    if os.environ.get("JARVIS_CI") == "true":
        spec = _mock_spec(user_task)
        spec["assignments"] = _finalize_assignments(spec)
        _write_spec_md(spec)
        return spec

    try:
        from agents.model_router import get_model, get_provider
        from agents.base_agent import BaseAgent
        from agents.frontend_agent import safe_parse_response

        class _ArchitectAgent(BaseAgent):
            def __init__(self):
                self.role = "orchestrator"
                self.model = get_model("orchestrator")
                self.provider = get_provider(self.model)
                self.max_retries = 3

            def run(self, task):
                pass

        agent = _ArchitectAgent()
        logger.info(f"[architect] Producing SPEC with {agent.model} via {agent.provider}...")
        raw = agent._call_model(ARCHITECT_PROMPT, user_task)
        spec = safe_parse_response(raw)
        if not isinstance(spec, dict):
            raise ValueError("architect returned non-dict spec")
        spec["assignments"] = _finalize_assignments(spec)
        _write_spec_md(spec)
        logger.info(f"[architect] SPEC produced: {spec.get('title', 'untitled')} "
                    f"({len(spec.get('api_contract', []))} endpoints, "
                    f"{len(spec.get('assignments', []))} agent assignments)")
        return spec
    except Exception as e:
        logger.warning(f"[architect] SPEC generation failed ({e}); proceeding with minimal spec.")
        spec = _mock_spec(user_task)
        spec["assignments"] = _finalize_assignments(spec)
        _write_spec_md(spec)
        return spec
