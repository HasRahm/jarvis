# AGENTS.md Protocol Specification

**Version:** 1.0.0  
**Status:** Draft  
**Authors:** Jarvis Contributors  
**License:** Apache 2.0  

---

## Abstract

AGENTS.md is an open protocol for coordinating multiple AI agents through a single shared markdown file. Instead of requiring message buses, gRPC channels, or proprietary orchestration SDKs, agents communicate by reading and writing sections of a plain-text file that both humans and machines can understand.

The protocol solves three problems simultaneously:

1. **Agent coordination** — Every agent knows what every other agent is doing, has done, and plans to do.
2. **Human observability** — A human can open the file at any time and understand the full system state in a format they already know how to read.
3. **Contract negotiation** — Backend agents publish API contracts that frontend agents consume, with the file serving as the single source of truth.

---

## Motivation

Existing multi-agent coordination approaches fall into two categories:

**Message passing** (e.g., AutoGen, CrewAI) — Agents send messages to each other through an orchestrator. The coordination state exists only in memory. If the system crashes, state is lost. If a human wants to understand what happened, they must parse logs.

**Shared databases** (e.g., custom SQL stores, Redis) — Agents read and write structured data. This works but requires infrastructure, schemas, and serialization. It is invisible to humans without a dashboard.

AGENTS.md takes a third approach: **shared state in a human-readable file**. The file is the protocol. No infrastructure required. Version-controllable with git. Readable by any text editor. Parseable by any LLM without special tooling.

### Design Principles

1. **Markdown is the wire format** — Every LLM can read and write markdown natively. No serialization layer needed.
2. **File is the message bus** — Agents coordinate by reading and writing sections of the same file, not by sending messages.
3. **Human-first observability** — A developer should be able to `cat AGENTS.md` at any time and understand the full system state.
4. **No dependencies** — The protocol requires no libraries, servers, or infrastructure beyond a filesystem.
5. **Append-only log** — The Task Log section is append-only. Agents never delete log entries.

---

## File Structure

An AGENTS.md file contains five sections in order. All sections are required except Contracts.

### 1. Header

```markdown
# AGENTS.md - Shared Agent State
```

The header is always exactly this string. Parsers use it to identify valid AGENTS.md files.

### 2. Current Task

A markdown table describing the active task.

```markdown
## Current Task
| Field | Value |
|-------|-------|
| Task ID | task_20260605_143159 |
| Description | Build a REST API for user management |
| Status | IN_PROGRESS |
| Requested By | orchestrator |
```

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `Task ID` | `string` | Unique identifier. Convention: `task_YYYYMMDD_HHMMSS` |
| `Description` | `string` | Human-readable task description. Max 120 characters. |
| `Status` | `enum` | One of: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED` |
| `Requested By` | `string` | The agent role or `user` that initiated the task |

### 3. Agent Assignments

A markdown table showing all registered agents and their current state.

```markdown
## Agent Assignments
| Agent | Model | Status | Current Step |
|-------|-------|--------|-------------|
| frontend | gemini-3.1-pro | IDLE | --- |
| backend | claude-sonnet-4-6 | WORKING | Creating API endpoints |
| qa | gpt-5.4 | IDLE | --- |
| iac | claude-sonnet-4-6 | IDLE | --- |
```

**Column definitions:**

| Column | Type | Description |
|--------|------|-------------|
| `Agent` | `string` | Role identifier. Lowercase, no spaces. |
| `Model` | `string` | The LLM model this agent uses. Informational. |
| `Status` | `enum` | One of: `IDLE`, `WORKING`, `DONE`, `FAILED`, `INTERRUPTED`, `STALE` |
| `Current Step` | `string` | Human-readable description of what the agent is doing now. `---` when idle. |

**Status lifecycle:**

```
IDLE → WORKING → DONE
                → FAILED
                → INTERRUPTED (cancelled by orchestrator)
DONE → STALE (output superseded by a later agent)
```

### 4. Task Log

An append-only log of agent events. Every state change, contract publication, completion, or error is recorded here.

```markdown
## Task Log
- [2026-06-05 14:32] backend: Started: Designing database schema
- [2026-06-05 14:33] backend: Contract published:
  ```json
  { "tables": [...], "endpoints": [...] }
  ```
