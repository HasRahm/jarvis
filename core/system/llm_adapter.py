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


def call_llm(messages, model="gemma4:31b-cloud", tools=None):
    """
    Unified LLM call adapter with resilient cloud fallbacks.
    1. Tries local Ollama with a 30s timeout.
    2. Falls back to OpenAI API if OPENAI_API_KEY is defined.
    3. Falls back to OpenRouter if OPENROUTER_API_KEY is defined.
    """
    # 1. Try Local Ollama first
    if is_ollama_available():
        try:
            print(Fore.CYAN + f"[LLM Adapter] Routing request to local Ollama server (model: {model})..." + Style.RESET_ALL)
            sys.stdout.flush()
            # Set a 30-second timeout to prevent infinite hangs on model loading/VRAM bottlenecks
            client = ollama.Client(timeout=30.0)
            response = client.chat(
                model=model,
                messages=messages,
                tools=tools,
                options={"temperature": 0.3}
            )
            return response["message"]
        except Exception as e:
            print(Fore.RED + f"[LLM Adapter] Local Ollama call failed or timed out: {e}." + Style.RESET_ALL)
            print(Fore.CYAN + "Initiating cloud API failover sequence..." + Style.RESET_ALL)
            sys.stdout.flush()
    
    # 2. Fallback Option A: OpenAI API
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key and HAS_OPENAI:
        print(Fore.CYAN + "[LLM Adapter] Falling back to OpenAI API..." + Style.RESET_ALL)
        sys.stdout.flush()
        
        fallback_model = os.environ.get("JARVIS_OPENAI_MODEL", "gpt-4o")
        client = OpenAI(api_key=openai_key)
        
        try:
            return _call_openai_compatible_api(client, fallback_model, messages, tools)
        except Exception as e:
            print(Fore.RED + f"[LLM Adapter] OpenAI API fallback failed: {e}. Trying secondary fallback..." + Style.RESET_ALL)
            sys.stdout.flush()
            
    # 3. Fallback Option B: OpenRouter API
    if OPENROUTER_API_KEY and HAS_OPENAI:
        print(Fore.CYAN + "[LLM Adapter] Falling back to OpenRouter API..." + Style.RESET_ALL)
        sys.stdout.flush()
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            timeout=90.0,
        )
        return _call_openai_compatible_api(client, OPENROUTER_MODEL, messages, tools)
        
    # 4. Error state: No models available
    raise ValueError(
        "Ollama is unavailable/failed, and no valid cloud API keys (OPENAI_API_KEY or OPENROUTER_API_KEY) "
        "are configured in the environment variables to handle fallback routing."
    )

