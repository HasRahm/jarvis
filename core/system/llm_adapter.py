import os
import sys
import json
import traceback
import uuid
import httpx
from colorama import Fore, Style

HAS_OLLAMA = True # We will import locally when needed

# ── Optional streaming hook ─────────────────────────────────────────────────
# When set, the adapter routes streamed tokens to this callback instead of
# printing them raw to stdout. The REPL uses this to render live markdown.
# Signature: hook(text: str, kind: str)  where kind ∈ {"content", "reasoning"}.
# When None (default — CLI/TUI), behaviour is unchanged: tokens print to stdout.
_STREAM_HOOK = None


def set_stream_hook(fn):
    """Register (or clear with None) a callback that receives streamed tokens."""
    global _STREAM_HOOK
    _STREAM_HOOK = fn


def _emit(text: str, kind: str = "content", *, raw_print):
    """Send a streamed token to the hook if registered, else fall back to raw_print()."""
    if _STREAM_HOOK is not None:
        try:
            _STREAM_HOOK(text, kind)
            return
        except Exception:
            pass  # never let a UI hook break the stream
    raw_print()


def yield_json_chunks(data: dict, chunk_size=1024):
    """Generator that yields a JSON dict in bytes chunks (Karpathy-style chunked streaming)."""
    json_bytes = json.dumps(data).encode('utf-8')
    for i in range(0, len(json_bytes), chunk_size):
        yield json_bytes[i:i+chunk_size]

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")

def _get_temperature(model: str) -> float:
    """Resolve sampling temperature (Phase 27).

    Priority: JARVIS_TEMPERATURE env override → per-model tuned value → balanced default.
    Default raised from 0.3 to 0.6 so the orchestrator explores alternative approaches
    while staying reliable enough for tool-call JSON. Set JARVIS_TEMPERATURE=0.3 to
    restore the old conservative behaviour on a flaky machine.
    """
    env = os.environ.get("JARVIS_TEMPERATURE")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    m = (model or "").lower()
    if "nemotron" in m or m.startswith("nvidia/") or "moonshotai" in m:
        return 1.0  # reasoning models keep their tuned value
    return 0.6


def is_ollama_available():
    if not HAS_OLLAMA:
        return False
    try:
        # Quick health check to see if Ollama server is up
        with httpx.Client(timeout=1.0) as client:
            resp = client.get("http://127.0.0.1:11434/api/tags")
            return resp.status_code == 200
    except Exception:
        return False

def _select_relevant_tools(tools: list, messages: list, max_tools: int) -> list:
    """
    Select the most relevant tool definitions for the current conversation,
    capping at max_tools to keep the API payload small and prevent hangs.

    Strategy:
    1. Always include core I/O tools (read/write file, run_command, brain_query)
    2. Score remaining tools by keyword overlap with recent message content
    3. Return top max_tools by score
    """
    ALWAYS_INCLUDE = {"read_file", "write_file", "run_command", "brain_query", "brain_write"}

    # Gather keywords from last 3 messages
    recent_text = " ".join(
        str(m.get("content", "")) for m in messages[-3:]
    ).lower()

    # Task-type keyword buckets
    KEYWORD_BUCKETS = {
        "browser":   ["browser", "navigate", "scrape", "web", "url", "http", "linkedin",
                      "search", "extract", "website", "page", "html"],
        "desktop":   ["click", "type", "window", "desktop", "gui", "mouse", "keyboard",
                      "focus", "screen", "button", "ui"],
        "shell":     ["command", "shell", "powershell", "script", "run", "install",
                      "execute", "terminal", "cmd", "process"],
        "files":     ["file", "write", "read", "save", "json", "path", "directory",
                      "create", "folder", "output"],
        "delegate":  ["agent", "orchestrat", "dag", "subtask", "delegate", "multi"],
        "memory":    ["brain", "memory", "remember", "recall", "gbrain"],
        "visual":    ["visual", "servo", "image", "screenshot", "pixel", "coordinate"],
        "window":    ["window", "graph", "3d", "process"],
    }

    # Score each tool
    def score(tool_def: dict) -> int:
        name = tool_def.get("function", {}).get("name", "").lower()
        desc = tool_def.get("function", {}).get("description", "").lower()
        combined = name + " " + desc
        s = 0
        for bucket, kws in KEYWORD_BUCKETS.items():
            bucket_hits = sum(1 for kw in kws if kw in recent_text)
            tool_hits   = sum(1 for kw in kws if kw in combined)
            s += bucket_hits * tool_hits
        return s

    always   = [t for t in tools if t.get("function", {}).get("name") in ALWAYS_INCLUDE]
    rest     = [t for t in tools if t.get("function", {}).get("name") not in ALWAYS_INCLUDE]
    rest_sorted = sorted(rest, key=score, reverse=True)

    selected = always + rest_sorted
    selected = selected[:max_tools]

    names = [t.get("function", {}).get("name") for t in selected]
    print(Fore.CYAN + f"[LLM Adapter] Tool chunk ({len(selected)}/{len(tools)}): {names}" + Style.RESET_ALL, flush=True)
    return selected


