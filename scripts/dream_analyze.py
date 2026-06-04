"""
dream_analyze.py - Nightly self-improvement pass.

Reads learned_preferences.json, generates an ASCII model-score summary,
and persists it to GBrain under daily-summary/{date}.

Called by scripts/cron_dream.ps1 after `gbrain dream`.
Fully guarded by JARVIS_CI check -- safe to import in test environments.
"""

import os
import sys
from datetime import datetime

# Allow running as a script from any working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    if os.environ.get("JARVIS_CI") == "true":
        print("[DREAM] JARVIS_CI=true. Skipping dream_analyze in CI.")
        return

    try:
        from agents.adaptive_router import load_preferences, compute_daily_summary
        prefs = load_preferences()
        summary = compute_daily_summary(prefs)
    except Exception as e:
        print(f"[DREAM] Summary computation failed: {e}")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"daily-summary/{date_str}"

    try:
        from brain.write import brain_write
        brain_write(slug, summary)
    except Exception as e:
        print(f"[DREAM] GBrain write failed: {e}")
        return

    print("[DREAM] Analysis complete. Summary stored to GBrain.")


if __name__ == "__main__":
    main()
