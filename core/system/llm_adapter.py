import os
import sys
import json
import uuid
import httpx
from colorama import Fore, Style

try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")

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

def _call_openai_compatible_api(client, model, messages, tools):
    """Unified OpenAI-compatible API caller for both OpenAI and OpenRouter fallback endpoints."""
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
    formatted_tools = None
    if tools:
        formatted_tools = []
        for t in tools:
            formatted_tools.append(t)
            
    # Make API call
    try:
        response = client.chat.completions.create(
            model=model,
            messages=formatted_messages,
            tools=formatted_tools,
            temperature=0.3
        )
    except Exception as e:
        print(Fore.RED + f"[LLM Adapter] API call to {model} failed: {e}" + Style.RESET_ALL)
        sys.stdout.flush()
        raise
    
    choice = response.choices[0]
    res_msg = choice.message
    res_content = res_msg.content or ""
    
    # Map OpenAI response back to standard Ollama message dictionary format
    result_message = {
        "role": "assistant",
        "content": res_content
    }
    
    # Standard OpenRouter/OpenAI native tool_calls
    if res_msg.tool_calls:
        ollama_tool_calls = []
        for call in res_msg.tool_calls:
            # Parse arguments string back into dictionary
            try:
                args_dict = json.loads(call.function.arguments)
            except Exception:
                args_dict = call.function.arguments
                
            ollama_tool_calls.append({
                "function": {
                    "name": call.function.name,
                    "arguments": args_dict
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


def _call_anthropic_api(model, messages, tools):
    """Call Anthropic API natively and map standard formats back and forth."""
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)
    
    system_instruction = ""
    anthropic_messages = []
    
    # Track tool_use IDs to align them with subsequent tool results
    # Each tool result (role == "tool") corresponds sequentially to a tool call (in role == "assistant")
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
            
        # Determine the Anthropic role: tool messages belong to "user" role
        anthropic_role = "user" if role in ("user", "tool") else "assistant"
        
        # If role changed, flush the current message
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
                    # Generate a unique tool use ID and tag the tool call object
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
            # Match this tool response with the corresponding tool call's generated ID
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
            
    # Flush final message
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
            
    # Map friendly names to current Anthropic API model IDs
    ANTHROPIC_MODEL_MAP = {
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-opus-4-8": "claude-opus-4-8",
        "claude-haiku-4-5": "claude-haiku-4-5-20251001",
        # Legacy aliases
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-opus": "claude-opus-4-8",
        "claude-haiku": "claude-haiku-4-5-20251001",
    }
    anthropic_model = ANTHROPIC_MODEL_MAP.get(model.lower(), model)
    
    params = {
        "model": anthropic_model,
        "max_tokens": 4096,
        "messages": anthropic_messages,
    }
    if system_instruction:
        params["system"] = system_instruction.strip()
    if anthropic_tools:
        params["tools"] = anthropic_tools
        
    response = client.messages.create(**params)
    
    response_text = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            response_text += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "function": {
                    "name": block.name,
                    "arguments": block.input
                }
            })
            
    result = {
        "role": "assistant",
        "content": response_text
    }
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def call_llm(messages, model="gemma4:31b-cloud", tools=None):
    """
    Unified LLM call adapter with resilient cloud fallbacks.
    Rotates through FALLBACK_CHAIN in order when a model fails.
    """
    FALLBACK_CHAIN = [
        "gemini-3.1-pro-preview",
        "gemini-2.5-pro",
        "claude-sonnet-4-6",
        "gpt-5.4"
    ]

    models_to_try = [model]
    for m in FALLBACK_CHAIN:
        if m not in models_to_try:
            models_to_try.append(m)

    last_error = None
    for m in models_to_try:
        try:
            m_lower = m.lower()
            
            # 1. Local Ollama Routing
            if m_lower == "gemma4:31b-cloud" or "gemma" in m_lower:
                if is_ollama_available():
                    print(Fore.CYAN + f"[LLM Adapter] Routing request to local Ollama server (model: {m})..." + Style.RESET_ALL)
                    sys.stdout.flush()
                    client = ollama.Client(timeout=30.0)
                    response = client.chat(
                        model=m,
                        messages=messages,
                        tools=tools,
                        options={"temperature": 0.3}
                    )
                    return response["message"]
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
                client = OpenAI(
                    api_key=gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
                return _call_openai_compatible_api(client, gemini_model, messages, tools)
                
            # 3. Anthropic Cloud Routing
            elif m_lower.startswith("claude-") or "claude" in m_lower:
                anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
                if not anthropic_key:
                    raise ValueError("ANTHROPIC_API_KEY is not defined.")
                print(Fore.CYAN + f"[LLM Adapter] Routing request to Anthropic API (model: {m})..." + Style.RESET_ALL)
                sys.stdout.flush()
                return _call_anthropic_api(m, messages, tools)
                
            # 4. OpenAI Cloud Routing
            elif m_lower.startswith("gpt-") or "openai" in m_lower or "gpt" in m_lower:
                openai_key = os.environ.get("OPENAI_API_KEY")
                if not openai_key:
                    raise ValueError("OPENAI_API_KEY is not defined.")
                print(Fore.CYAN + f"[LLM Adapter] Routing request to OpenAI API (model: {m})..." + Style.RESET_ALL)
                sys.stdout.flush()
                
                # Pass model name through — OpenAI resolves current model IDs
                openai_model = m
                client = OpenAI(api_key=openai_key)
                return _call_openai_compatible_api(client, openai_model, messages, tools)
                
            else:
                raise ValueError(f"Unknown model provider structure: {m}")
                
        except Exception as e:
            print(Fore.RED + f"[LLM Adapter] Model {m} failed: {e}. Trying next fallback..." + Style.RESET_ALL)
            sys.stdout.flush()
            last_error = e

    raise ValueError(
        f"All models in fallback chain failed. Last error: {last_error}"
    )

