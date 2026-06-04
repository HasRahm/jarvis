# Contributing to Jarvis OS

Thank you for your interest in contributing to Jarvis OS! We welcome help in making this self-hosted Personal AI Operating System more powerful, secure, and easier to deploy.

---

## Code of Conduct

By participating in this project, you agree to abide by the terms of our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to the project maintainers.

---

## Local Development Setup

To set up a local development environment, follow these steps:

1. **Fork the Repository**: Create a fork of the repo on GitHub and clone it locally.
2. **Run the Bootstrap Script**:
   ```bash
   bash scripts/bootstrap.sh
   ```
   This script will install Bun, clone the external GBrain tool, configure a Python virtual environment, install all python requirements, and fetch the Playwright browser.
3. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your AI API keys. If you want to use cloud fallbacks, supply your `OPENROUTER_API_KEY`.
4. **Ollama Setup (Optional)**:
   If running models locally, make sure Ollama is installed and running, then pull the model:
   ```bash
   ollama pull qwen2.5-coder:7b  # or gemma4:31b-cloud if you have a powerful GPU
   ```
5. **Run the Diagnostic Check**:
   Verify your installation is correct:
   ```bash
   python jarvis-cli.py --doctor
   ```

---

## How to Contribute

### 1. Adding Custom Agent Modes
Jarvis utilizes specialized agent behavioral templates stored as markdown in the `modes/` directory (e.g., `modes/research.md`, `modes/excel.md`).
To add a new mode:
1. Create a markdown file under `modes/{my_new_mode}.md`.
2. Define the agent's system rules, tool preferences, and expected outputs.
3. Add the mode to the `AVAILABLE_MODES` list in `jarvis-cli.py`.
4. Test it:
   ```bash
   python jarvis-cli.py --mode my_new_mode --task "Test task"
   ```

### 2. Code Style & Linting
We use **Ruff** for Python formatting and linting.
Before submitting code, run the formatter to ensure consistent style:
```bash
ruff format .
ruff check . --fix
```
You can view our lint rules in [pyproject.toml](pyproject.toml).

### 3. Running Unit Tests
All changes must pass our test suite. Run tests offline (no API keys required) using:
```bash
JARVIS_CI=true python -m pytest tests/ -v
```

---

## Pull Request Guidelines

1. **Create a Branch**: Create a descriptive branch name (e.g., `feature/custom-mcp-server` or `bugfix/prevent-websocket-timeout`).
2. **Write Clean Commits**: Keep commit messages clear, concise, and focused.
3. **Include Documentation**: Update `README.md` or other documentation if you are changing command structures or adding config keys.
4. **Submit for Review**: Open a PR against the `main` branch. Ensure that all tests pass before requesting review.
