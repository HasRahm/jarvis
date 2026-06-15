"""
Agent Tools — thin wrappers exposing coding agents and skills as orchestrator-callable tools.

Each function lazy-imports the agent to avoid circular imports and returns json.dumps(result)
so the Hermes orchestrator receives a plain string tool result it can embed in context.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)


def run_backend_agent(task: str, user_id: str | None = None) -> str:
    """Invoke the BackendAgent for API routes, SQL migrations, and server logic."""
    try:
        from agents.backend_agent import BackendAgent
        result = BackendAgent(user_id=user_id).run(task)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"[agent_tools] run_backend_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_frontend_agent(task: str, user_id: str | None = None) -> str:
    """Invoke the FrontendAgent for HTML, CSS, JavaScript, and UI generation."""
    try:
        from agents.frontend_agent import FrontendAgent
        result = FrontendAgent(user_id=user_id).run(task)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"[agent_tools] run_frontend_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_qa_agent(task: str, user_id: str | None = None) -> str:
    """Invoke the QAAgent for code review, testing, and verification."""
    try:
        from agents.qa_agent import QAAgent
        result = QAAgent(user_id=user_id).run(task)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"[agent_tools] run_qa_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


def run_iac_agent(task: str) -> str:
    """Invoke the IacAgent for Terraform infrastructure and system configuration."""
    try:
        from agents.iac_agent import IacAgent
        result = IacAgent().run(task)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"[agent_tools] run_iac_agent failed: {e}")
        return json.dumps({"status": "error", "output": str(e), "files": []})


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
        return f"[ERROR] Skill not found: {e}"
    except Exception as e:
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
