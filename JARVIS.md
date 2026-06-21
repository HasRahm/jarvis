# Jarvis Project Context

This file is automatically loaded by the Jarvis CLI when you run it from this directory
(like CLAUDE.md / GEMINI.md). Add project-specific instructions, context, or constraints here.

## Project
Jarvis — Local AI agent OS powering desktop automation, multi-agent orchestration, and phone access.

## Stack
- Primary brain: Ollama gemma4:31b-cloud (local, free) — this is the chat/orchestrator default
- Desktop automation: pyautogui + visual_servo + UI-TARS observe-after-act loop
- Multi-agent: per-agent models are configured in the router (`agents/model_router.py`). Run `/agents`
  for the LIVE assignments — do NOT hardcode model IDs here (they drift out of sync)
- Memory: GBrain (local Bun) + SQLite fallback
- Phone: Hermes WebSocket bridge via Cloudflare tunnel

## Rules for this project
- Always check AGENTS.md before assigning new subtasks
- Use `delegate_task` for multi-component builds (DB + API + UI)
- Never output Unicode symbols that break CP1252 in orchestrator scripts
- Write generated files into the working directory (the resolved output root), NOT the install dir
- The chat/orchestrator default is gemma4:31b-cloud (local Ollama, free); vision and document
  generation route separately — `--model` controls only the chat/orchestrator primary

## API Quick Reference

Full cheatsheet: `docs/api-reference.md` — read it before writing any API call.

| Provider | Env var | Base URL / SDK | Notes |
|----------|---------|----------------|-------|
| Anthropic | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1/messages` | NOT OpenAI-compat; use `x-api-key` header |
| OpenAI | `OPENAI_API_KEY` | `https://api.openai.com/v1/` | Standard bearer auth |
| Gemini | `GEMINI_API_KEY` | `google.genai` SDK or OpenAI-compat at `googleapis.com/v1beta/openai/` | Tool results must match by `functionCall.id` |
| NVIDIA | `NVIDIA_API_KEY` | `https://integrate.api.nvidia.com/v1` | OpenAI-compat; model names: `nvidia/nemotron-...` |
| OpenRouter | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1/` | Add `X-Title: Jarvis` + `HTTP-Referer` headers |
| Supabase | `SUPABASE_URL` + keys | `supabase.create_client(url, key)` | Use SERVICE_ROLE_KEY server-side |
| Ollama | none | `http://localhost:11434/v1/` | Free, local; primary model: `gemma4:31b-cloud` |
| Tavily | `TAVILY_API_KEY` | `TavilyClient(api_key=...)` | Web search; 1k free credits/month |
| E2B | `E2B_API_KEY` | `e2b_code_interpreter.Sandbox` | Isolated code execution sandbox |
