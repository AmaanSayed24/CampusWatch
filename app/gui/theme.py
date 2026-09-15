"""GUI design tokens: professional colour themes, typography and urgency styles.

The dashboard ships with two hand-tuned themes:

* ``Midnight`` — dark navy-slate. Default. Designed for long monitoring
  sessions and to match terminal-centric workflows.
* ``Studio``   — clean light theme.

Themes are exposed through named ttk styles (``Accent.TButton``,
``Card.TFrame``, ``Table.Treeview`` ...) so swapping themes at runtime simply
reconfigures the styles every widget already references.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Candidate font families (first one installed on the machine wins).
FAMILY_UI = ("Segoe UI", "Calibri", "Arial", "Helvetica", "TkDefaultFont")
FAMILY_MONO = ("Consolas", "Cascadia Mono", "Courier New", "Courier")


@dataclass(frozen=True)
class FontScale:
    title: int = 16
    section: int = 12
    body: int = 10
    small: int = 9
    micro: int = 8
    table: int = 9
    card_value: int = 24
    card_label: int = 8
    mono: int = 9


FONT_SCALE = FontScale()


def pick_family(root, candidates: tuple[str, ...]) -> str:
    """Return the first installed font family from *candidates*."""
    import tkinter as tk
    from tkinter import font as tkfont

    try:
        available = {f.lower() for f in tkfont.families(root)}
        for name in candidates:
            if name.lower() in available:
                return name
    except tk.TclError:
        pass
    return tkfont.nametofont("TkDefaultFont").actual("family")


@dataclass(frozen=True)
class Palette:
    """Flat colour tokens; every widget colour is derived from these."""

    background: str
    header: str
    surface: str
    card: str
    border: str
    primary: str
    primary_dim: str
    text: str
    text_muted: str
    text_faint: str
    success: str
    warning: str
    danger: str
    link: str


MIDNIGHT = Palette(
    background="#131722",
    header="#0D1117",
    surface="#1B2130",
    card="#202839",
    border="#2A3346",
    primary="#3E7BFA",
    primary_dim="#2E6BD8",
    text="#DDE3EC",
    text_muted="#8A94A6",
    text_faint="#5D6675",
    success="#4CC38A",
    warning="#F2A33C",
    danger="#E5533D",
    link="#6FA8FF",
)

STUDIO = Palette(
    background="#EEF1F6",
    header="#FFFFFF",
    surface="#FFFFFF",
    card="#FFFFFF",
    border="#D8DEE9",
    primary="#2563EB",
    primary_dim="#1D4FD8",
    text="#1B2430",
    text_muted="#5B6473",
    text_faint="#98A1B0",
    success="#16A34A",
    warning="#D97706",
    danger="#DC2626",
    link="#2563EB",
)

# Urgency -> (foreground, background) used for table rows.
MIDNIGHT_URGENCY = {
    "OVERDUE": ("#FF7A74", "#331723"),
    "DUE_TODAY": ("#FF9A5C", "#30200F"),
    "DUE_WITHIN_24H": ("#FFB45C", "#2F2412"),
    "DUE_WITHIN_3_DAYS": ("#FFD166", "#2F2813"),
    "DUE_WITHIN_7_DAYS": ("#B9E39A", "#1E2D1C"),
    "FUTURE": ("#87D3AB", "#16261E"),
    "NO_DEADLINE": ("#8A94A6", "#1B2130"),
    "COMPLETED": ("#6E7A8C", "#1B2130"),
}

STUDIO_URGENCY = {
    "OVERDUE": ("#C62828", "#FCE9E9"),
    "DUE_TODAY": ("#E65100", "#FDF0E7"),
    "DUE_WITHIN_24H": ("#E87A1D", "#FDF2E5"),
    "DUE_WITHIN_3_DAYS": ("#B8860B", "#FCF4E0"),
    "DUE_WITHIN_7_DAYS": ("#2E7D32", "#E9F5EC"),
    "FUTURE": ("#1E7A46", "#E6F4ED"),
    "NO_DEADLINE": ("#5B6473", "#FFFFFF"),
    "COMPLETED": ("#3A4452", "#F0F3F7"),
}


@dataclass(frozen=True)
class Theme:
    name: str
    is_dark: bool
    palette: Palette
    urgency_row: dict[str, tuple[str, str]]


THEMES = {
    "Midnight (dark)": Theme("Midnight (dark)", True, MIDNIGHT, MIDNIGHT_URGENCY),
    "Studio (light)": Theme("Studio (light)", False, STUDIO, STUDIO_URGENCY),
}

PREFS_FILE = PROJECT_ROOT / "data" / "gui_prefs.json"
_DEFAULT_THEME = "Midnight (dark)"


def load_theme_name() -> str:
    try:
        raw = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        name = raw.get("theme", _DEFAULT_THEME)
        return name if name in THEMES else _DEFAULT_THEME
    except (OSError, ValueError):
        return _DEFAULT_THEME


def save_theme_name(name: str) -> None:
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps({"theme": name}), encoding="utf-8")
    except OSError:
        pass  # prefs are best-effort only
