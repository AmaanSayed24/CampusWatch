"""CampusWatch desktop dashboard.

A professional, single-window Tkinter front-end on top of the *same* agent
stack the CLI drives (App -> Repository / SyncService / Notifier). Nothing is
forked; the GUI is purely an alternative view.

Highlights
    * live stat cards - outstanding / overdue / due today / next 7 days / none
    * colour-coded assignment table, rows tinted by urgency, right-click menu
    * details panel with manual deadlines and status actions
    * background sync runs (worker thread + event queue, UI never blocks),
      optional in-window auto-scan every CHECK_INTERVAL_MINUTES
    * activity log, sync-run history and a configuration panel
    * two professional themes - Midnight (dark) and Studio (light)

The GUI is pure stdlib (tkinter) - zero new dependencies.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from app.config.settings import PROJECT_ROOT as PROJECT_ROOT_DIR
from app.config.settings import Settings
from app.gui import theme as gui_theme
from app.gui.sync_worker import SyncEvent, SyncWorker
from app.main import App
from app.parsers.deadline_parser import parse_deadline
from app.services.deadline_engine import (
    compute_urgency,
    format_remaining,
    time_remaining,
)
from app.utils.dates import format_deadline

# --- presentation constants -------------------------------------------------

FILTERS = (
    "All", "Overdue", "Due today", "Next 7 days", "Later", "No deadline", "Completed",
)
WEEK_SET = frozenset(
    {"DUE_TODAY", "DUE_WITHIN_24H", "DUE_WITHIN_3_DAYS", "DUE_WITHIN_7_DAYS"}
)

URGENCY_LABELS = {
    "OVERDUE": "OVERDUE",
    "DUE_TODAY": "DUE TODAY",
    "DUE_WITHIN_24H": "DUE < 24H",
    "DUE_WITHIN_3_DAYS": "DUE < 3D",
    "DUE_WITHIN_7_DAYS": "DUE < 7D",
    "FUTURE": "LATER",
    "NO_DEADLINE": "NO DATE",
    "COMPLETED": "DONE",
}

URGENCY_RANK = {
    "OVERDUE": 0, "DUE_TODAY": 1, "DUE_WITHIN_24H": 2, "DUE_WITHIN_3_DAYS": 3,
    "DUE_WITHIN_7_DAYS": 4, "FUTURE": 5, "NO_DEADLINE": 6, "COMPLETED": 7,
}

CARD_SPECS = (
    ("outstanding", "OUTSTANDING", "Primary"),
    ("overdue", "OVERDUE", "Danger"),
    ("due_today", "DUE TODAY", "Warning"),
    ("next_7", "NEXT 7 DAYS", "Success"),
    ("no_deadline", "NO DEADLINE", "Muted"),
)

DONE_STATUSES = frozenset({"COMPLETED", "SUBMITTED"})


class GuiApp(tk.Tk):
    """The CampusWatch desktop dashboard window."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self._app = App(settings=settings)
        self._settings = self._app.settings
        self._worker = SyncWorker(self._app)
        self._interval_minutes = self._settings.check_interval_minutes

        self._rows: list[dict] = []
        self._row_by_id: dict[int, dict] = {}
        self._subject_names: dict[int, str] = {}
        self._filter = tk.StringVar(value="All")
        self._auto_sync = tk.BooleanVar(value=False)
        self._countdown = self._interval_minutes * 60
        self._last_run_summary = "no scans yet"
        self._sync_running = False
        self._after_ids: set[str] = set()
        self._modal_windows: set[tk.Toplevel] = set()

        self._clock_var = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="● idle")
        self._theme_var = tk.StringVar(value=gui_theme.load_theme_name())
        self._current_theme = gui_theme.THEMES[self._theme_var.get()]

        self.title("CampusWatch — Assignment Monitoring Agent")
        self.geometry("1320x820")
        self.minsize(1080, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._resolve_fonts()
        self._build_ui()
        self._apply_theme(self._current_theme)
        self._schedule(120, self._delayed_start)

    # --- scheduling helpers ------------------------------------------------

    def _schedule(self, ms: int, fn, *args) -> str:
        aid = self.after(ms, fn, *args)
        self._after_ids.add(aid)
        return aid

    def _delayed_start(self) -> None:
        self._refresh_data()
        self._poll_events()
        self._tick()

    def _resolve_fonts(self) -> None:
        ui = gui_theme.pick_family(self, gui_theme.FAMILY_UI)
        mono = gui_theme.pick_family(self, gui_theme.FAMILY_MONO)
        f = gui_theme.FONT_SCALE
        self.fonts = {
            "title": (ui, f.title, "bold"),
            "section": (ui, f.section, "bold"),
            "body": (ui, f.body),
            "small": (ui, f.small),
            "micro": (ui, f.micro),
            "table": (ui, f.table),
            "mono": (mono, f.mono),
            "card_value": (ui, f.card_value, "bold"),
            "card_label": (ui, f.card_label),
        }

    # --- layout -------------------------------------------------------------

    def _build_ui(self) -> None:
        self.rowconfigure(3, weight=3)  # table area
        self.rowconfigure(4, weight=2)  # notebook
        self.columnconfigure(0, weight=1)
        self._build_header()
        self._build_cards()
        self._build_filters_bar()
        self._build_table_area()
        self._build_notebook()
        self._build_footer()
    def _build_header(self) -> None:
        self._header = ttk.Frame(self, style="Header.TFrame")
        self._header.grid(row=0, column=0, sticky="ew")
        self._header.columnconfigure(1, weight=1)

        brand = ttk.Frame(self._header, style="Header.TFrame")
        brand.grid(row=0, column=0, sticky="w", padx=(16, 0))
        ttk.Label(
            brand, text="CampusWatch", style="HeaderBrand.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            brand,
            text="College portal · assignment tracking · deadline reminders",
            style="HeaderMuted.TLabel",
        ).grid(row=1, column=0, sticky="w")

        right = ttk.Frame(self._header, style="Header.TFrame")
        right.grid(row=0, column=2, sticky="e", padx=(0, 16))
        ttk.Label(right, text="Theme", style="HeaderMuted.TLabel").pack(
            side="left", padx=(0, 6)
        )
        self._theme_picker = ttk.Combobox(
            right,
            values=list(gui_theme.THEMES),
            state="readonly",
            width=18,
            textvariable=self._theme_var,
        )
        self._theme_picker.pack(side="left", padx=(0, 14))
        self._theme_picker.bind("<<ComboboxSelected>>", self._on_theme_change)
        ttk.Label(
            right, textvariable=self._clock_var, style="HeaderClock.TLabel"
        ).pack(side="left")

    def _build_cards(self) -> None:
        wrap = ttk.Frame(self, style="BG.TFrame")
        wrap.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 2))
        self._card_vars: dict[str, tk.StringVar] = {}
        for i, (_key, label, color) in enumerate(CARD_SPECS):
            wrap.columnconfigure(i, weight=1)
            var = tk.StringVar(value="—")
            self._card_vars[_key] = var
            card = ttk.Frame(wrap, style="Card.TFrame")
            card.grid(row=0, column=i, sticky="nsew", padx=6, pady=2)
            ttk.Frame(card, style=f"CardAccent.{color}.TFrame").grid(
                row=0, column=0, sticky="ew"
            )
            card.columnconfigure(0, weight=1)
            ttk.Label(card, textvariable=var, style=f"Value.{color}.TLabel").grid(
                row=1, column=0, sticky="ew"
            )
            ttk.Label(card, text=label, style="CardLabel.TLabel").grid(
                row=2, column=0, sticky="ew"
            )

    def _build_filters_bar(self) -> None:
        bar = ttk.Frame(self, style="Surface.TFrame")
        bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 0))
        self._filter_buttons: dict[str, ttk.Button] = {}
        for key in FILTERS:
            btn = ttk.Button(
                bar, text=key, style="Filter.TButton",
                command=lambda k=key: self._set_filter(k),
            )
            btn.pack(side="left", padx=1, pady=6)
            self._filter_buttons[key] = btn
        ttk.Separator(bar, orient="vertical").pack(
            side="left", fill="y", padx=8, pady=6
        )
        ttk.Button(
            bar, text="↻ Refresh", style="Ghost.TButton", command=self._refresh_data
        ).pack(side="left", padx=1, pady=6)
        self._sync_button = ttk.Button(
            bar, text="Sync Now", style="Accent.TButton", command=self._start_sync
        )
        self._sync_button.pack(side="left", padx=1, pady=6)
        self._status_label = ttk.Label(
            bar, textvariable=self._status_var, style="Status.idle.TLabel"
        )
        self._status_label.pack(side="left", padx=10)

        ttk.Checkbutton(
            bar,
            text=f"Auto-scan every {self._interval_minutes // 60}h",
            variable=self._auto_sync,
            command=self._on_auto_toggle,
            style="Toggle.TCheckbutton",
        ).pack(side="right", padx=2, pady=6)
        ttk.Button(
            bar, text="Test", style="Ghost.TButton", command=self._test_notification
        ).pack(side="right", padx=1, pady=6)
        ttk.Button(
            bar, text="Settings", style="Ghost.TButton", command=self._open_settings
        ).pack(side="right", padx=1, pady=6)
    def _build_table_area(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 0))
        table_wrap = ttk.Frame(paned, style="Surface.TFrame")
        details_wrap = ttk.Frame(paned, style="Surface.TFrame")
        paned.add(table_wrap, weight=3)
        paned.add(details_wrap, weight=1)
        self._details_wrap = details_wrap
        self._build_table(table_wrap)
        self._build_details(details_wrap)

    def _build_table(self, parent) -> None:
        columns = ("id", "subject", "title", "deadline", "remaining", "status")
        self._tree = ttk.Treeview(
            parent, columns=columns, show="headings",
            style="Table.Treeview", selectmode="browse",
        )
        headings = (
            ("id", "ID", 46, "center"),
            ("subject", "SUBJECT", 190, "w"),
            ("title", "ASSIGNMENT", 460, "w"),
            ("deadline", "DEADLINE", 172, "w"),
            ("remaining", "REMAINING", 110, "e"),
            ("status", "STATUS", 96, "center"),
        )
        for col, text, width, anchor in headings:
            self._tree.heading(col, text=text, anchor=anchor)
            self._tree.column(
                col, width=width, minwidth=44,
                anchor=anchor, stretch=(col in ("subject", "title")),
            )
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", lambda _e: self._set_deadline())

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Set deadline…", command=self._set_deadline)
        self._menu.add_command(label="Clear deadline", command=self._clear_deadline)
        self._menu.add_command(label="Mark as completed", command=self._mark_completed)
        self._menu.add_separator()
        self._menu.add_command(label="Open in browser", command=self._open_in_browser)
        self._tree.bind("<Button-3>", self._show_context_menu)

    def _build_details(self, parent) -> None:
        ttk.Label(parent, text="DETAILS", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2)
        )
        self._det_subject = tk.StringVar(value="—")
        self._det_status = tk.StringVar(value="—")
        self._det_deadline = tk.StringVar(value="—")
        self._det_remaining = tk.StringVar(value="—")
        self._det_portal = tk.StringVar(value="—")
        fields = (
            ("Subject", self._det_subject),
            ("Status", self._det_status),
            ("Deadline", self._det_deadline),
            ("Remaining", self._det_remaining),
            ("Portal ID", self._det_portal),
        )
        for i, (label, var) in enumerate(fields, start=1):
            ttk.Label(parent, text=label, style="Muted.TLabel").grid(
                row=i, column=0, sticky="w", padx=10, pady=2
            )
            ttk.Label(parent, textvariable=var, style="Body.TLabel",
                      wraplength=240).grid(
                row=i, column=1, sticky="w", padx=(4, 0), pady=2
            )
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="— DESCRIPTION —", style="Section.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2)
        )
        self._desc_text = tk.Text(
            parent, height=8, wrap="word", relief="flat",
            font=self.fonts["small"], state="disabled",
        )
        self._desc_text.grid(row=7, column=0, columnspan=2, sticky="nsew",
                             padx=10, pady=(2, 6))
        parent.rowconfigure(7, weight=1)

        ttk.Label(parent, text="— ACTIONS —", style="Section.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 2)
        )
        actions = ttk.Frame(parent, style="Surface.TFrame")
        actions.grid(row=9, column=0, columnspan=2, sticky="ew", padx=10, pady=6)
        self._btn_set = ttk.Button(
            actions, text="Set deadline…", style="Accent.TButton",
            command=self._set_deadline,
        )
        self._btn_set.pack(side="left", padx=2)
        self._btn_clear = ttk.Button(
            actions, text="Clear", style="Ghost.TButton",
            command=self._clear_deadline,
        )
        self._btn_clear.pack(side="left", padx=2)
        self._btn_done = ttk.Button(
            actions, text="Completed", style="Ghost.TButton",
            command=self._mark_completed,
        )
        self._btn_done.pack(side="left", padx=2)
        self._btn_open = ttk.Button(
            actions, text="Open URL", style="Ghost.TButton",
            command=self._open_in_browser,
        )
        self._btn_open.pack(side="left", padx=2)
    def _build_notebook(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 2))

        log_tab = ttk.Frame(notebook, style="Surface.TFrame")
        notebook.add(log_tab, text="  Activity Log  ")
        self._log_text = tk.Text(
            log_tab, wrap="none", relief="flat", state="disabled",
            font=self.fonts["mono"], height=8,
        )
        log_vsb = ttk.Scrollbar(log_tab, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_vsb.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        log_vsb.pack(side="right", fill="y")
        self._log_autoscroll = True
        self._log_text.bind("<MouseWheel>", self._on_log_scrollwheel, add="+")

        runs_tab = ttk.Frame(notebook, style="Surface.TFrame")
        notebook.add(runs_tab, text="  Sync Runs  ")
        runs_cols = ("id", "started", "finished", "status", "subjects", "found")
        self._runs_tree = ttk.Treeview(
            runs_tab, columns=runs_cols, show="headings", style="Runs.Treeview",
        )
        runs_headings = (
            ("id", "ID", 50, "center"),
            ("started", "STARTED", 150, "w"),
            ("finished", "FINISHED", 150, "w"),
            ("status", "STATUS", 90, "center"),
            ("subjects", "SUBJECTS", 90, "e"),
            ("found", "FOUND", 90, "e"),
        )
        for col, text, width, anchor in runs_headings:
            self._runs_tree.heading(col, text=text, anchor=anchor)
            self._runs_tree.column(col, width=width, minwidth=40, anchor=anchor)
        runs_vsb = ttk.Scrollbar(runs_tab, orient="vertical",
                                 command=self._runs_tree.yview)
        self._runs_tree.configure(yscrollcommand=runs_vsb.set)
        self._runs_tree.pack(side="left", fill="both", expand=True)
        runs_vsb.pack(side="right", fill="y")

    def _on_log_scrollwheel(self, _event) -> None:
        at_bottom = self._log_text.yview()[1] >= 0.999
        self._log_autoscroll = at_bottom

    def _build_footer(self) -> None:
        self._footer_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self._footer_var, style="Footer.TLabel", anchor="w",
        ).grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))
    # --- theming ------------------------------------------------------------

    def _apply_theme(self, theme: gui_theme.Theme) -> None:
        self._current_theme = theme
        p = theme.palette
        self.configure(bg=p.background)
        st = ttk.Style(self)
        st.theme_use("clam")

        self.option_add("*TCombobox*Listbox.background", p.surface)
        self.option_add("*TCombobox*Listbox.foreground", p.text)

        st.configure("BG.TFrame", background=p.background)
        st.configure("Surface.TFrame", background=p.surface)
        st.configure("Header.TFrame", background=p.header)
        st.configure("Card.TFrame", background=p.card)
        card_colors = (
            ("Primary", "primary"), ("Danger", "danger"), ("Warning", "warning"),
            ("Success", "success"), ("Muted", "text_muted"),
        )
        for color, prop in card_colors:
            st.configure(f"CardAccent.{color}.TFrame", background=getattr(p, prop))
            st.configure(
                f"Value.{color}.TLabel", background=p.card,
                foreground=getattr(p, prop), font=self.fonts["card_value"],
            )
        st.configure(
            "CardLabel.TLabel", background=p.card, foreground=p.text_muted,
            font=self.fonts["card_label"],
        )
        st.configure("Section.TLabel", background=p.surface,
                     foreground=p.text_muted, font=self.fonts["section"])
        st.configure("Body.TLabel", background=p.surface, foreground=p.text,
                     font=self.fonts["body"])
        st.configure("BodyBold.TLabel", background=p.surface, foreground=p.text,
                     font=self.fonts["body"] + ("bold",))
        st.configure("Muted.TLabel", background=p.surface,
                     foreground=p.text_muted, font=self.fonts["small"])
        st.configure("Link.TLabel", background=p.surface, foreground=p.link,
                     font=self.fonts["small"])
        st.configure("Footer.TLabel", background=p.background,
                     foreground=p.text_muted, font=self.fonts["small"])
        st.configure("HeaderBrand.TLabel", background=p.header,
                     foreground=p.text, font=self.fonts["title"])
        st.configure("HeaderMuted.TLabel", background=p.header,
                     foreground=p.text_muted, font=self.fonts["micro"])
        st.configure("HeaderClock.TLabel", background=p.header,
                     foreground=p.text_muted, font=self.fonts["small"])
        for level, color in (
            ("idle", p.text_muted), ("ok", p.success), ("busy", p.warning),
            ("warn", p.warning), ("err", p.danger),
        ):
            st.configure(f"Status.{level}.TLabel", background=p.surface,
                         foreground=color, font=self.fonts["small"])
        st.configure("Accent.TButton", background=p.primary, foreground="#FFFFFF",
                     font=self.fonts["body"], borderwidth=0, padding=(14, 7))
        st.map(
            "Accent.TButton",
            background=[("active", p.primary_dim), ("pressed", p.primary_dim),
                        ("disabled", p.card)],
            foreground=[("disabled", p.text_faint)],
        )
        st.configure("Ghost.TButton", background=p.surface, foreground=p.text,
                     font=self.fonts["body"], borderwidth=0, padding=(10, 6))
        st.map("Ghost.TButton",
               background=[("active", p.card), ("pressed", p.card)],
               foreground=[("disabled", p.text_faint)])
        st.configure("Filter.TButton", background=p.surface,
                     foreground=p.text_muted, font=self.fonts["body"],
                     borderwidth=0, padding=(12, 6))
        st.map("Filter.TButton", background=[("active", p.card)],
               foreground=[("active", p.text)])
        st.configure("FilterSelected.TButton", background=p.primary,
                     foreground="#FFFFFF", font=self.fonts["body"],
                     borderwidth=0, padding=(12, 6))
        st.map("FilterSelected.TButton", background=[("active", p.primary_dim)])
        st.configure("Toggle.TCheckbutton", background=p.background,
                     foreground=p.text_muted, font=self.fonts["small"],
                     focuscolor=p.background, indicatorcolor=p.primary)
        st.map("Toggle.TCheckbutton", background=[("active", p.card)],
               foreground=[("active", p.text)])
        st.configure("TCombobox", fieldbackground=p.surface,
                     background=p.surface, foreground=p.text,
                     arrowcolor=p.text_muted, bordercolor=p.border,
                     lightcolor=p.border, darkcolor=p.border,
                     font=self.fonts["small"])
        st.map("TCombobox", fieldbackground=[("readonly", p.surface)],
               foreground=[("readonly", p.text)])
        st.configure("Table.Treeview", background=p.surface,
                     fieldbackground=p.surface, foreground=p.text,
                     font=self.fonts["table"], rowheight=26, borderwidth=0)
        st.configure("Table.Treeview.Heading", background=p.card,
                     foreground=p.text_muted, font=self.fonts["body"],
                     borderwidth=0, padding=(6, 5), relief="flat")
        st.map("Table.Treeview.Heading", background=[("active", p.border)])
        st.map("Table.Treeview", background=[("selected", p.primary_dim)],
               foreground=[("selected", "#FFFFFF")])
        st.configure("Runs.Treeview", background=p.surface,
                     fieldbackground=p.surface, foreground=p.text,
                     font=self.fonts["micro"], rowheight=20, borderwidth=0)
        st.configure("Runs.Treeview.Heading", background=p.card,
                     foreground=p.text_muted, font=self.fonts["micro"],
                     borderwidth=0, padding=(4, 4), relief="flat")
        st.map("Runs.Treeview", background=[("selected", p.primary_dim)],
               foreground=[("selected", "#FFFFFF")])
        st.configure("TNotebook", background=p.background, borderwidth=0)
        st.configure("TNotebook.Tab", background=p.card,
                     foreground=p.text_muted, font=self.fonts["body"],
                     padding=(14, 7))
        st.map("TNotebook.Tab", background=[("selected", p.surface)],
               foreground=[("selected", p.text)])
        st.configure("TSeparator", background=p.border)
        st.configure("TPanedwindow", background=p.border)
        self._log_text.configure(bg=p.surface, fg=p.text, insertbackground=p.text,
                                 selectbackground=p.primary_dim,
                                 font=self.fonts["mono"])
        for tag, fg in (
            ("meta", p.text_faint), ("info", p.text_muted),
            ("success", p.success), ("warn", p.warning),
            ("error", p.danger), ("bold", p.text),
        ):
            self._log_text.tag_configure(tag, foreground=fg)
        self._desc_text.configure(bg=p.surface, fg=p.text, insertbackground=p.text,
                                  selectbackground=p.primary_dim,
                                  font=self.fonts["small"])
        for key, (fg, bg) in theme.urgency_row.items():
            self._tree.tag_configure(key, foreground=fg, background=bg)
        self._runs_tree.tag_configure("ok", foreground=p.success)
        self._runs_tree.tag_configure("warn", foreground=p.warning)
        self._runs_tree.tag_configure("err", foreground=p.danger)

    def _set_status(self, text: str, level: str = "idle") -> None:
        self._status_var.set(text)
        self._status_label.configure(style=f"Status.{level}.TLabel")
    # --- data refresh ------------------------------------------------------------

    def _refresh_data(self) -> None:
        repo = self._app.repository
        try:
            subjects = repo.get_subjects(active_only=False)
        except Exception:
            subjects = []
        self._subject_names = {s.id: s.name for s in subjects}
        try:
            assignments = repo.get_assignments()
        except Exception:
            assignments = []

        now = datetime.now()
        counts = {"outstanding": 0, "overdue": 0, "due_today": 0,
                  "next_7": 0, "no_deadline": 0}
        self._rows = []
        for a in assignments:
            if a.status.upper() in DONE_STATUSES:
                urgency = "COMPLETED"
            else:
                urgency = compute_urgency(a.deadline, now).value
                counts["outstanding"] += 1
                if urgency == "OVERDUE":
                    counts["overdue"] += 1
                if urgency == "DUE_TODAY":
                    counts["due_today"] += 1
                if urgency in WEEK_SET:
                    counts["next_7"] += 1
                if urgency == "NO_DEADLINE":
                    counts["no_deadline"] += 1
            self._rows.append({
                "id": a.id,
                "subject": self._subject_names.get(a.subject_id, "?"),
                "title": a.title,
                "deadline": a.deadline,
                "urgency": urgency,
                "status": a.status,
                "manual": a.manual_deadline,
                "url": a.source_url,
                "description": a.description,
                "portal_id": a.portal_id,
            })
        self._rows.sort(key=lambda r: (URGENCY_RANK.get(r["urgency"], 9),
                                       r["deadline"] or datetime.max))
        self._row_by_id = {r["id"]: r for r in self._rows}
        for key, var in self._card_vars.items():
            var.set(str(counts.get(key, 0)))

        self._refresh_sync_runs()
        self._apply_filter(keep_selection=True)
        self._last_run_summary, _ok = self._summarise_last_run()
        self._refresh_footer()

    def _summarise_last_run(self) -> tuple[str, bool]:
        run = self._app.repository.get_last_sync_run()
        if run is None:
            return "no scans yet", False
        finished = run.finished_at or run.started_at
        when = finished.strftime("%d %b · %I:%M %p").lstrip("0")
        ok = run.status in ("SUCCESS", "PARTIAL")
        return (f"#{run.id} {run.status} · {run.subjects_checked} subj · "
                f"{run.assignments_found} found · {when}"), ok

    def _refresh_sync_runs(self) -> None:
        try:
            runs = self._app.repository.get_sync_runs(limit=50)
        except Exception:
            runs = []
        self._runs_tree.delete(*self._runs_tree.get_children())
        for run in runs:
            tag = "ok"
            if run.status == "FAILED":
                tag = "err"
            elif run.status in ("PARTIAL", "RUNNING"):
                tag = "warn"
            started = (run.started_at.strftime("%d %b %I:%M %p").lstrip("0")
                       if run.started_at else "—")
            finished = (run.finished_at.strftime("%d %b %I:%M %p").lstrip("0")
                        if run.finished_at else "—")
            self._runs_tree.insert(
                "", "end", iid=str(run.id),
                values=(run.id, started, finished, run.status,
                        run.subjects_checked, run.assignments_found),
                tags=(tag,),
            )
    # --- filters / table -----------------------------------------------------------

    def _set_filter(self, key: str) -> None:
        self._filter.set(key)
        self._apply_filter()

    def _matches(self, row: dict, key: str) -> bool:
        if key == "All":
            return True
        if key == "Overdue":
            return row["urgency"] == "OVERDUE"
        if key == "Due today":
            return row["urgency"] == "DUE_TODAY"
        if key == "Next 7 days":
            return row["urgency"] in WEEK_SET
        if key == "Later":
            return row["urgency"] == "FUTURE"
        if key == "No deadline":
            return row["urgency"] == "NO_DEADLINE"
        if key == "Completed":
            return row["urgency"] == "COMPLETED"
        return True

    def _apply_filter(self, keep_selection: bool = False) -> None:
        key = self._filter.get()
        selected = None
        if keep_selection and self._tree.selection():
            selected = self._tree.selection()[0]
        self._tree.delete(*self._tree.get_children())
        for row in self._rows:
            if not self._matches(row, key):
                continue
            remaining = time_remaining(row["deadline"])
            remaining_text = format_remaining(remaining) if remaining else "—"
            title = f"{'◆ ' if row['manual'] else ''}{row['title']}"
            status_text = URGENCY_LABELS.get(row["urgency"], row["status"])
            self._tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["id"], row["subject"], title,
                        format_deadline(row["deadline"]), remaining_text,
                        status_text),
                tags=(row["urgency"],),
            )
        if selected and self._tree.exists(selected):
            self._tree.selection_set(selected)
            self._tree.focus(selected)
            self._on_tree_select()
        self._update_filter_buttons()

    def _update_filter_buttons(self) -> None:
        active = self._filter.get()
        for key, btn in self._filter_buttons.items():
            btn.configure(
                style="FilterSelected.TButton" if key == active else "Filter.TButton"
            )

    def _selected_row(self) -> dict | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._row_by_id.get(int(sel[0]))

    def _on_tree_select(self, _event=None) -> None:
        self._render_details()

    def _render_details(self) -> None:
        row = self._selected_row()
        if row is None:
            self._det_subject.set("—")
            self._det_status.set("—")
            self._det_deadline.set("—")
            self._det_remaining.set("—")
            self._det_portal.set("—")
            self._desc_text.configure(state="normal")
            self._desc_text.delete("1.0", "end")
            self._desc_text.insert("1.0",
                                   "Select an assignment to see its details.")
            self._desc_text.configure(state="disabled")
            for button in (self._btn_set, self._btn_clear,
                           self._btn_done, self._btn_open):
                button.configure(state="disabled")
            return
        remaining = time_remaining(row["deadline"])
        remaining_text = format_remaining(remaining) if remaining else "—"
        self._det_subject.set(row["subject"])
        self._det_status.set(URGENCY_LABELS.get(row["urgency"], row["status"]))
        self._det_deadline.set(format_deadline(row["deadline"]))
        self._det_remaining.set(remaining_text)
        self._det_portal.set(row["portal_id"] or "—")
        self._desc_text.configure(state="normal")
        self._desc_text.delete("1.0", "end")
        self._desc_text.insert("1.0", row["description"] or "No description.")
        self._desc_text.configure(state="disabled")
        for button in (self._btn_set, self._btn_clear, self._btn_done):
            button.configure(state="normal")
        self._btn_open.configure(
            state="normal" if row["url"] else "disabled"
        )
    # --- sync orchestration -----------------------------------------------------

    def _start_sync(self) -> None:
        if self._sync_running:
            return
        if not self._worker.start():
            self._log("warn", "Another scan is already running; skipped.")
            return
        self._sync_running = True
        self._set_status("● scanning…", "busy")
        self._log("info", "Manual scan started from the dashboard.")

    def _poll_events(self) -> None:
        for event in self._worker.drain():
            self._handle_event(event)
        self._schedule(220, self._poll_events)

    def _handle_event(self, event: SyncEvent) -> None:
        if event.kind == "started":
            self._set_status("● scanning…", "busy")
        elif event.kind == "finished":
            self._sync_running = False
            self._sync_button.configure(state="normal")
            self._set_status("● up to date", "ok")
            self._log("success", event.message)
            self._set_countdown()
            self._refresh_data()
        elif event.kind == "skipped":
            self._sync_running = False
            self._sync_button.configure(state="normal")
            self._set_status("● idle", "idle")
            self._log("warn", event.message)
        elif event.kind == "failed":
            self._sync_running = False
            self._sync_button.configure(state="normal")
            self._set_status("● scan failed", "err")
            self._log("error", event.message)
            self._refresh_data()

    def _set_countdown(self) -> None:
        self._countdown = self._interval_minutes * 60

    def _on_auto_toggle(self) -> None:
        if self._auto_sync.get():
            self._set_countdown()
            self._log("info", f"Auto-scan enabled: every "
                              f"{self._interval_minutes // 60}h")
        else:
            self._log("info", "Auto-scan disabled.")

    def _tick(self) -> None:
        now = datetime.now()
        clock = now.strftime("%A, %d %B %Y  ·  %I:%M:%S %p").lstrip("0")
        self._clock_var.set(clock)
        if self._auto_sync.get():
            self._countdown -= 1
            if self._countdown <= 0:
                self._set_countdown()
                if not self._sync_running and not self._worker.busy:
                    self._start_sync()
        self._refresh_footer()
        self._schedule(1000, self._tick)

    def _refresh_footer(self) -> None:
        minutes = self._interval_minutes
        interval_txt = f"{minutes // 60}h" if minutes >= 60 else f"{minutes}m"
        if self._auto_sync.get():
            next_txt = f"auto-scan in {self._fmt_cd(self._countdown)}"
        else:
            next_txt = f"next scan {self._next_scan_text()}"
        self._footer_var.set(
            f"Periodic scan: every {interval_txt}   ·   {next_txt}   ·   "
            f"last run: {self._last_run_summary}"
        )

    @staticmethod
    def _fmt_cd(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _next_scan_text(self) -> str:
        run = self._app.repository.get_last_sync_run()
        base = (run.finished_at or run.started_at) if run else None
        if base is None:
            return "never"
        target = base + timedelta(minutes=self._interval_minutes)
        seconds = int((target - datetime.now()).total_seconds())
        if seconds <= 0:
            return "now"
        hours, remainder = divmod(seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
    # --- activity log -------------------------------------------------------------

    def _log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"{timestamp}  ", ("meta",))
        self._log_text.insert("end", f"{message}\n", (level,))
        line_count = int(self._log_text.index("end-1c").split(".")[0])
        if line_count > 2000:
            self._log_text.delete("1.0", "501.0")
        if self._log_autoscroll:
            self._log_text.see("end")
        self._log_text.configure(state="disabled")

    # --- table actions -----------------------------------------------------------

    def _show_context_menu(self, event) -> None:
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
            self._tree.focus(item)
            self._on_tree_select()
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _set_deadline(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        dialog = _DeadlineDialog(self, row, self._app.repository,
                                 self._settings.get_timezone(),
                                 on_done=self._deadline_applied)
        self._modal_windows.add(dialog)

    def _deadline_applied(self) -> None:
        self._log("success", "Manual deadline updated.")
        self._refresh_data()

    def _clear_deadline(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        title = row["title"]
        if not messagebox.askyesno(
            "Clear deadline",
            f"Remove the manual deadline for \"{title[:60]}\"?",
            parent=self,
        ):
            return
        self._app.repository.set_manual_deadline(row["id"], None)
        self._log("success", f"Manual deadline cleared for #{row['id']}.")
        self._refresh_data()

    def _mark_completed(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._app.repository.mark_assignment_status(row["id"], "COMPLETED")
        self._log("success", f"#{row['id']} marked as completed.")
        self._refresh_data()

    def _test_notification(self) -> None:
        sent = self._app.notifier.send(
            "Test Notification",
            "CampusWatch dashboard is connected to your desktop notifications.",
        )
        if sent:
            self._log("success", "Test notification sent to the desktop.")
        else:
            self._log("warn", "Test notification failed - see logs/agent.log.")

    def _open_in_browser(self) -> None:
        row = self._selected_row()
        if row is None or not row["url"]:
            return
        webbrowser.open(row["url"])
    # --- settings / misc ---------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("CampusWatch — Configuration")
        dialog.minsize(560, 420)
        dialog.transient(self)
        self._modal_windows.add(dialog)

        body = ttk.Frame(dialog, style="Surface.TFrame")
        body.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(body, text="Configuration", style="HeaderBrand.TLabel").pack(
            anchor="w"
        )
        s = self._settings
        fields = (
            ("Portal URL", s.portal_url),
            ("Username", s.portal_username or "<blank — browser login>"),
            ("Scan interval", f"{s.check_interval_minutes} min "
                              f"({s.check_interval_minutes // 60}h)"),
            ("Reminder windows", s.reminder_windows),
            ("Daily summary", s.daily_summary_time),
            ("Notify overdue", str(s.notify_overdue)),
            ("Notifications", "enabled" if s.notification_enabled else "disabled"),
            ("Headless browser", str(s.browser_headless)),
            ("Timezone", s.timezone),
            ("Database", s.database_url),
            ("Log file", str(s.log_file)),
            ("Screenshots", str(s.screenshots_dir)),
        )
        grid = ttk.Frame(body, style="Surface.TFrame")
        grid.pack(fill="x", pady=(8, 4))
        for i, (label, value) in enumerate(fields):
            ttk.Label(grid, text=label, style="Muted.TLabel").grid(
                row=i, column=0, sticky="w", padx=(0, 8), pady=2
            )
            ttk.Label(grid, text=value or "—", style="Body.TLabel",
                      wraplength=340).grid(
                row=i, column=1, sticky="w", pady=2
            )
        grid.columnconfigure(1, weight=1)

        actions = ttk.Frame(body, style="Surface.TFrame")
        actions.pack(fill="x", pady=(10, 2))
        for text, path in (
            ("Open .env", PROJECT_ROOT_DIR / ".env"),
            ("Open logs folder", s.log_file.parent),
            ("Open screenshots folder", s.screenshots_dir),
            ("Open data folder", PROJECT_ROOT_DIR / "data"),
        ):
            ttk.Button(
                actions, text=text, style="Ghost.TButton",
                command=lambda p=path: self._open_path(p),
            ).pack(side="left", padx=3)
        ttk.Button(
            actions, text="Close", style="Accent.TButton",
            command=dialog.destroy,
        ).pack(side="left", padx=3)

    def _open_path(self, path: "os.PathLike | str") -> None:
        try:
            if os.name == "nt":
                os.startfile(os.fspath(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", os.fspath(path)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", os.fspath(path)])
        except OSError as exc:
            messagebox.showerror("Cannot open path", str(exc), parent=self)

    def _on_theme_change(self, _event=None) -> None:
        name = self._theme_var.get()
        theme = gui_theme.THEMES.get(name)
        if theme is None:
            return
        self._apply_theme(theme)
        gui_theme.save_theme_name(name)

    def _on_close(self) -> None:
        for aid in tuple(self._after_ids):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()
        self.destroy()


class _DeadlineDialog(tk.Toplevel):
    """Modal dialog to set/replace a manual deadline for one assignment."""

    def __init__(self, master: "GuiApp", row: dict, repository, tz, on_done) -> None:
        super().__init__(master)
        self._app_master = master
        self._row = row
        self._repo = repository
        self._tz = tz
        self._on_done = on_done

        self.title("Set deadline")
        self.minsize(460, 210)
        self.transient(master)
        self.grab_set()

        body = ttk.Frame(self, style="Surface.TFrame")
        body.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(
            body,
            text=f"#{row['id']} — {row['title'][:60]}",
            style="BodyBold.TLabel", wraplength=420,
        ).pack(anchor="w")
        ttk.Label(
            body,
            text='Format: "20/09/2026" or "20/09/2026 11:59 PM"',
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 2))
        self._entry_var = tk.StringVar()
        entry = ttk.Entry(body, textvariable=self._entry_var,
                          font=master.fonts["body"])
        entry.pack(fill="x", pady=(2, 6))
        entry.focus_set()
        entry.bind("<Return>", lambda _e: self._apply())

        self._error_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=self._error_var, style="Muted.TLabel").pack(
            anchor="w"
        )

        buttons = ttk.Frame(body, style="Surface.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Set deadline", style="Accent.TButton",
                   command=self._apply).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", style="Ghost.TButton",
                   command=self.destroy).pack(side="right")

    def _apply(self) -> None:
        when = self._entry_var.get().strip()
        if not when:
            self._error_var.set("Enter a deadline first.")
            return
        parsed = parse_deadline(when, self._tz)
        if parsed is None:
            self._error_var.set(f"Could not parse: {when!r}")
            return
        naive = parsed.astimezone(self._tz).replace(tzinfo=None)
        self._repo.set_manual_deadline(self._row["id"], naive)
        self._on_done()
        self.destroy()
