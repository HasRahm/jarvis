"""
Design System (Phase 36B) — a concrete, opinionated design brief injected into the frontend
agent so generated UIs look intentionally designed instead of default-browser plain.

The leading agentic builders (Antigravity, bolt) produce good UI because the model is grounded
in a real design system — tokens, a type scale, spacing rhythm, and component patterns — not just
told to "make it responsive." `get_design_brief()` returns that grounding as a prompt block.

Themes are named token sets. The default ("aurora") is a clean, modern, accessible light/dark
palette. Callers may pass a theme name to switch palettes while keeping the same structure.
"""
import sys
from core.trace import trace as _jtrace

# Named palettes (semantic tokens). Keep these tasteful and high-contrast (WCAG AA).
_THEMES = {
    "aurora": {  # default — calm indigo/slate, modern SaaS
        "bg": "#0b0f1a", "surface": "#141a2a", "surface_alt": "#1b2336",
        "text": "#e7ecf5", "muted": "#9aa6bf", "border": "#243049",
        "primary": "#6366f1", "primary_hover": "#4f46e5", "accent": "#22d3ee",
        "success": "#22c55e", "warning": "#f59e0b", "danger": "#ef4444",
        "light_bg": "#f7f8fb", "light_surface": "#ffffff", "light_text": "#0f172a",
        "light_muted": "#5b6577", "light_border": "#e6e9f0",
    },
    "warmsand": {  # warm, editorial, high-end
        "bg": "#1a1613", "surface": "#241e19", "surface_alt": "#2e2620",
        "text": "#f3ece2", "muted": "#b8a994", "border": "#3a3028",
        "primary": "#d97706", "primary_hover": "#b45309", "accent": "#14b8a6",
        "success": "#16a34a", "warning": "#eab308", "danger": "#dc2626",
        "light_bg": "#faf7f2", "light_surface": "#ffffff", "light_text": "#1c1917",
        "light_muted": "#78716c", "light_border": "#ede8e0",
    },
    "mono": {  # minimal black/white, product-focused
        "bg": "#0a0a0a", "surface": "#141414", "surface_alt": "#1c1c1c",
        "text": "#fafafa", "muted": "#a3a3a3", "border": "#2a2a2a",
        "primary": "#fafafa", "primary_hover": "#d4d4d4", "accent": "#3b82f6",
        "success": "#22c55e", "warning": "#f59e0b", "danger": "#ef4444",
        "light_bg": "#ffffff", "light_surface": "#fafafa", "light_text": "#0a0a0a",
        "light_muted": "#737373", "light_border": "#e5e5e5",
    },
}

DEFAULT_THEME = "aurora"


def list_themes() -> list:
    return list(_THEMES.keys())


def _tokens_block(theme: str) -> str:
    _jtrace(f"[TRACE] agents.design_system._tokens_block: enter")
    t = _THEMES.get(theme, _THEMES[DEFAULT_THEME])
    return (
        ":root {\n"
        f"  --bg: {t['bg']}; --surface: {t['surface']}; --surface-alt: {t['surface_alt']};\n"
        f"  --text: {t['text']}; --muted: {t['muted']}; --border: {t['border']};\n"
        f"  --primary: {t['primary']}; --primary-hover: {t['primary_hover']}; --accent: {t['accent']};\n"
        f"  --success: {t['success']}; --warning: {t['warning']}; --danger: {t['danger']};\n"
        "  --radius: 12px; --radius-sm: 8px; --radius-lg: 20px;\n"
        "  --shadow: 0 1px 2px rgba(0,0,0,.2), 0 8px 24px rgba(0,0,0,.25);\n"
        "  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;\n"
        "  --space-6: 24px; --space-8: 32px; --space-12: 48px; --space-16: 64px;\n"
        "  --font: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;\n"
        "  --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;\n"
        "  --maxw: 1120px;\n"
        "}\n"
        "@media (prefers-color-scheme: light) {\n"
        f"  :root {{ --bg: {t['light_bg']}; --surface: {t['light_surface']}; "
        f"--surface-alt: {t['light_bg']}; --text: {t['light_text']}; "
        f"--muted: {t['light_muted']}; --border: {t['light_border']}; }}\n"
        "}"
    )


def get_design_brief(task: str = "", theme: str | None = None) -> str:
    """Return a `<design_system>` prompt block grounding the frontend agent in a real design
    system. `theme` selects a palette (defaults to DEFAULT_THEME)."""
    _jtrace(f"[TRACE] agents.design_system.get_design_brief: enter")
    theme = theme if theme in _THEMES else DEFAULT_THEME
    return f"""
<design_system theme="{theme}">
  <principles>
    Design like a senior product designer. Aim for the polish of Linear, Vercel, and Stripe:
    generous whitespace, clear visual hierarchy, restrained color, crisp typography, and motion
    that is subtle and purposeful. Never ship default-browser styling.
  </principles>

  <tokens>
    Define these CSS custom properties at the top of your stylesheet and use ONLY these tokens
    (no hard-coded hex/px scattered through the code). Honor light/dark via prefers-color-scheme:
```css
{_tokens_block(theme)}
```
  </tokens>

  <typography>
    - Load Inter (and JetBrains Mono for code) from Google Fonts.
    - Scale: display 48/56, h1 32/40, h2 24/32, h3 20/28, body 16/26, small 14/22. Use rem.
    - Body text uses var(--muted) for secondary copy; headings use var(--text), weight 600-700.
    - Max line length ~70ch for readable paragraphs.
  </typography>

  <layout>
    - Center content in a container: max-width var(--maxw); padding-inline clamp(16px, 5vw, 32px).
    - Use CSS grid/flex with the spacing tokens for rhythm (multiples of 4/8px). Mobile-first;
      add responsive breakpoints at 640/768/1024px.
  </layout>

  <components>
    - Buttons: var(--radius-sm), solid var(--primary) with white text for primary; subtle
      var(--surface-alt) + border for secondary; clear :hover (--primary-hover), :focus-visible
      ring, and :active states. Min touch target 40px.
    - Cards/panels: var(--surface), 1px var(--border), var(--radius), var(--shadow), padding
      var(--space-6).
    - Inputs: var(--surface-alt) bg, 1px var(--border), var(--radius-sm), visible focus ring in
      var(--primary), labels above fields, inline validation states.
    - Nav/header: sticky, var(--surface) with bottom border, logo left, actions right.
  </components>

  <quality_bar>
    - WCAG AA contrast; visible :focus-visible outlines; respect prefers-reduced-motion.
    - Transitions 150-200ms ease on color/transform/opacity only. No layout-thrashing animations.
    - Empty/loading/error states for any data-driven UI.
    - Pixel-consistent spacing — everything snaps to the spacing scale.
  </quality_bar>

  <implementation>
    - For a single-file page: put all CSS in one <style> block using the tokens above.
    - Prefer semantic HTML5 (header/nav/main/section/footer) and accessible roles/aria.
    - Keep JS unobtrusive; wire to the backend contract endpoints exactly.
  </implementation>
</design_system>"""
