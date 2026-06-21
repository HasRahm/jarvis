# Jarvis API Reference — Provider Cheatsheet

Quick reference for every provider used in this project. Use this when writing code that calls any
of these APIs so you get the auth, endpoint, model IDs, and tool format right the first time.

---

## 1. Anthropic (`ANTHROPIC_API_KEY`)

**Endpoint:** `POST https://api.anthropic.com/v1/messages`  
**Auth:** `x-api-key: <key>` + `anthropic-version: 2023-06-01`  
**NOT OpenAI-compatible** — uses its own message format.

```python
import anthropic
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    system="You are Jarvis.",
    messages=[{"role": "user", "content": "Hello"}]
)
text = response.content[0].text
```

**Tool calling:**
```python
tools = [{"name": "get_weather", "description": "...", "input_schema": {"type": "object", "properties": {...}}}]
response = client.messages.create(model=..., tools=tools, messages=[...])
# Tool call is a content block: response.content[i].type == "tool_use"
# Run tool, then send result back:
messages.append({"role": "assistant", "content": response.content})
messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": block.id, "content": result}]})
```

**Streaming:** add `stream=True` → use `with client.messages.stream(...) as stream: for text in stream.text_stream`

**Models in Jarvis:**
| Model | Context | Input $/MTok | Output $/MTok |
|-------|---------|-------------|--------------|
| `claude-sonnet-4-6` | 1M | $3 | $15 |
| `claude-opus-4-8` | 1M | $5 | $25 |
| `claude-haiku-4-5-20251001` | 1M | $1 | $5 |

---

## 2. OpenAI (`OPENAI_API_KEY`)

**Endpoint:** `POST https://api.openai.com/v1/chat/completions`  
**Auth:** `Authorization: Bearer <key>`

```python
from openai import OpenAI
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = client.chat.completions.create(
    model="gpt-5.4",
    messages=[{"role": "user", "content": "Hello"}]
)
text = response.choices[0].message.content
```

**Tool calling:**
```python
tools = [{"type": "function", "function": {"name": "fn", "description": "...", "parameters": {"type": "object", "properties": {...}}}}]
response = client.chat.completions.create(model=..., tools=tools, messages=[...])
# Check: response.choices[0].message.tool_calls
# Each: tc.id, tc.function.name, json.loads(tc.function.arguments)
```

**Streaming:** `stream=True` → iterate `client.chat.completions.create(..., stream=True)` for chunks

**Models in Jarvis:** `gpt-5.4` (1M ctx), `gpt-5.5` (1M ctx)

---

## 3. Google Gemini (`GEMINI_API_KEY`)

**SDK:** `from google import genai`  
**OpenAI-compatible endpoint:** `https://generativelanguage.googleapis.com/v1beta/openai/`

```python
# Native SDK (used in agents/base_agent.py)
from google import genai
from google.genai import types as genai_types
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents="Hello",
    config={"system_instruction": "You are Jarvis."}
)
text = response.text
```

**OpenAI-compatible path (used in llm_adapter.py):**
```python
from openai import OpenAI
client = OpenAI(api_key=os.environ["GEMINI_API_KEY"],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
# Then use same interface as OpenAI above
```

**Tool format (native):** wrap functions in `genai_types.Tool(function_declarations=[...])`  
**IMPORTANT:** Gemini 3 returns `functionCall.id` — always match tool results by ID, not position.

**Streaming (native):** `client.models.generate_content_stream(model, contents)` → iterate chunks

**Models in Jarvis:** `gemini-3.1-pro-preview` (1M ctx), `gemini-2.5-flash-lite`, `gemini-3.5-flash`

---

## 4. NVIDIA Build (`NVIDIA_API_KEY`)

**Base URL:** `https://integrate.api.nvidia.com/v1`  
**Auth:** `Authorization: Bearer <key>`  
**OpenAI-compatible** — use OpenAI SDK pointed at the NVIDIA base URL.

```python
from openai import OpenAI
client = OpenAI(api_key=os.environ["NVIDIA_API_KEY"],
                base_url="https://integrate.api.nvidia.com/v1")
response = client.chat.completions.create(
    model="nvidia/nemotron-3-ultra-550b-a55b",
    messages=[{"role": "user", "content": "Hello"}],
    temperature=1.0,  # reasoning models use 1.0
    top_p=0.95,
    max_tokens=16384
)
```

**Models in Jarvis:**
- `nvidia/nemotron-3-ultra-550b-a55b` — QA/reasoning agent
- `moonshotai/kimi-k2.6` — coding tasks
- `openai/gpt-oss-120b` — general (has content policy, avoid for creative tasks)

**Model name format:** NVIDIA uses `provider/model-name`, e.g. `nvidia/nemotron-...`

---

## 5. OpenRouter (`OPENROUTER_API_KEY`)

**Base URL:** `https://openrouter.ai/api/v1/`  
**Auth:** `Authorization: Bearer <key>`  
**Required headers:** `X-Title: Jarvis` + `HTTP-Referer: https://github.com/HasRahm/jarvis`  
**OpenAI-compatible** — drop-in replacement.

