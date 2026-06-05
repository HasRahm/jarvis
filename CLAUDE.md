# Antigravity — Local AI Agent (Jarvis Framework) for Claude Code

> **Token saver**: Antigravity runs on local Ollama (free). Delegate research, browsing, diagnostics, and automation tasks to Antigravity instead of spending Claude API tokens.

## What Is Antigravity


Jarvis is a local AI agent powered by Ollama (`gemma4:31b-cloud`). It has full system access:
- 🌐 **Headless browser** (Playwright) — navigate, extract text, screenshot
- 💻 **Shell execution** — run any command, scripts, installers
- 🖥️ **Desktop automation** — mouse clicks, keyboard input, window management
- 📁 **File system** — read, write, list directories
- 🧠 **Memory** — GBrain persistent memory (when available)
- 📊 **Excel/document generation** — styled spreadsheets with openpyxl

## When to Delegate to Jarvis

**DELEGATE** (saves tokens):
- Web research & data scraping (Jarvis has a headless Chromium browser)
- System diagnostics & troubleshooting (registry, event viewer, processes)
- Desktop GUI automation (clicking, typing, window management)
- File/Excel/document generation from structured data
- Multi-step shell command sequences
- Repetitive tasks that require many tool calls

**KEEP** (needs Claude's reasoning):
- Complex architectural design decisions
- Code review requiring deep semantic understanding
- Tasks that need your current conversation context
- Security-sensitive operations requiring human oversight

## How to Use

### Slash Commands
```
/jarvis [mode] [task description]
/screen
```

### Direct CLI
```bash
cd C:\Users\YOUR_USERNAME\jarvis
.venv\Scripts\python.exe -u jarvis-cli.py --mode [mode] --task "[description]"
.venv\Scripts\python.exe -u jarvis-cli.py --screen
```

## Available Modes

| Mode | Use When | Example |
|------|----------|---------|
| `research` | Web research, job searching, data collection | `/jarvis research Find 20 AI startups hiring entry-level` |
| `diagnose` | System troubleshooting, app debugging | `/jarvis diagnose Why won't the Claude app open` |
| `browse` | Scrape a specific URL or extract web content | `/jarvis browse Extract all job listings from https://example.com/jobs` |
| `desktop` | GUI automation — click, type, navigate apps | `/jarvis desktop Open Excel and create a new spreadsheet` |
| `excel` | Create styled spreadsheets from data | `/jarvis excel Create a tracker with columns: Company, Role, Status` |
| `shell` | Run multi-step shell sequences | `/jarvis shell Check disk space, list large files, clean temp` |
| `screen` | Audit active window, child controls, and visual layout | `/jarvis screen Audit my current VS Code window context` |
| `auto` | Let Antigravity decide the best approach | `/jarvis auto Set up a Python virtual environment and install requirements` |

## Architecture

```
Claude Code  ──delegates──▶  jarvis-cli.py  ──▶  Hermes Runner  ──▶  Ollama (local, free)
                                   │
                                   ├── modes/_shared.md (behavioral rules)
                                   ├── modes/{mode}.md (mode-specific instructions)
                                   └── tools/dispatcher.py (browser, shell, desktop, files)
```

## File Structure

```
jarvis/
├── CLAUDE.md                    # This file (Claude Code reads this)
├── jarvis-cli.py                # CLI wrapper for Claude Code integration
├── .claude/commands/jarvis.md   # Slash command definition
├── modes/                       # Behavioral mode definitions
│   ├── _shared.md               # Shared rules for all modes
│   ├── research.md              # Web research mode
│   ├── diagnose.md              # System diagnostics mode
│   ├── browse.md                # URL scraping mode
│   ├── desktop.md               # Desktop automation mode
│   ├── excel.md                 # Spreadsheet generation mode
│   └── shell.md                 # Shell automation mode
├── core/hermes/hermes_cli_runner.py  # Autonomous agent loop
├── core/system/llm_adapter.py        # Ollama/OpenRouter routing
└── tools/dispatcher.py               # Tool definitions & dispatch
```

## Important Notes

- Jarvis runs **locally on Ollama** — no API costs, no rate limits
- Jarvis cannot access your Claude Code conversation context
- Write clear, self-contained task descriptions when delegating
- Jarvis will output a final report when done — use that in your response
- If Ollama is down, Jarvis falls back to OpenRouter (has rate limits on free tier)

## Future Phase Roadmap

### Phase 22 — Spatial Context Cortex (Ambient Spatial Awareness)
* **Ambience / Nervous System:** Runs a continuous parallel sensory loop (100ms cycle) beneath the conscious execution flow to detect background world shifts.
* **Integrated Sensory Streams:**
  * **Braille Layer:** Structural texture via accessibility tree hashes and DOM fingerprints (window hwnd, page URL, tree layout).
  * **Sound Layer:** Audio environment profile tracking which apps are producing audio (e.g. `chrome.exe`, `code.exe`) and active keystroke targets.
  * **Vibration Layer:** System metric spikes and delta bursts (CPU, RAM jump, I/O burst, network activity).
  * **Air Movement Layer:** Cursor trajectory flow, tracking if mouse moves out of the task region or if keyboard focuses a new window.
* **Spatial Cortex & Context Interrupts:** Fuses all four streams into a unified Context Fingerprint. If the fingerprint shifts (measured via hash distance delta > 0.3), it immediately triggers a `CONTEXT_SWITCH` interrupt, suspending the agent's tools until the original "home" context returns, preventing accidental CLI execution on incorrect apps.