- [2026-06-05 14:33] backend: Completed: Built REST API with 4 endpoints
- [2026-06-05 14:34] frontend: Started: Building UI components
- [2026-06-05 14:36] frontend: Completed: Created responsive dashboard
```

**Log entry format:**

```
- [YYYY-MM-DD HH:MM] <agent_role>: <event_type>: <message>
```

**Event types:**

| Event | Description |
|-------|-------------|
| `Started` | Agent began working on a subtask |
| `Completed` | Agent finished successfully |
| `Failed` | Agent encountered an unrecoverable error |
| `Contract published` | Agent published an interface contract (see §5) |
| `Interrupted` | Agent was stopped by the orchestrator |

**Rules:**
- Log entries are **append-only**. Agents MUST NOT modify or delete existing entries.
- Timestamps use the local timezone of the orchestrator.
- Messages should be concise (under 200 characters for non-contract entries).

### 5. Contracts (Optional)

Contracts are published inline in the Task Log as fenced JSON code blocks. They define the interface between agents — typically between backend and frontend.

A contract contains two sections:

```json
{
  "tables": [
    {
      "name": "users",
      "columns": [
        { "name": "id", "type": "SERIAL", "primary_key": true },
        { "name": "email", "type": "VARCHAR(255)", "nullable": false, "unique": true },
        { "name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP" }
      ]
    }
  ],
  "endpoints": [
    {
      "method": "GET",
      "path": "/api/users",
      "response": {
        "items": [{ "id": "integer", "email": "string", "created_at": "datetime" }]
      }
    },
    {
      "method": "POST",
      "path": "/api/users",
      "body": { "email": "string" },
      "response": { "id": "integer", "email": "string", "created_at": "datetime" }
    }
  ]
}
```

**Contract rules:**
- Contracts are published by the producing agent (typically `backend`).
- Consuming agents (typically `frontend`) MUST read the latest contract before generating code.
- If multiple contracts are published, the latest one wins.
- Contracts SHOULD be persisted to long-term memory for cross-session recall (see §Extensions).

---

## Operations

### Creating a New Task

The orchestrator creates a fresh AGENTS.md at the start of each task:

1. Write the header.
2. Set Current Task with `Status: IN_PROGRESS`.
3. Register all agents in Agent Assignments with `Status: IDLE`.
4. Create an empty Task Log section.

### Agent State Updates

When an agent begins work:
1. Update its row in Agent Assignments: `Status: WORKING`, `Current Step: <description>`.
2. Append a `Started` entry to the Task Log.

When an agent completes:
1. Update its row: `Status: DONE`, `Current Step: Created N files`.
2. Append a `Completed` entry to the Task Log.

### Reading Contracts

Before generating code, an agent SHOULD:
1. Read the full Task Log.
2. Find the most recent `Contract published` entry from the relevant producing agent.
3. Parse the JSON contract.
4. Generate code that conforms to the contract's schemas and endpoints.

### Concurrency

Multiple agents may run in parallel. To prevent write conflicts:

- Use a file-level lock (`AGENTS.md.lock`) when writing.
- Acquire the lock, read the current file, modify, write, release.
- Lock timeout: 10 seconds. Log a warning if waiting longer.

The reference implementation uses `fcntl.flock()` on Unix and `msvcrt.locking()` on Windows.

---

## Extensions

The core protocol is the file structure above. Implementations MAY extend it with:

### Context Injection

Agents receive the current AGENTS.md content (truncated to 1500 characters) as part of their system prompt. This gives every agent awareness of the full system state without requiring explicit message passing.

### Memory Persistence

Contracts and task results MAY be persisted to a long-term memory store (e.g., SQLite, vector database) keyed by Task ID. This enables cross-session recall — a future task can retrieve the contract from a previous task.

### Telemetry

Implementations MAY include a telemetry section tracking:
- Total LLM calls
- Total input/output tokens
- Estimated cost in USD

### Visual Grounding

For agents with screen access, implementations MAY include a visual grounding section tracking recent UI interactions (tap targets, selectors, coordinates).

### User Scoping

In multi-user deployments, AGENTS.md is scoped per user:
- Self-hosted: `<project_root>/AGENTS.md`
- SaaS: `<project_root>/workspaces/<user_id>/AGENTS.md`

---

## Example: Full Session

```markdown
# AGENTS.md - Shared Agent State

