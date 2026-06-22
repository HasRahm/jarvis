"""
Agent Tools — thin wrappers exposing coding agents and skills as orchestrator-callable tools.

Each function lazy-imports the agent to avoid circular imports and returns json.dumps(result)
so the Hermes orchestrator receives a plain string tool result it can embed in context.
"""
import sys

import json
import logging
import os
from core.cli import run_events as ev

logger = logging.getLogger(__name__)


def _self_correct(agent, result: dict) -> dict:
    """Run the shared self-correction spine on a direct-tool agent result.

    Provisions an ephemeral sandbox (E2B when JARVIS_SANDBOX_MODE=e2b, else None → safe local
    checks). No-op in CI or when JARVIS_SELF_CORRECT=0. Never raises."""
    print(f"[TRACE] agents.agent_tools._self_correct: enter", file=sys.stderr, flush=True)
    if os.environ.get("JARVIS_CI") == "true" or os.environ.get("JARVIS_SELF_CORRECT", "1") in ("0", "false", "False"):
        return result
    sandbox = None
    try:
        from core.orchestrator.self_correct import verify_and_correct
        from tools.sandbox import create_sandbox, destroy_sandbox
        sandbox = create_sandbox(f"tool_{agent.role}")
        return verify_and_correct(agent, result, sandbox=sandbox)
    except Exception as e:
        print(f"[TRACE] agents.agent_tools._self_correct: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[agent_tools] self-correction skipped: {e}")
        return result
    finally:
        try:
            if sandbox is not None:
                from tools.sandbox import destroy_sandbox
                destroy_sandbox(sandbox, f"tool_{agent.role}")
        except Exception:
            print(f"[TRACE] agents.agent_tools._self_correct: except Exception", file=sys.stderr, flush=True)
            pass


