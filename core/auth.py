"""
core/auth.py — Dual-mode authentication for Jarvis.

Self-hosted mode: validates against HERMES_SECRET (shared secret, original behaviour).
SaaS / multi-user mode: validates a Supabase JWT and extracts the user_id claim.

Which mode is active is determined by whether SUPABASE_JWT_SECRET is set in the
environment.  When it is set, every token that arrives over the WebSocket is treated
as a Supabase access token rather than the raw HERMES_SECRET string.
"""
import sys

import os
import secrets
import logging

logger = logging.getLogger(__name__)

# ── JWT validation (Supabase SaaS mode) ──────────────────────────────────────

def _validate_supabase_jwt(token: str) -> dict | None:
    """
    Decode and validate a Supabase-issued JWT.

    Returns the payload dict on success, or None on failure.
    Requires PyJWT (`pip install PyJWT`).
    """
    print(f"[TRACE] core.auth._validate_supabase_jwt: enter", file=sys.stderr, flush=True)
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
    if not jwt_secret:
        return None
    try:
        import jwt
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except Exception as exc:
        print(f"[TRACE] core.auth._validate_supabase_jwt: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[auth] Supabase JWT validation failed: {exc}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def authenticate(token: str) -> tuple[bool, str | None]:
    """
    Authenticate an incoming WebSocket token.

    Returns:
        (ok: bool, user_id: str | None)

    Behaviour:
        • If SUPABASE_JWT_SECRET is set → validate as Supabase JWT.
          On success, user_id is extracted from the JWT 'sub' claim.
        • Otherwise → compare directly against HERMES_SECRET (self-hosted mode).
          On success, user_id is None (single-user; no per-user scoping needed).
    """
    print(f"[TRACE] core.auth.authenticate: enter", file=sys.stderr, flush=True)
    supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")

    if supabase_jwt_secret:
        # ── SaaS mode: Supabase JWT ──────────────────────────────────────────
        payload = _validate_supabase_jwt(token)
        if payload is None:
            return False, None
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            logger.warning("[auth] Supabase JWT missing 'sub' claim.")
            return False, None
        return True, str(user_id)

    # ── Self-hosted mode: shared secret ─────────────────────────────────────
    # Fail closed: an unconfigured server must NOT accept any token. Previously
    # this defaulted to the constant "default_secret", which let anyone who knew
    # that string authenticate against an unconfigured, internet-exposed agent.
    hermes_secret = os.getenv("HERMES_SECRET", "")
    if not hermes_secret:
        logger.error("[auth] HERMES_SECRET is not set; rejecting all tokens (fail closed).")
        return False, None
    if token and secrets.compare_digest(token, hermes_secret):
        return True, None   # single-user; no user_id scoping
    return False, None


def _output_root() -> str:
    """Root for generated files (Phase 46 cluster 1).

    JARVIS_OUTPUT_ROOT (set by the CLI to the user's working dir / --output-dir) when present,
    else the install dir — so unset behaviour (tests, direct module use) is byte-identical to
    before, while CLI runs write into the user's project instead of the install directory.
    """
    print(f"[TRACE] core.auth._output_root: enter", file=sys.stderr, flush=True)
    env = os.environ.get("JARVIS_OUTPUT_ROOT")
    if env:
        return env
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_agents_md_path(user_id: str | None = None) -> str:
    """
    Return the path to AGENTS.md, scoped to user_id when running in SaaS mode.

    Self-hosted (user_id=None): <output_root>/AGENTS.md
    SaaS       (user_id set):   <output_root>/workspaces/<user_id>/AGENTS.md
    """
    print(f"[TRACE] core.auth.get_agents_md_path: enter", file=sys.stderr, flush=True)
    root = _output_root()
    if user_id:
        workspace = os.path.join(root, "workspaces", user_id)
        os.makedirs(workspace, exist_ok=True)
        return os.path.join(workspace, "AGENTS.md")
    return os.path.join(root, "AGENTS.md")


def get_workspace_path(role: str, user_id: str | None = None) -> str:
    """
    Return the agent workspace path, scoped to user_id in SaaS mode.

    Self-hosted: <output_root>/workspaces/<role>/
    SaaS:        <output_root>/workspaces/<user_id>/<role>/
    """
    print(f"[TRACE] core.auth.get_workspace_path: enter", file=sys.stderr, flush=True)
    root = _output_root()
    if user_id:
        path = os.path.join(root, "workspaces", user_id, role)
    else:
        path = os.path.join(root, "workspaces", role)
    os.makedirs(path, exist_ok=True)
    return path
