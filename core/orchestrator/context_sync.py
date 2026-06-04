import json
import os
from core.hermes.server import get_visual_context_history, get_speech_history

def compile_converged_context() -> str:
    """
    Compiles a unified markdown context block containing:
    1. Active visual coordinate grounding tap history.
    2. Vocalized agent status history (last 10 speech messages).
    3. Operational telemetry spend summary.
    4. AGENTS.md snapshot.

    Returns:
        str: Fresh compiled markdown context segment.
    """
    context_sections = []

    # 1. Visual Grounding History
    taps = get_visual_context_history()
    if taps:
        context_sections.append("### Active Visual Grounding History (Last 5 Taps)")
        for idx, tap in enumerate(taps, 1):
            selector = tap.get("selector", "unknown-selector")
            tag = tap.get("tag_name", "UNKNOWN")
            classes = ", ".join(tap.get("classes", [])) or "None"
            text = tap.get("inner_text", "")
            context_sections.append(
                f"- Tap {idx}: Tag `{tag}`, Selector `{selector}`, Classes: `{classes}`, Inner Text: \"{text}\""
            )
    else:
        context_sections.append("### Active Visual Grounding History\n- No tap history registered yet.")

    # 2. Vocalized Agent Status History
    speech_log = get_speech_history()
    if speech_log:
        context_sections.append("### Vocalized Agent Status History (Last 10)")
        for entry in speech_log:
            ts = entry.get("ts", "")
            role = entry.get("role", "system")
            msg = entry.get("text", "")
            context_sections.append(f'- [{ts}] [{role}] "{msg}"')
    else:
        context_sections.append("### Vocalized Agent Status History\n- No vocalized history yet.")

    # 4. Telemetry Spend Summary
    telemetry_path = "workspaces/telemetry.json"
    total_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost_usd = 0.0
    
    if os.path.exists(telemetry_path):
        try:
            with open(telemetry_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    total_calls = len(data)
                    for entry in data:
                        total_input_tokens += entry.get("input_tokens", 0)
                        total_output_tokens += entry.get("output_tokens", 0)
                        total_cost_usd += entry.get("cost_usd", 0.0)
        except Exception:
            pass

    context_sections.append(
        f"### Operational Spend & Telemetry Summary\n"
        f"- Total LLM calls: `{total_calls}`\n"
        f"- Total input tokens: `{total_input_tokens}`\n"
        f"- Total output tokens: `{total_output_tokens}`\n"
        f"- Estimated cost: `${total_cost_usd:.5f} USD`"
    )

    # 5. AGENTS.md Snapshot
    agents_md_path = "AGENTS.md"
    if os.path.exists(agents_md_path):
        try:
            with open(agents_md_path, "r", encoding="utf-8") as f:
                content = f.read()
                context_sections.append(f"### Current AGENTS.md Protocol Status\n```markdown\n{content[:1500]}\n```")
        except Exception:
            pass

    return "\n\n".join(context_sections)
