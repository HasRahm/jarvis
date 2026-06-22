"""
intent_router.py — zero-LLM coding intent classifier.

Runs before every REPL turn to detect whether the user wants to BUILD something.
Returns routing guidance so _agent_turn can inject a hard coding mandate into the
system message, guaranteeing the model uses run_frontend_agent / run_backend_agent /
delegate_task instead of answering conversationally.

No API calls, no imports beyond stdlib re. Runs in < 1 ms.
"""
import sys
from core.trace import trace as _jtrace
import re

# Verbs that signal "build something"
_BUILD_VERBS = {
    "create", "build", "make", "write", "develop", "generate", "implement",
    "code", "program", "scaffold", "design", "produce", "construct", "assemble",
    "add", "set up", "setup", "initialize", "init", "start", "bootstrap",
    "need", "want", "get",  # "i need a backend", "i want a website"
}

# Nouns that signal "a software artifact"
_BUILD_NOUNS = {
    "game", "app", "application", "website", "site", "webpage", "web page",
    "script", "tool", "api", "server", "backend", "frontend", "bot", "cli",
    "dashboard", "plugin", "extension", "function", "class", "module",
    "component", "page", "endpoint", "service", "library", "package",
    "database", "schema", "migration", "test", "spec", "pipeline",
    "chatbot", "discord bot", "telegram bot", "slackbot",
    "calculator", "todo", "to-do", "tracker", "blog", "portfolio",
    "snake", "tetris", "pong", "platformer", "rpg", "pokemon",
}

# Frontend signals (suggests run_frontend_agent)
_FRONTEND_SIGNALS = {
    "frontend", "ui", "html", "css", "react", "vue", "svelte", "angular",
    "page", "website", "site", "dashboard", "component", "canvas", "game",
    "pygame", "phaser", "pixi", "animation", "chart", "tailwind", "bootstrap",
    "nextjs", "next.js", "remix", "vite",
}

# Backend signals (suggests run_backend_agent)
_BACKEND_SIGNALS = {
    "backend", "api", "server", "database", "db", "sql", "postgres", "mysql",
    "sqlite", "mongodb", "endpoint", "rest", "graphql", "fastapi", "django",
    "flask", "express", "node", "auth", "jwt", "oauth", "migration", "schema",
    "redis", "celery", "queue", "websocket",
}

# Full-stack trigger — when BOTH backend+frontend are present, or explicit keywords
_FULLSTACK_SIGNALS = {"full-stack", "fullstack", "full stack", "end-to-end", "complete app"}

# Pure question words — when the sentence OPENS with one of these it's a question, not a request.
_QUESTION_STARTERS = {
    "why", "what", "how", "when", "where", "who", "which", "whom",
    "is", "are", "was", "were", "does", "did", "explain", "tell",
}

# Phrases that override the question-starter check and still mean "build this"
_REQUEST_OVERRIDES = {
    "can you", "could you", "please", "i want", "i need",
    "help me build", "help me create", "help me make",
}

# Complaint/meta-question phrases — always general regardless of nouns/verbs.
_COMPLAINT_PHRASES = {
    "why are you", "why the hell", "why did you", "why is it", "why isn't",
    "why aren't", "what happened", "what are you doing", "stop ", "don't ",
    "you already", "already built", "already created", "already made",
    "have build", "have built", "have made", "have created",
}


def _is_question(text: str) -> bool:
    """Return True when the text is clearly a question or complaint, not a build request."""
    _jtrace(f"[TRACE] core.orchestrator.intent_router._is_question: enter")
    lower = text.strip().lower()
    # Ends with a question mark — almost always a question.
    if lower.endswith("?"):
        return True
    # Contains a complaint/meta-question phrase.
    if any(phrase in lower for phrase in _COMPLAINT_PHRASES):
        return True
    # Starts with a pure question word AND no explicit request override follows.
    first = lower.split()[0] if lower.split() else ""
    if first in _QUESTION_STARTERS:
        if not any(lower.startswith(r) for r in _REQUEST_OVERRIDES):
            return True
    return False


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][\w\-\.]*", text.lower()))


