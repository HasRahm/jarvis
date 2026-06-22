"""
Task Classifier for the Orchestrator.
Uses a 4-dimensional classification matrix to determine execution domain, complexity tier,
required context, and verification method before delegating any work.
"""
import sys
from core.trace import trace as _jtrace

CLASSIFICATION_PROMPT = """
You are the Chief Orchestrator of Jarvis OS.
A task has arrived. Classify it across four dimensions
before delegating to any agent.

Task: {task}

DIMENSION 1 — EXECUTION DOMAIN
Which domain does this task primarily live in?

  DESKTOP_AUTOMATION: anything requiring control of 
    the physical Windows machine — clicking, typing,
    navigating apps, reading screens, file management,
    system settings, process management
    → Route to: Gemma4 (openrouter/google/gemma-4-27b-it)
    
  FRONTEND_BUILD: UI components, React/HTML/CSS,
    visual design, Figma integration, user interfaces,
    layouts, animations, responsive design
    → Route to: Gemini 3.1 Pro Preview (best visual)
    
  BACKEND_BUILD: API routes, authentication, business
    logic, server code, integrations, security
    → Route to: Claude Sonnet 4.6 (best reasoning)
    
  DATABASE: schema design, SQL migrations, RLS
    policies, query optimization, data modeling
    → Route to: Claude Sonnet 4.6 + Supabase MCP
    
  RESEARCH: web search, data gathering, analysis,
    competitive intelligence, summarization
    → Route to: Claude Opus 4.8 (lowest hallucination)
    
  QA_TESTING: browser automation, test generation,
    visual verification, regression testing
    → Route to: GPT-5.4 (75% OSWorld, computer use)
    
  SYSTEM_HEALTH: disk cleanup, process management,
    performance monitoring, maintenance
    → Route to: Gemma4 (openrouter/google/gemma-4-27b-it)
    
  ORCHESTRATION_ONLY: task decomposition, planning,
    cross-agent coordination, project management
    → Handle myself

DIMENSION 2 — COMPLEXITY TIER
  TIER 1 — Single model, single pass (< 5 tool calls)
  TIER 2 — Single model, multi-step (5-20 tool calls)
  TIER 3 — Multi-agent sequential (agents depend on each other)
  TIER 4 — Multi-agent parallel (agents work simultaneously)

DIMENSION 3 — REQUIRED CONTEXT
  What must the receiving agent know before starting?
  List every piece of information they need:
  - Project structure and tech stack
  - What has already been built
  - API contracts from other agents
  - Design system and conventions
  - Acceptance criteria

DIMENSION 4 — VERIFICATION METHOD
  How will I know this subtask is complete?
  What command, check, or output proves success?

Return your final structured classification as JSON with the following keys:
- "domain"
- "tier"
- "context_needed"
- "verification"
"""

def get_classification_prompt(task: str) -> str:
    return CLASSIFICATION_PROMPT.format(task=task)


# Phase 41 — actual classify-and-route (was prompt-only before).
import os
import logging

logger = logging.getLogger(__name__)

VALID_DOMAINS = {
    "DESKTOP_AUTOMATION", "FRONTEND_BUILD", "BACKEND_BUILD", "DATABASE",
    "RESEARCH", "QA_TESTING", "SYSTEM_HEALTH", "ORCHESTRATION_ONLY",
}


def _heuristic(task: str) -> dict:
    """Fast keyword classifier — used as the CI mock and as a fallback when the LLM call fails
    or returns garbage. Token-boundary matching (NOT substring — 'api' must not match 'capital').
    Deterministic, zero-cost."""
    _jtrace(f"[TRACE] core.orchestrator.task_classifier._heuristic: enter")
    import re
    t = (task or "").lower()
    toks = set(re.findall(r"[a-z0-9]+", t))

    def has(*kw):
        return any(k in toks for k in kw)

    def phrase(*ph):
        return any(p in t for p in ph)

    if has("click", "spotify", "navigate", "screenshot", "desktop", "window", "scroll") \
            or phrase("open ", "type ", "press ", " play "):
        domain = "DESKTOP_AUTOMATION"
    elif has("disk",) or phrase("clean up", "cleanup", "free up", "kill process", "memory usage",
                                "performance monitor", "maintenance", "system health"):
        domain = "SYSTEM_HEALTH"
    elif has("research", "summarize", "competitive") \
            or phrase("search the web", "look up", "find information", "gather data"):
        domain = "RESEARCH"
    elif has("schema", "migration", "sql", "rls") or phrase("table design", "data model"):
        domain = "DATABASE"
    elif has("qa", "regression", "tests") or phrase("verify the", "test that"):
        domain = "QA_TESTING"
    elif has("ui", "frontend", "css", "react", "button", "layout", "page") \
            or phrase("landing page", "design a ui"):
        domain = "FRONTEND_BUILD"
    elif has("api", "backend", "endpoint", "server", "auth"):
        domain = "BACKEND_BUILD"
    elif has("build", "create", "make", "app", "website", "tool", "game", "dashboard", "bot", "cli"):
        domain = "ORCHESTRATION_ONLY"
    else:
        domain = "ORCHESTRATION_ONLY"
    return {"domain": domain, "tier": "TIER 1", "context_needed": [], "verification": "output produced"}


def classify(task: str) -> dict:
    """Classify a task across the 4 dimensions. Returns {domain, tier, context_needed, verification}.

    Uses the chief-orchestrator model (Kimi K2.6) when available; CI-safe (heuristic mock under
    JARVIS_CI) and never raises (falls back to the heuristic on any failure)."""
    _jtrace(f"[TRACE] core.orchestrator.task_classifier.classify: enter")
    if os.environ.get("JARVIS_CI") == "true":
        return _heuristic(task)
    try:
        from agents.model_router import get_model, get_provider
        from agents.base_agent import BaseAgent
        from agents.frontend_agent import safe_parse_response

        class _Classifier(BaseAgent):
            def __init__(self):
                self.role = "orchestrator"
                self.model = get_model("orchestrator")
                self.provider = get_provider(self.model)
                self.max_retries = 2

            def run(self, t):
                pass

        agent = _Classifier()
        raw = agent._call_model(get_classification_prompt(task), task)
        result = safe_parse_response(raw)
        if isinstance(result, dict):
            dom = str(result.get("domain", "")).upper().strip()
            if dom in VALID_DOMAINS:
                result["domain"] = dom
                return result
    except Exception as e:
        _jtrace(f"[TRACE] core.orchestrator.task_classifier.classify: except {str(e)[:80]}")
        logger.warning(f"[task_classifier] classify failed ({e}); using heuristic")
    return _heuristic(task)
