# /screen — Audit active window and dump visual & semantic screen graphs

Get a complete visual block of the current active screen, rendering both the structural semantic metadata and the physical halftone density graph.

## Usage

```
/screen
```

## How to Execute

When the user invokes `/screen`, do the following:

### Step 1: Run the Screen capture tool

Run this command synchronously and capture the stdout:

```bash
cd C:\Users\YOUR_USERNAME\jarvis
.venv\Scripts\python.exe -u jarvis-cli.py --screen
```

### Step 2: Render the Warp Block

Display the complete stdout content directly to the user as a single, formatted monospace block.

## Output Contents Included

1. **Active Application Properties**: Focus window title, process name, PID, and visual coordinates.
2. **Cognitive Screen Summary**: A Gemma4-synthesized high-level semantic summary explaining the app state and active context.
3. **Top 10 Action Elements**: List of action components (inputs, fields, buttons, options) with active coordinates.
4. **Halftone Visual Density Imprint**: A high-speed 32x32 visual grid mapping density blocks, outline borders, and contrast bounds.

## Why use /screen?

This is a built-in diagnostic tool for Jarvis developers to inspect how the visual graph layers are parsed, which is crucial for testing desktop GUI automation and debugging window alignment issues.