def classify(text: str) -> dict:
    """Classify a user prompt and return routing guidance.

    Returns:
        {
            "mode": "coding" | "general",
            "agents": list[str],     # suggested tool names, in call order
            "mandate": str,          # text to prepend to system message (coding only)
            "rationale": str,
        }
    """
    # Hard veto: questions and complaints are never build tasks, even if they mention
    # verbs like "create" or nouns like "game".  "why are you creating a game" is a
    # question about past behaviour, not a request to build one.
    _jtrace(f"[TRACE] core.orchestrator.intent_router.classify: enter")
    if _is_question(text):
        return {"mode": "general", "agents": [], "mandate": "", "rationale": "question/complaint detected"}

    words = _tokens(text)
    lower = text.lower()

    # Check verb + noun co-occurrence
    has_verb = bool(words & _BUILD_VERBS)
    has_noun = bool(words & _BUILD_NOUNS)

    # Multi-word noun phrases
    if not has_noun:
        has_noun = any(phrase in lower for phrase in {"web page", "full stack", "to-do"})

    if not (has_verb and has_noun):
        return {"mode": "general", "agents": [], "mandate": "", "rationale": "no build verb+noun pair"}

    # Determine which agents to suggest
    has_frontend = bool(words & _FRONTEND_SIGNALS)
    has_backend = bool(words & _BACKEND_SIGNALS)
    has_fullstack = any(phrase in lower for phrase in _FULLSTACK_SIGNALS) or (has_frontend and has_backend)

    if has_fullstack:
        agents = ["delegate_task"]
        primary_call = "delegate_task"
        detail = "full-stack project detected"
    elif has_backend and not has_frontend:
        agents = ["run_backend_agent", "run_qa_agent"]
        primary_call = "run_backend_agent"
        detail = "backend-only signals"
    else:
        # Default: frontend first (games, scripts, pure UI — most common case)
        agents = ["run_frontend_agent", "run_qa_agent"]
        primary_call = "run_frontend_agent"
        detail = "frontend/game/script signals (or ambiguous — defaulting to frontend)"

    mandate = _build_mandate(text, agents, primary_call)

    return {
        "mode": "coding",
        "agents": agents,
        "mandate": mandate,
        "rationale": f"build verb+noun detected; {detail}",
    }


def route(task: str) -> dict:
    """Office execution router (Phase 41). Combines the fast coding-intent classifier with a
    keyword domain heuristic to choose an execution PATH. Zero-LLM, <1ms, free — the richer
    LLM classifier (task_classifier.classify) is reserved for the architect, where its cost is
    justified.

    Returns {"path", "domain", "mode", "agents", "mandate"} where path ∈
    {"desktop", "build", "research", "qa", "chat"}.
    """
    _jtrace(f"[TRACE] core.orchestrator.intent_router.route: enter")
    intent = classify(task)
    try:
        from core.orchestrator.task_classifier import _heuristic
        domain = _heuristic(task)["domain"]
    except Exception:
        _jtrace(f"[TRACE] core.orchestrator.intent_router.route: except Exception")
        domain = "ORCHESTRATION_ONLY"

    if domain in ("DESKTOP_AUTOMATION", "SYSTEM_HEALTH"):
        path = "desktop"               # local gemma desktop loop (free, private)
    elif intent["mode"] == "coding" or domain in ("FRONTEND_BUILD", "BACKEND_BUILD", "DATABASE"):
        path = "build"                 # the DAG (architect → assignments → agents)
    elif domain == "RESEARCH":
        path = "research"
    elif domain == "QA_TESTING":
        path = "qa"
    else:
        # ORCHESTRATION_ONLY is the heuristic's catch-all; without a coding intent it's just chat.
        path = "chat"                  # plain conversational answer

    return {
        "path": path,
        "domain": domain,
        "mode": intent["mode"],
        "agents": intent.get("agents", []),
        "mandate": intent.get("mandate", ""),
    }


def _build_mandate(task: str, agents: list[str], primary_call: str) -> str:
    _jtrace(f"[TRACE] core.orchestrator.intent_router._build_mandate: enter")
    agent_guide = (
        "  - run_frontend_agent  → UI, games, websites, HTML/CSS/JS, React, Pygame, canvas\n"
        "  - run_backend_agent   → APIs, servers, Python/Node backends, databases, SQL\n"
        "  - run_qa_agent        → testing and verification after building\n"
        "  - delegate_task       → full-stack apps that need backend + frontend coordinated"
    )
    first_verb = f"Call {primary_call} NOW" if len(agents) == 1 else \
        f"Call {agents[0]} first, then {agents[1]} after it finishes"

    return (
        "\n\n<CODING_MANDATE>\n"
        "The user has asked you to BUILD software. This is a CODING TASK.\n"
        "RULES:\n"
        "  1. Do NOT explain, describe, or write a guide. Build it.\n"
        "  2. Do NOT ask for confirmation or clarification before starting.\n"
        "  3. You MUST call a coding tool immediately.\n"
        "  4. Write all generated code to files under workspaces/ using write_file.\n"
        "  5. After building, call run_qa_agent to verify the output.\n\n"
        "AVAILABLE CODING TOOLS:\n"
        f"{agent_guide}\n\n"
        f"ACTION: {first_verb} with the full task description below.\n"
        "</CODING_MANDATE>\n"
    )
