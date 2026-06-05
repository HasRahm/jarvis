# Why We Replaced Shared Model Context with a Markdown File

When we started building [Jarvis](https://github.com/hasinrahman/jarvis) — a multi-agent AI system where different LLMs handle different parts of a coding task — the first coordination problem we hit was simple: how does the frontend agent know what API the backend agent just built?

Every existing approach felt wrong. Message passing (AutoGen, CrewAI) loses state on crash. Shared databases require infrastructure we didn't want. Agent-to-agent function calls create tight coupling between components that should be independent.

So we tried something stupid: we put a markdown file in the project root called `AGENTS.md` and had every agent read and write to it.

It worked embarrassingly well.

## What AGENTS.md looks like

```markdown
## Agent Assignments
| Agent | Model | Status | Current Step |
|-------|-------|--------|-------------|
| backend | claude-sonnet-4-6 | DONE | Created 2 files |
| frontend | gemini-3.1-pro | WORKING | Building stock cards |
| qa | gpt-5.4 | IDLE | --- |

## Task Log
- [14:33] backend: Contract published:
  { "endpoints": [{ "GET": "/api/stocks", ... }] }
- [14:35] frontend: Started: Reading backend contract
```

That's it. The backend agent finishes, writes its API contract as JSON in the log. The frontend agent reads the log, finds the contract, and builds against it. No message bus. No serialization library. No SDK.

## Why it works better than we expected

**Every LLM reads markdown natively.** We don't need to teach Claude how to parse AGENTS.md — it already knows. We don't need to serialize state into a format the model understands — markdown *is* the format. This eliminates an entire class of parsing bugs that plague JSON-based agent communication.

**Humans can read it too.** When a multi-agent run fails at step 5 of 7, we don't dig through logs or attach a debugger. We open AGENTS.md and read it top to bottom. The Task Log tells us exactly what happened, in order, with timestamps. The Agent Assignments table shows who was working on what. The contract JSON shows what interface was agreed upon.

**It version-controls for free.** Every AGENTS.md gets committed with the code it produced. Six months later, when someone asks "why did the frontend use this API shape?", the answer is in the git history — the backend agent published that contract at 14:33 on June 5th.

**Concurrency is a solved problem.** File locking has existed for decades. We use `fcntl.flock()` on Linux and `msvcrt.locking()` on Windows. Four agents writing concurrently to the same AGENTS.md has never caused a data race in production.

## The contract pattern changed everything

The real breakthrough wasn't the file — it was using it for **contract negotiation**. When the backend agent finishes, it publishes a JSON contract describing its tables and endpoints directly into the Task Log. The frontend agent's first action is always: read the latest contract, then generate code that conforms to it.

This means the backend and frontend agents never talk to each other directly. They don't need to. The contract is the interface. If the backend changes, it publishes a new contract. If the frontend needs something different, the QA agent catches the mismatch.

We tested this with a 7-step task: database schema → UI layout → data service → stock cards → API endpoint → API integration → QA verification. Four different LLMs (Claude, Gemini, GPT-5.4, Gemma4), 17 files produced, all coordinated through a single AGENTS.md file that a human can read in 30 seconds.

## Try it

We've published the protocol as an [open specification](https://github.com/hasinrahman/jarvis/blob/main/spec/AGENTS_PROTOCOL.md). It's framework-agnostic — you can implement it in any language, with any LLM provider, on any OS.

The spec is short. The implementation is shorter. The results surprised us.

---

*Jarvis is an open-source AI OS that routes every coding task to the best model automatically. [GitHub](https://github.com/hasinrahman/jarvis)*