def _call_openai_compatible_api(api_key, base_url, model, messages, tools):
    """Unified OpenAI-compatible API caller for both OpenAI and Gemini fallback endpoints."""
    # Preprocess messages to be fully compliant with OpenAI tool calling requirements
    # First, count the total number of tool response messages in the history
    num_tool_messages = sum(1 for m in messages if m.get("role") == "tool")
    tool_calls_assigned = 0

    formatted_messages = []
    # We will map standard tool calls to their generated tool_call_ids to align subsequent tool responses
    pending_tool_calls = []
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        
        # Ensure content is never None for assistant/user roles unless tool_calls are present
        if content is None:
            content = ""
            
        formatted_msg = {
            "role": role,
            "content": content
        }
        
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            valid_tool_calls = []
            if tool_calls:
                for call in tool_calls:
                    if tool_calls_assigned < num_tool_messages:
                        valid_tool_calls.append(call)
                        tool_calls_assigned += 1
            
            if valid_tool_calls:
                openai_tool_calls = []
                for call in valid_tool_calls:
                    call_id = f"call_{uuid.uuid4().hex[:8]}"
                    fn_info = call.get("function", {})
                    fn_name = fn_info.get("name")
                    fn_args = fn_info.get("arguments", {})
                    
                    # Store for matching tool responses
                    pending_tool_calls.append(call_id)
                    
                    # OpenAI expects arguments to be a JSON-serialized string
                    if isinstance(fn_args, dict):
                        args_str = json.dumps(fn_args)
                    else:
                        args_str = fn_args
                        
                    openai_tool_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": args_str
                        }
                    })
                formatted_msg["tool_calls"] = openai_tool_calls
                # Content can be None/empty when tool calls are present
                if not formatted_msg["content"]:
                    del formatted_msg["content"]
            else:
                # If tool calls were omitted or there were none, ensure content is non-empty
                if not formatted_msg["content"] or not formatted_msg["content"].strip():
                    formatted_msg["content"] = "Executing..."
            formatted_messages.append(formatted_msg)
            
        elif role == "tool":
            # Match this tool response with the corresponding tool call ID in order
            if pending_tool_calls:
                call_id = pending_tool_calls.pop(0)
            else:
                call_id = f"call_orphan_{uuid.uuid4().hex[:4]}"
            
            formatted_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": str(content)
            })
        else:
            formatted_messages.append(formatted_msg)

    # Format tool definitions to OpenAI structure
    # ── Selective tool chunking: send at most MAX_TOOLS per request ──────
    # Sending all tools at once can cause silent hangs on large payloads.
    # We select the most relevant tools based on recent message content.
    MAX_TOOLS = 32
    formatted_tools = None
    if tools:
        selected = _select_relevant_tools(tools, formatted_messages, MAX_TOOLS)
        formatted_tools = selected if selected else None

    payload = {
        "model": model,
        "messages": formatted_messages,
        "temperature": _get_temperature(model),
        "stream": True
    }

    if "nemotron" in model.lower() or model.lower().startswith("nvidia/"):
        payload["top_p"] = 0.95
        payload["max_tokens"] = 16384
        payload["reasoning_budget"] = 1024
    elif "moonshotai" in model.lower():
        payload["top_p"] = 1.0
        payload["max_tokens"] = 16384

    if formatted_tools:
        payload["tools"] = formatted_tools
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Ensure URL is correct
    url = base_url.rstrip("/") + "/chat/completions"

    res_content = ""
    raw_tool_calls: dict = {}   # index -> {id, name, arguments}

    print(Fore.CYAN + f"[LLM Adapter] Streaming from {model}..." + Style.RESET_ALL, end="", flush=True)
    try:
        with httpx.stream("POST", url, content=yield_json_chunks(payload), headers=headers, timeout=600.0) as response:
            if response.status_code != 200:
                response.read()
                raise ValueError(f"HTTP {response.status_code}: {response.text}")
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                # API ignored stream=True (common for some models when tools are present)
                full_json = response.read().decode("utf-8")
                try:
                    data = json.loads(full_json)
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        # reasoning_content (chain-of-thought) — present on gpt-oss-120b and similar reasoning models
                        if msg.get("reasoning_content"):
                            _emit(msg["reasoning_content"], "reasoning",
                                  raw_print=lambda: print(Fore.MAGENTA + msg["reasoning_content"] + Style.RESET_ALL, end="", flush=True))
                        if msg.get("content"):
                            res_content = msg["content"]
                            _emit(res_content, "content",
                                  raw_print=lambda: print(res_content, end="", flush=True))
                        if msg.get("tool_calls"):
                            for i, tc in enumerate(msg["tool_calls"]):
                                raw_tool_calls[i] = {
                                    "id": tc.get("id", f"call_{i}"),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": tc.get("function", {}).get("arguments", "")
                                }
                except Exception as e:
                    print(f"\n[LLM Adapter] Error parsing monolithic JSON: {e}")
            else:
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        
                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            res_content += delta["reasoning_content"]
                            _emit(delta["reasoning_content"], "reasoning",
                                  raw_print=lambda: print(Fore.MAGENTA + delta["reasoning_content"] + Style.RESET_ALL, end="", flush=True))

                        if "content" in delta and delta["content"]:
                            res_content += delta["content"]
                            _emit(delta["content"], "content",
                                  raw_print=lambda: print(delta["content"], end="", flush=True))
                            
                        if "tool_calls" in delta and delta["tool_calls"]:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index")
                                if idx not in raw_tool_calls:
                                    raw_tool_calls[idx] = {
                                        "id": tc.get("id") or f"call_{idx}",
                                        "name": tc.get("function", {}).get("name", ""),
                                        "arguments": "",
                                    }
                                if tc.get("function", {}).get("name"):
                                    raw_tool_calls[idx]["name"] = tc.get("function")["name"]
                                if tc.get("function", {}).get("arguments"):
                                    raw_tool_calls[idx]["arguments"] += tc.get("function")["arguments"]
                    except Exception as e:
                        pass
    except Exception as e:
        print(Fore.RED + f"\n[LLM Adapter] Stream error: {e}" + Style.RESET_ALL)
        sys.stdout.flush()
        raise

    print("", flush=True)   # newline after dots

    # Map streamed response back to standard message dictionary format
    result_message = {
        "role": "assistant",
        "content": res_content
    }

    # Reconstruct tool_calls from accumulated stream chunks
    if raw_tool_calls:
        ollama_tool_calls = []
        for idx in sorted(raw_tool_calls):
            tc = raw_tool_calls[idx]
            try:
                args_dict = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except Exception:
                args_dict = tc["arguments"]
            ollama_tool_calls.append({
                "function": {
                    "name": tc["name"],
                    "arguments": args_dict,
                }
            })
        result_message["tool_calls"] = ollama_tool_calls
        
    # Open-source model custom XML-like text-based tool calling fallback:
    # Look for <|tool_call|>call:tool_name{arguments}<tool_call>
    else:
        import re
        tool_calls = []
        matches = re.finditer(r"<\|tool_call\|?>call:(\w+)\{(.*?)\}<tool_call\|?>", res_content, re.DOTALL)
        for m in matches:
            fn_name = m.group(1)
            args_str = m.group(2)
            
            args = {}
            # Try extracting key:<|""|>value<|""|> pairs
            kv_pairs = re.finditer(r"(\w+):<\|\"\|>(.*?)<\|\"\|>", args_str, re.DOTALL)
            found_kv = False
            for kv in kv_pairs:
                args[kv.group(1)] = kv.group(2)
                found_kv = True
                
            if not found_kv:
                # Try standard JSON/dict parsing
                try:
                    cleaned = args_str.replace("'", '"')
                    args = json.loads("{" + cleaned + "}")
                except Exception:
                    args = {"raw": args_str}
                    
            tool_calls.append({
                "function": {
                    "name": fn_name,
                    "arguments": args
                }
            })
            
        if tool_calls:
            result_message["tool_calls"] = tool_calls
            # Remove the tool call tags from the assistant's content
            clean_content = re.sub(r"<\|tool_call\|?>call:(\w+)\{(.*?)\}<tool_call\|?>", "", res_content, flags=re.DOTALL).strip()
            result_message["content"] = clean_content

    return result_message


