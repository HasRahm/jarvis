"""
Adaptive Router — learns per-role model success rates from telemetry.

Persists learned_preferences.json atomically under agents_md_lock.
All GBrain calls are lazy-imported; never imported at module level from brain/*.
Safe to import in any environment including CI.
"""
import sys

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREFS_PATH = os.path.join(_PROJECT_ROOT, "workspaces", "learned_preferences.json")

DEFAULT_PREFS = {
    "model_scores": {},      # {role: {model: {successes, failures, total}}}
    "routing_overrides": {}, # {role: model_string} — auto-computed best model
    "score_threshold": 0.6,  # min success rate to qualify as an override
    "min_samples": 5,        # minimum calls before any override is considered
    "last_updated": None,
}


def load_preferences() -> dict:
    """Read learned_preferences.json; return defaults if missing or corrupt."""
    print(f"[TRACE] agents.adaptive_router.load_preferences: enter", file=sys.stderr, flush=True)
    if not os.path.exists(_PREFS_PATH):
        return dict(DEFAULT_PREFS)
    try:
        with open(_PREFS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Back-fill keys added in future schema versions
        for k, v in DEFAULT_PREFS.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        print(f"[TRACE] agents.adaptive_router.load_preferences: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[adaptive_router] Could not load preferences: {e}. Using defaults.")
        return dict(DEFAULT_PREFS)


def record_model_outcome(role: str, model: str, success: bool):
    """
    Atomically record one success/failure sample for (role, model).
    Recomputes routing_overrides when the role has any model with >= min_samples.

    Thread-safe: acquires agents_md_lock on the preferences file.
    """
    print(f"[TRACE] agents.adaptive_router.record_model_outcome: enter", file=sys.stderr, flush=True)
    from core.orchestrator.distributed_sync import agents_md_lock

    os.makedirs(os.path.dirname(_PREFS_PATH), exist_ok=True)
    lock_path = _PREFS_PATH + ".lock"

    with agents_md_lock(lock_path):
        # Re-read inside the lock to avoid TOCTOU races with concurrent agents
        prefs = load_preferences()

        entry = (
            prefs["model_scores"]
            .setdefault(role, {})
            .setdefault(model, {"successes": 0, "failures": 0, "total": 0})
        )
        if success:
            entry["successes"] += 1
        else:
            entry["failures"] += 1
        entry["total"] += 1

        # Recompute override for this role
        min_s = prefs.get("min_samples", 5)
        threshold = prefs.get("score_threshold", 0.6)
        overrides = prefs.setdefault("routing_overrides", {})

        qualified = {
            m: d
            for m, d in prefs["model_scores"].get(role, {}).items()
            if d["total"] >= min_s
        }
        if qualified:
            best = max(
                qualified,
                key=lambda m: qualified[m]["successes"] / qualified[m]["total"],
            )
            best_rate = qualified[best]["successes"] / qualified[best]["total"]
            if best_rate > threshold:
                overrides[role] = best
            elif role in overrides:
                del overrides[role]

        prefs["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)


def get_adaptive_model(role: str) -> str | None:
    """
    Return the learned best model for a role, or None if insufficient data.
    Always returns None under JARVIS_CI=true (keeps CI fully offline).
    """
    print(f"[TRACE] agents.adaptive_router.get_adaptive_model: enter", file=sys.stderr, flush=True)
    if os.environ.get("JARVIS_CI") == "true":
        return None
    return load_preferences().get("routing_overrides", {}).get(role)


def compute_daily_summary(prefs: dict) -> str:
    """
    Return a CP1252-safe ASCII summary of model scores for GBrain storage.
    Used by scripts/dream_analyze.py nightly.
    """
    print(f"[TRACE] agents.adaptive_router.compute_daily_summary: enter", file=sys.stderr, flush=True)
    lines = [
        f"Jarvis Adaptive Router - Daily Summary ({datetime.now().strftime('%Y-%m-%d')})"
    ]
    scores = prefs.get("model_scores", {})
    overrides = prefs.get("routing_overrides", {})

    if not scores:
        lines.append("No model outcome data recorded yet.")
        return "\n".join(lines)

    for role, models in sorted(scores.items()):
        lines.append(f"\nRole: {role}")
        for m, d in sorted(models.items()):
            total = d.get("total", 0)
            rate = (d["successes"] / total * 100) if total > 0 else 0.0
            lines.append(f"  {m}: {d['successes']}/{total} ({rate:.1f}%)")
        if overrides.get(role):
            lines.append(f"  [OVERRIDE] {role} -> {overrides[role]}")

    return "\n".join(lines)
