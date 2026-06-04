# /jarvis — Delegate task to local Jarvis AI agent

Delegate a task to Jarvis, a local AI agent running on Ollama (free, no API costs).
Jarvis has access to: headless browser, shell, desktop automation, file system, memory.

## Usage

```
/jarvis [mode] [task description]
```

## Modes

- `research` — Web research, job searching, data collection
- `diagnose` — System troubleshooting, app debugging  
- `browse` — Scrape URLs, extract web content
- `desktop` — GUI automation (mouse, keyboard, windows)
- `excel` — Create styled spreadsheets
- `shell` — Multi-step shell command sequences
- `auto` — Let Jarvis decide the best approach (default)

## How to Execute

When the user invokes `/jarvis`, do the following:

### Step 1: Write the task prompt

Create a prompt file at `C:\Users\YOUR_USERNAME\jarvis\scratch\jarvis_task_prompt.txt` containing:
- The mode-specific instructions (from `modes/{mode}.md`)
- The user's task description
- Any relevant context from the current conversation

### Step 2: Launch Jarvis

Run this command and wait for it to complete:

```bash
cd C:\Users\YOUR_USERNAME\jarvis
.venv\Scripts\python.exe -u jarvis-cli.py --mode {mode} --task "{task description}"
```

### Step 3: Report results

Read Jarvis's output and incorporate it into your response to the user.
If Jarvis created files (Excel, screenshots, etc.), mention their paths.

## Path Reference

| Alias | Absolute Path |
|-------|---------------|
| `jarvis/` | `C:\Users\YOUR_USERNAME\jarvis` |
| `scratch/` | `C:\Users\YOUR_USERNAME\jarvis\scratch` |
| `modes/` | `C:\Users\YOUR_USERNAME\jarvis\modes` |
| `venv python` | `C:\Users\YOUR_USERNAME\jarvis\.venv\Scripts\python.exe` |

## Why Delegate to Jarvis?

Jarvis runs on **local Ollama** — every task delegated saves your Claude API tokens.
A typical research task costs ~50K tokens on Claude but only ~2K when delegated to Jarvis
(just the prompt + result summary).

## Example

User: `/jarvis research Find 10 AI startups in NYC hiring junior engineers`

You should run:
```bash
cd C:\Users\YOUR_USERNAME\jarvis
.venv\Scripts\python.exe -u jarvis-cli.py --mode research --task "Find 10 AI startups in NYC hiring junior engineers"
```

Then read the output and present the findings to the user.