## Current Task
| Field | Value |
|-------|-------|
| Task ID | task_20260605_143159 |
| Description | Create a stock presentation with investment advice |
| Status | COMPLETED |
| Requested By | orchestrator |

## Agent Assignments
| Agent | Model | Status | Current Step |
|-------|-------|--------|-------------|
| frontend | gemini-3.1-pro | DONE | Created 3 files |
| backend | claude-sonnet-4-6 | DONE | Created 2 files |
| qa | gpt-5.4 | DONE | Verified 2 contracts |
| iac | claude-sonnet-4-6 | IDLE | --- |

## Task Log
- [2026-06-05 14:32] backend: Started: Designing database schema
- [2026-06-05 14:33] backend: Contract published:
  ```json
  {
    "tables": [
      { "name": "stock_tickers", "columns": [...] },
      { "name": "investment_advice", "columns": [...] }
    ],
    "endpoints": [
      { "method": "GET", "path": "/api/stocks", "response": {...} }
    ]
  }
  ```
- [2026-06-05 14:33] backend: Completed: Built REST API with stock schema
- [2026-06-05 14:34] frontend: Started: Building Robinhood-themed UI
- [2026-06-05 14:36] frontend: Completed: Dark-mode UI with stock cards
- [2026-06-05 14:37] qa: Started: Verifying API contracts and UI
- [2026-06-05 14:38] qa: Completed: All contracts verified
```

---

## Implementation Checklist

For teams adopting the protocol:

- [ ] Create AGENTS.md at task start with all five sections
- [ ] Update Agent Assignments atomically (read-modify-write under lock)
- [ ] Append to Task Log (never modify existing entries)
- [ ] Publish contracts as fenced JSON in the Task Log
- [ ] Read latest contract before generating consuming code
- [ ] Inject AGENTS.md snapshot into agent system prompts
- [ ] Use file locking for concurrent writes

---

## FAQ

**Why markdown instead of JSON or YAML?**

Every LLM can read and write markdown natively without instruction. JSON requires careful escaping and bracket matching — a common source of agent errors. Markdown tables are both human-scannable and machine-parseable.

**Why a file instead of a database?**

Files require zero infrastructure. They work on any OS, in any language, with any LLM. They version-control naturally with git. A developer can read the full coordination state with `cat AGENTS.md` — no dashboard, no query language, no client library.

**Why append-only logs?**

Append-only ensures no agent can silently rewrite history. Every state change is preserved. This makes debugging multi-agent failures trivial — read the log top to bottom.

**How does this scale to many agents?**

The protocol has been tested with 4 concurrent agents producing 17 files in a single session. For larger systems (10+ agents), consider sharding — one AGENTS.md per subsystem, with a root-level file linking them.

**Can different agents use different LLM providers?**

Yes. The `Model` column in Agent Assignments is informational. The protocol is provider-agnostic. In practice, the Jarvis reference implementation routes frontend tasks to Gemini, backend to Claude, QA to GPT, and local tasks to Gemma — all coordinating through the same AGENTS.md.

---

## Reference Implementation

The reference implementation is [Jarvis](https://github.com/hasinrahman/jarvis), an open-source AI OS that uses AGENTS.md as its primary coordination mechanism.

Key files:
- `core/orchestrator/dag.py` — DAG executor that reads/writes AGENTS.md
- `core/orchestrator/distributed_sync.py` — Cross-platform file locking
- `core/orchestrator/context_sync.py` — AGENTS.md → agent prompt injection
- `agents/backend_agent.py` — Contract publishing to AGENTS.md + GBrain

---

## Changelog

### v1.0.0 (2026-06-05)

- Initial specification
- Core sections: Header, Current Task, Agent Assignments, Task Log, Contracts
- Concurrency model with file locking
- Extension points: Context Injection, Memory Persistence, Telemetry, Visual Grounding
