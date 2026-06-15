# Shared Rules — All Jarvis Modes

These rules apply to EVERY Jarvis mode. Read these before executing any task.

## Core Principles

1. **Complete autonomy** — Execute every step without asking for human help
2. **Never stop early** — Complete ALL steps even if some data is partial
3. **Verify results** — Always verify that output files exist and are valid
4. **Retry on failure** — If a script or command fails, read the error, fix it, retry

## Tool Usage Rules

### Browser
- Do NOT use google.com for searches (blocks with CAPTCHA)
- Visit target sites directly instead
- Always `browser_navigate` before `browser_extract_text`

### Shell (run_command)
- Use PowerShell syntax on Windows
- Always check exit codes
- Capture both stdout and stderr

### Files (write_file / read_file)
- Use absolute paths on Windows: `C:\Users\YOUR_USERNAME\jarvis\scratch\`
- Before writing to a file, ensure no other process has it locked
- Verify file sizes after creation

### Desktop Automation
- Use `desktop_get_active_window` before clicking to confirm context
- Use `desktop_focus_window` to bring target apps to foreground
- Use realistic delays between actions

## Output Format

Always end your response with a structured summary:
- What was accomplished
- Files created (with full paths)
- Any issues encountered
- Recommended next steps (if any)

## Working Directory

All scratch files go in: `C:\Users\YOUR_USERNAME\jarvis\scratch\`