def _call_anthropic_api(api_key, model, messages, tools):
    """Call Anthropic API using httpx with chunked streaming request."""
    system_instruction = ""
    anthropic_messages = []
    
    # Track tool_use IDs to align them with subsequent tool results
    tool_responses_count = 0
    current_role = None
    current_content = []
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        
        if role == "system":
            if content:
                system_instruction += str(content) + "\n"
            continue
            
        anthropic_role = "user" if role in ("user", "tool") else "assistant"
        if anthropic_role != current_role:
            if current_role is not None and current_content:
                anthropic_messages.append({"role": current_role, "content": current_content})
            current_role = anthropic_role
            current_content = []
            
        if role == "user":
            if content:
                current_content.append({"type": "text", "text": str(content)})
        elif role == "assistant":
            if content:
                current_content.append({"type": "text", "text": str(content)})
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tc_id = f"tc_{uuid.uuid4().hex[:8]}"
                    tc["_anthropic_id"] = tc_id
                    current_content.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": fn.get("name"),
                        "input": fn.get("arguments")
                    })
            if not current_content:
                current_content.append({"type": "text", "text": "Executing..."})
        elif role == "tool":
            tc_id = None
            current_tc_count = 0
            for prev_msg in messages:
                if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                    for tc in prev_msg["tool_calls"]:
                        if current_tc_count == tool_responses_count:
                            tc_id = tc.get("_anthropic_id")
                            break
                        current_tc_count += 1
                    if tc_id:
                        break
            
            if not tc_id:
                tc_id = f"tc_orphan_{uuid.uuid4().hex[:8]}"
                
            current_content.append({
                "type": "tool_result",
                "tool_use_id": tc_id,
                "content": str(content)
            })
            tool_responses_count += 1
            
    if current_role is not None and current_content:
        anthropic_messages.append({"role": current_role, "content": current_content})
            
    anthropic_tools = []
    if tools:
        for t in tools:
            fn = t.get("function", {})
            anthropic_tools.append({
                "name": fn.get("name"),
                "description": fn.get("description"),
                "input_schema": fn.get("parameters")
            })
            
    ANTHROPIC_MODEL_MAP = {
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-opus-4-8": "claude-opus-4-8",
        "claude-sonnet-3-5": "claude-sonnet-4-6", # Auto-upgrade legacy requests
        "claude-opus": "claude-opus-4-8",
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-haiku": "claude-haiku-4-5-20251001",
    }
    anthropic_model = ANTHROPIC_MODEL_MAP.get(model.lower(), model)
    
    payload = {
        "model": anthropic_model,
        "max_tokens": 4096,
        "messages": anthropic_messages,
        "temperature": min(_get_temperature(model), 1.0),  # Anthropic caps at 1.0
        "stream": True
    }
    if system_instruction:
        payload["system"] = system_instruction.strip()
    if anthropic_tools:
        payload["tools"] = anthropic_tools
        
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    res_content = ""
    raw_tool_calls = {}
    current_tool_index = None

    print(Fore.CYAN + f"[LLM Adapter] Streaming from Anthropic ({anthropic_model})..." + Style.RESET_ALL, end="", flush=True)
    try:
        with httpx.stream("POST", "https://api.anthropic.com/v1/messages", content=yield_json_chunks(payload), headers=headers, timeout=120) as response:
            if response.status_code != 200:
                response.read()
                raise ValueError(f"HTTP {response.status_code}: {response.text}")

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                    type_ = data.get("type")
                    if type_ == "content_block_start":
                        idx = data["index"]
                        block = data["content_block"]
                        if block["type"] == "tool_use":
                            current_tool_index = idx
                            raw_tool_calls[idx] = {
                                "id": block["id"],
                                "name": block["name"],
                                "arguments": ""
                            }
                    elif type_ == "content_block_delta":
                        delta = data["delta"]
                        if delta["type"] == "text_delta":
                            res_content += delta["text"]
                            _emit(delta["text"], "content",
                                  raw_print=lambda: print(".", end="", flush=True))
                        elif delta["type"] == "input_json_delta":
                            idx = data["index"]
                            raw_tool_calls[idx]["arguments"] += delta["partial_json"]
                except Exception as e:
                    pass
    except Exception as e:
        print(Fore.RED + f"\n[LLM Adapter] Stream error: {e}" + Style.RESET_ALL)
        sys.stdout.flush()
        raise

    print("", flush=True)
    
    result = {
        "role": "assistant",
        "content": res_content
    }
    
    tool_calls = []
    for idx in sorted(raw_tool_calls):
        tc = raw_tool_calls[idx]
        try:
            args_dict = json.loads(tc["arguments"]) if tc["arguments"] else {}
        except Exception:
            args_dict = tc["arguments"]
        tool_calls.append({
            "function": {
                "name": tc["name"],
                "arguments": args_dict
            }
        })

    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def call_llm(messages, model="gemma4:31b-cloud", tools=None):
    """
    Unified LLM call adapter with resilient cloud fallbacks.
    Rotates through FALLBACK_CHAIN in order when a model fails.
    """
    FALLBACK_CHAIN = [
        "gemma4:31b-cloud",          # Ollama cloud proxy — free, no API key (primary free model)
        "claude-sonnet-4-6",         # Anthropic — paid but reliable
        "gpt-5.4",                   # OpenAI — fallback if quota available
        "gemini-3.1-pro-preview",    # Google Gemini — fallback
        "gemini-2.5-pro",            # Google Gemini — last resort
        # Removed: kimi-k2.6:cloud, gpt-oss:120b-cloud — require paid Ollama subscription
    ]

    models_to_try = [model]
    for m in FALLBACK_CHAIN:
        if m not in models_to_try:
            models_to_try.append(m)

    last_error = None
    for m in models_to_try:
        try:
            m_lower = m.lower()
            
            # 0. NVIDIA gpt-oss routing — must run BEFORE :cloud Ollama catch-all.
            #    gpt-oss:120b-cloud → openai/gpt-oss-120b on integrate.api.nvidia.com
            #    Strips the ":cloud" / ":latest" Ollama-style tag and adds "openai/" prefix.
            if "gpt-oss" in m_lower:
                nvidia_key = os.environ.get("NVIDIA_API_KEY")
                if not nvidia_key:
                    raise ValueError("NVIDIA_API_KEY is not defined.")
                # Normalise: "gpt-oss:120b-cloud" → "openai/gpt-oss-120b"
                #             "openai/gpt-oss-120b" → unchanged
                if m_lower.startswith("openai/"):
                    nvidia_model = m  # already canonical
                else:
                    # strip optional :tag suffix, then prepend openai/
                    base = m.split(":")[0]  # "gpt-oss"
                    size = m.split(":")[1].replace("-cloud", "").replace("-latest", "") if ":" in m else ""
                    nvidia_model = f"openai/{base}-{size}" if size else f"openai/{base}"
                print(Fore.CYAN + f"[LLM Adapter] Routing request to NVIDIA API (model: {nvidia_model})..." + Style.RESET_ALL)
                sys.stdout.flush()
                return _call_openai_compatible_api(
                    api_key=nvidia_key,
                    base_url="https://integrate.api.nvidia.com/v1/",
                    model=nvidia_model,
                    messages=messages,
                    tools=tools
                )

            # 1. Local Ollama Routing — catches all Ollama-named models:
            #    ":cloud" and ":latest" are Ollama's naming conventions for proxied/local models.
            elif (m_lower.endswith(":cloud") or m_lower.endswith(":latest") or
                    "gemma" in m_lower or m_lower.startswith("llama") or
                    m_lower.startswith("qwen") or m_lower.startswith("nomic") or
                    m_lower.startswith("mxbai")):
                if is_ollama_available():
                    print(Fore.CYAN + f"[LLM Adapter] Routing request to local Ollama (model: {m})..." + Style.RESET_ALL)
                    sys.stdout.flush()
                    return _call_openai_compatible_api(
                        api_key="ollama",
                        base_url="http://127.0.0.1:11434/v1/",
                        model=m,
                        messages=messages,
                        tools=tools
                    )
                else:
                    raise ValueError("Local Ollama is unavailable.")
            
            # 2. Gemini Cloud Routing
            elif m_lower.startswith("gemini-") or "gemini" in m_lower:
                gemini_key = os.environ.get("GEMINI_API_KEY")
                if not gemini_key:
                    raise ValueError("GEMINI_API_KEY is not defined.")
                print(Fore.CYAN + f"[LLM Adapter] Routing request to Gemini API (model: {m})..." + Style.RESET_ALL)
                sys.stdout.flush()
                
                # Map to proper API model name
                gemini_model = "gemini-3.1-pro-preview" if m == "gemini-3.1-pro" else m
                return _call_openai_compatible_api(
                    api_key=gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    model=gemini_model,
                    messages=messages,
                    tools=tools
                )
                
            # 3. Anthropic Cloud Routing
            elif m_lower.startswith("claude-") or "claude" in m_lower:
                anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
                if not anthropic_key:
                    raise ValueError("ANTHROPIC_API_KEY is not defined.")
                print(Fore.CYAN + f"[LLM Adapter] Routing request to Anthropic API (model: {m})..." + Style.RESET_ALL)
                sys.stdout.flush()
                return _call_anthropic_api(anthropic_key, m, messages, tools)
                
            # 4. OpenAI Cloud Routing
            # Guard: :cloud and :latest suffix models belong to Ollama — never route to OpenAI.
            elif (m_lower.startswith("gpt-") or "openai" in m_lower or "gpt" in m_lower) and not m_lower.endswith(":cloud") and not m_lower.endswith(":latest"):
                openai_key = os.environ.get("OPENAI_API_KEY")
                if not openai_key:
                    raise ValueError("OPENAI_API_KEY is not defined.")
                print(Fore.CYAN + f"[LLM Adapter] Routing request to OpenAI API (model: {m})..." + Style.RESET_ALL)
                sys.stdout.flush()
                
                # Pass model name through — OpenAI resolves current model IDs
                openai_model = m
                return _call_openai_compatible_api(
                    api_key=openai_key,
                    base_url="https://api.openai.com/v1/",
                    model=openai_model,
                    messages=messages,
                    tools=tools
                )
                
            # 5. NVIDIA Cloud Routing
            elif m_lower.startswith("nvidia/") or "nemotron" in m_lower or "moonshotai" in m_lower:
                nvidia_key = os.environ.get("NVIDIA_API_KEY")
                if not nvidia_key:
                    raise ValueError("NVIDIA_API_KEY is not defined.")
                print(Fore.CYAN + f"[LLM Adapter] Routing request to NVIDIA API (model: {m})..." + Style.RESET_ALL)
                sys.stdout.flush()
                
                return _call_openai_compatible_api(
                    api_key=nvidia_key,
                    base_url="https://integrate.api.nvidia.com/v1/",
                    model=m,
                    messages=messages,
                    tools=tools
                )
                
            # 6. OpenRouter routing — handles openrouter/ prefix OR OPENROUTER_MODEL env var
            elif m_lower.startswith("openrouter/") or (OPENROUTER_API_KEY and OPENROUTER_MODEL and m == OPENROUTER_MODEL):
                if not OPENROUTER_API_KEY:
                    raise ValueError("OPENROUTER_API_KEY is not defined.")
                openrouter_model = m[len("openrouter/"):] if m_lower.startswith("openrouter/") else m
                print(Fore.CYAN + f"[LLM Adapter] Routing request to OpenRouter (model: {openrouter_model})..." + Style.RESET_ALL)
                sys.stdout.flush()
                return _call_openai_compatible_api(
                    api_key=OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1/",
                    model=openrouter_model,
                    messages=messages,
                    tools=tools
                )

            else:
                raise ValueError(f"Unknown model provider structure: {m}")
                
        except Exception as e:
            print(Fore.RED + f"[LLM Adapter] Model {m} failed: {e}. Trying next fallback..." + Style.RESET_ALL)
            print(Fore.YELLOW + "[Debugger] Traceback details for the failure:" + Style.RESET_ALL)
            traceback.print_exc()
            sys.stdout.flush()
            last_error = e

    raise ValueError(
        f"All models in fallback chain failed. Last error: {last_error}"
    )

