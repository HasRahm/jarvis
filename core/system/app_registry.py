# core/system/app_registry.py

APP_CAPABILITIES = {
    # ── Tier 1: Full API ─────────────────────────────────
    "figma": {
        "tier": 1,
        "api": "FigmaAPIClient",
        "can_read":  True,
        "can_write": False,   # REST API read-only; writes via plugin
        "mcp": "figma-mcp",
    },
    "github": {
        "tier": 1,
        "api": "GitHubAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "github-mcp",
    },
    "google docs": {
        "tier": 1,
        "api": "GoogleDocsAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "gdrive-mcp",
    },
    "google sheets": {
        "tier": 1,
        "api": "GoogleSheetsAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "gdrive-mcp",
    },
    "slack": {
        "tier": 1,
        "api": "SlackAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "slack-mcp",
    },
    "notion": {
        "tier": 1,
        "api": "NotionAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "notion-mcp",
    },
    "gmail": {
        "tier": 1,
        "api": "GmailAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "gmail-mcp",
    },
    "calendar": {
        "tier": 1,
        "api": "GoogleCalendarAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "calendar-mcp",
    },
    "spotify": {
        "tier": 1,
        "api": "SpotifyAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "spotify-mcp",
    },
    "linear": {
        "tier": 1,
        "api": "LinearAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "linear-mcp",
    },
    "jira": {
        "tier": 1,
        "api": "JiraAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "jira-mcp",
    },
    "supabase": {
        "tier": 1,
        "api": "SupabaseAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "supabase-mcp",
    },
    "vercel": {
        "tier": 1,
        "api": "VercelAPIClient",
        "can_read":  True,
        "can_write": True,
        "mcp": "vercel-mcp",
    },

    # ── Tier 2: MCP only (no direct API) ─────────────────
    "vs code": {
        "tier": 2,
        "mcp": "vscode-mcp",
        "can_read":  True,
        "can_write": True,
        "background_msg": True,
    },
    "chrome": {
        "tier": 2,
        "mcp": "chrome-mcp",
        "can_read":  True,
        "can_write": True,
        "background_msg": False,
    },

    # ── Tier 3: Background Win32 messaging ───────────────
    "notepad": {
        "tier": 3,
        "background_msg": True,
        "can_read":  True,
        "can_write": True,
    },
    "excel": {
        "tier": 3,
        "background_msg": True,
        "api": "ExcelCOMClient",   # COM automation
        "can_read":  True,
        "can_write": True,
    },
    "word": {
        "tier": 3,
        "background_msg": True,
        "api": "WordCOMClient",
        "can_read":  True,
        "can_write": True,
    },
    "powerpoint": {
        "tier": 3,
        "background_msg": True,
        "api": "PowerPointCOMClient",
        "can_read":  True,
        "can_write": True,
    },
    "terminal": {
        "tier": 3,
        "background_msg": True,
        "can_read":  True,
        "can_write": True,
    },

    # ── Tier 4: Foreground required ───────────────────────
    "photoshop": {
        "tier": 4,
        "background_msg": False,
        "virtual_display": True,   # can use virtual display
        "can_read":  True,
        "can_write": True,
    },
    "blender": {
        "tier": 4,
        "background_msg": False,
        "virtual_display": True,
        "has_api": True,           # Blender Python API
        "can_read":  True,
        "can_write": True,
    },
    "steam": {
        "tier": 4,
        "background_msg": False,
        "virtual_display": True,
        "can_read":  True,
        "can_write": False,
    },
}