def run_backend_agent(task: str, user_id: str | None = None) -> str:
    """Invoke the BackendAgent for API routes, SQL migrations, and server logic."""
    print(f"[TRACE] agents.agent_tools.run_backend_agent: enter", file=sys.stderr, flush=True)
    ev.emit("agent_started", agent="backend", detail="working...")
    try:
        from agents.backend_agent import BackendAgent
        agent = BackendAgent(user_id=user_id)
        result = _self_correct(agent, agent.run(task))
        ev.emit("agent_finished", agent="backend", detail="done")
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.run_backend_agent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        ev.emit("agent_failed", agent="backend", detail=str(e)[:48])
        logger.error(f"[agent_tools] run_backend_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_frontend_agent(task: str, user_id: str | None = None) -> str:
    """Invoke the FrontendAgent for HTML, CSS, JavaScript, and UI generation."""
    print(f"[TRACE] agents.agent_tools.run_frontend_agent: enter", file=sys.stderr, flush=True)
    ev.emit("agent_started", agent="frontend", detail="working...")
    try:
        from agents.frontend_agent import FrontendAgent
        agent = FrontendAgent(user_id=user_id)
        result = _self_correct(agent, agent.run(task))
        ev.emit("agent_finished", agent="frontend", detail="done")
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.run_frontend_agent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        ev.emit("agent_failed", agent="frontend", detail=str(e)[:48])
        logger.error(f"[agent_tools] run_frontend_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_qa_agent(task: str, user_id: str | None = None) -> str:
    """Invoke the QAAgent for code review, testing, and verification."""
    print(f"[TRACE] agents.agent_tools.run_qa_agent: enter", file=sys.stderr, flush=True)
    ev.emit("agent_started", agent="qa", detail="working...")
    try:
        from agents.qa_agent import QAAgent
        agent = QAAgent(user_id=user_id)
        result = _self_correct(agent, agent.run(task))
        ev.emit("agent_finished", agent="qa", detail="done")
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.run_qa_agent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        ev.emit("agent_failed", agent="qa", detail=str(e)[:48])
        logger.error(f"[agent_tools] run_qa_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_iac_agent(task: str) -> str:
    """Invoke the IacAgent for Terraform infrastructure and system configuration."""
    print(f"[TRACE] agents.agent_tools.run_iac_agent: enter", file=sys.stderr, flush=True)
    ev.emit("agent_started", agent="iac", detail="working...")
    try:
        from agents.iac_agent import IacAgent
        result = IacAgent().run(task)
        ev.emit("agent_finished", agent="iac", detail="done")
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.run_iac_agent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        ev.emit("agent_failed", agent="iac", detail=str(e)[:48])
        logger.error(f"[agent_tools] run_iac_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def select_skill_for(task: str) -> str | None:
    """Auto keyword-match a task to the single best skill (Phase 37 routing). Returns the skill
    name, or None when nothing matches (caller falls back to a base agent)."""
    print(f"[TRACE] agents.agent_tools.select_skill_for: enter", file=sys.stderr, flush=True)
    try:
        from core.system.skills import SkillsEngine
        matches = SkillsEngine().get_relevant_skills(task, limit=1)
        if matches:
            return matches[0].get("name")
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.select_skill_for: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[agent_tools] skill selection failed: {e}")
    return None


def run_skill_agent(skill_name: str, task: str, user_id: str | None = None) -> str:
    """Run a named skill as a FULL agent (workspace + file output + self-correction), not a
    one-shot prompt like run_skill. This is how the vendored claude-skills become real agents."""
    try:
        from agents.skill_agent import SkillAgent
        agent = SkillAgent(skill_name, user_id=user_id)
        result = _self_correct(agent, agent.run(task))
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.run_skill_agent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"[agent_tools] run_skill_agent('{skill_name}') failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_engineering_agent(task: str, user_id: str | None = None) -> str:
    """Auto-select the best-matching expert skill for an engineering task and run it as a full
    agent. Falls back to the backend agent when no skill matches. Prefer this for specialized
    engineering work (security audits, RAG, k8s, migrations, performance, etc.)."""
    print(f"[TRACE] agents.agent_tools.run_engineering_agent: enter", file=sys.stderr, flush=True)
    skill = select_skill_for(task)
    if skill:
        logger.info(f"[agent_tools] run_engineering_agent → skill-agent '{skill}'")
        return run_skill_agent(skill, task, user_id)
    logger.info("[agent_tools] run_engineering_agent → no skill matched; using backend agent")
    return run_backend_agent(task, user_id)


def run_skill(skill_name: str, task: str, model: str | None = None) -> str:
    """
    Invoke any skill persona from skills/skills/ as an LLM agent.

    Loads the skill's SKILL.md as the system prompt, routes to the appropriate model
    via model_router.get_skill_model(), and returns the raw response string.
    """
    try:
        from core.system.skills import SkillsEngine
        from agents.model_router import get_skill_model, get_provider, get_api_key

        skill_prompt = SkillsEngine().load_skill_prompt(skill_name)
        chosen_model = model or get_skill_model(skill_name)

        if os.environ.get("JARVIS_CI") == "true":
            logger.info(f"[agent_tools] JARVIS_CI=true. Returning mock skill response for '{skill_name}'.")
            return f"[CI MOCK] Skill '{skill_name}' executed for task: {task[:120]}"

        provider = get_provider(chosen_model)
        api_key = get_api_key(provider)
        return _call_skill_llm(provider, chosen_model, api_key, skill_prompt, task)

    except FileNotFoundError as e:
        print(f"[TRACE] agents.agent_tools.run_skill: except {str(e)[:80]}", file=sys.stderr, flush=True)
        return f"[ERROR] Skill not found: {e}"
    except Exception as e:
        print(f"[TRACE] agents.agent_tools.run_skill: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"[agent_tools] run_skill('{skill_name}') failed: {e}")
        return f"[ERROR] Skill execution failed: {e}"


def _call_skill_llm(provider: str, model: str, api_key: str | None, system_prompt: str, user_prompt: str) -> str:
    """Direct LLM call for skill execution — mirrors BaseAgent._raw_call without telemetry overhead."""
    if provider == "google":
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key, http_options=genai_types.HttpOptions(timeout=90000))
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={"system_instruction": system_prompt},
        )
        return response.text

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=90.0)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    elif provider in ("openai", "nvidia"):
        import openai
        base_url = "https://integrate.api.nvidia.com/v1" if provider == "nvidia" else None
        kwargs = {"api_key": api_key, "timeout": 90.0}
        if base_url:
            kwargs["base_url"] = base_url
        client = openai.OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    elif provider == "ollama":
        import ollama
        client = ollama.Client(timeout=90)
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response["message"]["content"]

    else:
        raise ValueError(f"[agent_tools] Unknown provider '{provider}' for model '{model}'")