```python
from openai import OpenAI
client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1/",
    default_headers={
        "X-Title": "Jarvis",
        "HTTP-Referer": "https://github.com/HasRahm/jarvis",
    }
)
response = client.chat.completions.create(
    model="google/gemma-4-31b-it:free",  # or "anthropic/claude-3.5-sonnet"
    messages=[{"role": "user", "content": "Hello"}]
)
```

**Free models:** `google/gemma-4-31b-it:free`, `mistralai/mistral-7b-instruct:free`  
**Paid pass-through:** prefix with provider, e.g. `openai/gpt-4o`, `anthropic/claude-3.5-sonnet`

---

## 6. Supabase (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`)

**SDK:** `from supabase import create_client`

```python
from supabase import create_client
# Use SERVICE_ROLE_KEY server-side (bypasses RLS)
client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

# CRUD
rows = client.table("users").select("*").eq("active", True).execute().data
client.table("users").insert({"name": "Alice"}).execute()
client.table("users").update({"active": False}).eq("id", 1).execute()
client.table("users").delete().eq("id", 1).execute()

# Upsert (insert or update on conflict)
client.table("users").upsert({"id": 1, "name": "Alice"}).execute()

# Storage
client.storage.from_("bucket").upload("path/file.txt", b"content")
url = client.storage.from_("bucket").get_public_url("path/file.txt")
```

**Direct Postgres:** `postgresql://postgres:<password>@<host>:5432/postgres`  
**IMPORTANT:** `ANON_KEY` for client-side (respects RLS); `SERVICE_ROLE_KEY` for server-side (bypasses RLS)

---

## 7. Ollama (local, no API key)

**HTTP endpoint:** `POST http://localhost:11434/api/chat`  
**Python SDK:** `from ollama import Client`

```python
from ollama import Client
client = Client(host="http://localhost:11434")

# Chat (blocking)
response = client.chat(model="gemma4:31b-cloud", messages=[{"role": "user", "content": "Hello"}])
text = response.message.content

# Streaming
for chunk in client.chat(model="gemma4:31b-cloud", messages=[...], stream=True):
    print(chunk.message.content, end="", flush=True)

# List loaded models
models = [m.model for m in client.list().models]

# Pull a model
client.pull("llama3.2")
```

**OpenAI-compatible endpoint:** `http://localhost:11434/v1/` (same as OpenAI SDK, api_key="ollama")  
**No auth, no rate limits, fully local and free.**  
**Models persist in memory for 5 min after last use.** Primary model: `gemma4:31b-cloud`

---

## 8. Tavily (`TAVILY_API_KEY`)

**SDK:** `from tavily import TavilyClient`

```python
from tavily import TavilyClient
client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])  # or auto-reads env var

# Basic search
results = client.search("latest AI news", max_results=5)
# results["results"] is a list of {url, title, content, score}

# Get full page context (for RAG)
context = client.get_search_context("AI agent frameworks", max_tokens=4000)

# Q&A mode — returns a direct answer string
answer = client.qna_search("Who is the CEO of Anthropic?")

# Extract content from specific URLs
data = client.extract(urls=["https://example.com/page"])
```

**Free tier:** 1,000 credits/month. Each search = 1 credit. QNA = 1 credit.

---

## 9. E2B Code Interpreter (`E2B_API_KEY`)

**SDK:** `from e2b_code_interpreter import Sandbox`

```python
from e2b_code_interpreter import Sandbox

# Context manager — auto-closes sandbox
with Sandbox.create() as sb:
    result = sb.run_code("x = 42\nprint(x)")
    print(result.logs.stdout)  # ["42\n"]
    
    # State persists across run_code calls in the same sandbox
    sb.run_code("import pandas as pd")
    result2 = sb.run_code("df = pd.DataFrame({'a': [1,2,3]}); print(df)")
    
    # Install packages
    sb.run_code("!pip install requests")
    
    # File I/O
    sb.files.write("/tmp/data.json", '{"key": "value"}')
    content = sb.files.read("/tmp/data.json")

# Async version
from e2b_code_interpreter import AsyncSandbox
async with await AsyncSandbox.create() as sb:
    result = await sb.run_code("print('async')")
```

**Use cases in Jarvis:** run untrusted code safely, test generated scripts, data analysis in isolation.

---

## Provider Routing Summary (llm_adapter.py)

| Model prefix / pattern | Routes to |
|------------------------|-----------|
| `gemma*`, `*:cloud`, `llama*`, `qwen*` | Ollama local |
| `gemini-*` | Google Gemini API |
| `claude-*` | Anthropic API |
| `gpt-*`, `openai*` (no `:cloud`) | OpenAI API |
| `gpt-oss*` | NVIDIA Build |
| `nvidia/*`, `nemotron*`, `moonshotai*` | NVIDIA Build |
| `openrouter/*` | OpenRouter |
