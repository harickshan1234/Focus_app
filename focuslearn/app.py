"""Focus Learn main window: Focus, Progress and Settings pages."""

import atexit
import ctypes
import math
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox

import customtkinter as ctk

from . import store
from . import theme as T
from .blocker import HostsBlocker, WindowGuard, display_name, is_admin, normalize_site, relaunch_as_admin
from .widgets import BarChart, Card, ProgressRing, Stepper, caption

try:
    import winsound
except ImportError:
    winsound = None

SUBJECTS = [
    "Python", "Flask", "FastAPI", "Django", "Linux", "Networking", "Docker", "SQL",
    "JavaScript", "React", "OWASP", "Burp Suite", "Web Security", "Cryptography",
    "Reverse Engineering", "Malware Analysis", "Exploit Development", "Active Directory",
    "AWS", "Azure", "English", "Bug Bounty", "Other",
]

FOCUS, SHORT_BREAK, LONG_BREAK = "focus", "short_break", "long_break"
PHASE_NAMES = {FOCUS: "Focus", SHORT_BREAK: "Short break", LONG_BREAK: "Long break"}

# label: (focus, short break, long break, long break after every N focus blocks)
PRESETS = {
    "25 / 5": (25, 5, 15, 4),
    "50 / 10": (50, 10, 20, 3),
    "90 / 15": (90, 15, 30, 2),
}
CUSTOM = "Custom"

QUICK_SITES = ["instagram.com", "facebook.com", "tiktok.com", "reddit.com", "x.com", "netflix.com", "twitch.tv"]

PAGES = (("focus", "Focus"), ("progress", "Progress"), ("settings", "Settings"))


def fmt_hm(minutes):
    """71.5 -> '1h 12m', 600 -> '10h', 25 -> '25m'."""
    h, m = divmod(int(round(minutes)), 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


def fmt_clock(seconds):
    s = int(math.ceil(max(0, seconds)))
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


def join_names(names):
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


class FocusLearnApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=T.BG)
        store.init_db()
        self.cfg = store.Settings()

        self.title("Focus Learn")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        icon_path = T.app_icon_path()
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except tk.TclError:
                pass

        # --- distraction shield ---
        self.guard = WindowGuard()
        self.hosts = HostsBlocker()
        self.admin = is_admin()
        self.stale_hosts_block = False
        if self.hosts.has_block():          # left over from a crash
            if self.hosts.writable:
                self.hosts.release()
            else:
                self.stale_hosts_block = True
        atexit.register(self.hosts.release)
        self._shield_on = False
        self._last_intercept = 0.0
        self._overlay = None

        # --- timer state ---
        self.phase = None            # None = idle, else FOCUS / SHORT_BREAK / LONG_BREAK
        self.running = False         # False while paused or waiting for the next phase to be started
        self.phase_total = 0         # seconds
        self.phase_elapsed = 0.0     # seconds actually counted
        self.phase_started = None    # wall-clock start, None until the phase is started
        self.blocks_this_run = 0
        self._mono = time.monotonic()

        # --- render caches ---
        self._texts = {}
        self._btn_state = None
        self._bar_frac = -1.0
        self._dots = []
        self._chip_sites = None
        self._site_rows_key = None
        self._window_title = ""
        self._today = date.today()
        self.stats = {}
        self.current_page = None

        self._build()
        self.refresh_stats()
        self.show_page("focus")
        self._render_timer(force=True)
        self._update_shield()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<space>", self._on_space)
        self.bind("<Button-1>", self._clear_focus, add="+")
        for i, (key, _) in enumerate(PAGES, start=1):
            self.bind(f"<Control-Key-{i}>", lambda e, k=key: self.show_page(k))
        self.after(200, self._tick)
        self.after(1000, self._shield_tick)
        self.after(30_000, self._refresh_loop)
        self.after(400, self._tint_title_bar)

    # ================================================================ layout

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=32, pady=(26, 28))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.pages = {
            "focus": self._build_focus_page(),
            "progress": self._build_progress_page(),
            "settings": self._build_settings_page(),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page_header(self, parent, title, subtitle):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid_columnconfigure(0, weight=1)
        title_label = ctk.CTkLabel(head, text=title, font=T.font(26, "semibold"), text_color=T.TEXT, anchor="w")
        title_label.grid(row=0, column=0, sticky="w")
        sub_label = ctk.CTkLabel(head, text=subtitle, font=T.font(13), text_color=T.MUTED, anchor="w")
        sub_label.grid(row=1, column=0, sticky="w")
        return head, title_label, sub_label

    # ---- sidebar ----

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=236)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(len(PAGES) + 1, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=22, pady=(28, 30))
        ctk.CTkLabel(brand, text="", image=T.logo(34)).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(brand, text="Focus Learn", font=T.font(17, "semibold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=1, sticky="sw")
        self.tagline = ctk.CTkLabel(brand, text="", font=T.font(12), text_color=T.MUTED, anchor="w", height=18)
        self.tagline.grid(row=1, column=1, sticky="nw")

        self.nav = {}
        for row, (key, label) in enumerate(PAGES, start=1):
            button = ctk.CTkButton(bar, text=f"  {label}", anchor="w", height=42, corner_radius=10, font=T.font(14),
                                   fg_color="transparent", hover_color=T.CARD, text_color=T.MUTED,
                                   image=T.icon(key, 18, T.MUTED), command=lambda k=key: self.show_page(k))
            button.grid(row=row, column=0, sticky="ew", padx=14, pady=2)
            self.nav[key] = button

        foot = Card(bar, corner_radius=14)
        foot.grid(row=len(PAGES) + 2, column=0, sticky="ew", padx=14, pady=16)
        foot.grid_columnconfigure(0, weight=1)
        self.side_shield = ctk.CTkLabel(foot, text="", font=T.font(12, "semibold"), anchor="w", compound="left")
        self.side_shield.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.side_today = ctk.CTkLabel(foot, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.side_today.grid(row=1, column=0, sticky="w", padx=14)
        self.side_bar = ctk.CTkProgressBar(foot, height=6, corner_radius=3, fg_color=T.TRACK, progress_color=T.ACCENT)
        self.side_bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 14))

    # ---- focus page ----

    def _build_focus_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2, minsize=340)
        page.grid_rowconfigure(1, weight=1)

        head, self.greeting, self.date_label = self._page_header(page, "", "")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 22))
        ctk.CTkLabel(head, text="Space  start / pause", font=T.font(12), text_color=T.FAINT).grid(
            row=0, column=1, rowspan=2, sticky="e")

        card = Card(page)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, 20))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        self.preset = ctk.CTkSegmentedButton(card, values=list(PRESETS) + [CUSTOM], command=self._on_preset,
                                             font=T.font(13), **T.SEGMENTED)
        self.preset.grid(row=0, column=0, pady=(24, 0))

        self.ring = ProgressRing(card, size=290, thickness=11)
        self.ring.grid(row=1, column=0, pady=10)

        fields = ctk.CTkFrame(card, fg_color="transparent")
        fields.grid(row=2, column=0, sticky="ew", padx=32)
        fields.grid_columnconfigure(1, weight=1)
        self.subject = ctk.CTkComboBox(fields, values=SUBJECTS, width=176, font=T.font(13), dropdown_font=T.font(13),
                                       command=lambda v: self.cfg.set("subject", v), **T.COMBO)
        self.subject.set(self.cfg["subject"])
        self.subject.grid(row=0, column=0, padx=(0, 10))
        self.task = ctk.CTkEntry(fields, placeholder_text="What are you studying?", font=T.font(13), **T.ENTRY)
        if self.cfg["task"]:
            self.task.insert(0, self.cfg["task"])
        self.task.grid(row=0, column=1, sticky="ew")

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.grid(row=3, column=0, pady=(20, 28))
        # corner radius 16: CustomTkinter pads icon buttons by their radius, so a full circle would grow wider
        round_btn = dict(text="", width=50, height=50, corner_radius=16, **T.GHOST)
        self.skip_btn = ctk.CTkButton(controls, image=T.icon("skip", 18), command=self.skip_break, **round_btn)
        self.skip_btn.grid(row=0, column=0, padx=6)
        self.skip_btn.grid_remove()
        # Empty slot that balances the Stop button during focus, so the main button stays centred.
        self.skip_spacer = ctk.CTkFrame(controls, width=50, height=50, fg_color="transparent")
        self.skip_spacer.grid(row=0, column=0, padx=6)
        self.primary_btn = ctk.CTkButton(controls, text="Start focus", width=210, height=50, corner_radius=16,
                                         font=T.font(15, "semibold"), text_color=T.ON_ACCENT, compound="left",
                                         command=self.toggle)
        self.primary_btn.grid(row=0, column=1, padx=6)
        self.stop_btn = ctk.CTkButton(controls, image=T.icon("stop", 17), command=self.stop, **round_btn)
        self.stop_btn.grid(row=0, column=2, padx=6)

        side = ctk.CTkFrame(page, fg_color="transparent")
        side.grid(row=1, column=1, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)
        self._build_today_card(side).grid(row=0, column=0, sticky="ew")
        self._build_shield_card(side).grid(row=1, column=0, sticky="ew", pady=(20, 0))
        return page

    def _build_today_card(self, parent):
        card = Card(parent)
        card.grid_columnconfigure((0, 1), weight=1, uniform="today")
        caption(card, "Today").grid(row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(20, 0))

        amount = ctk.CTkFrame(card, fg_color="transparent")
        amount.grid(row=1, column=0, columnspan=2, sticky="w", padx=22)
        self.today_value = ctk.CTkLabel(amount, text="0m", font=T.font(36, "semibold"), text_color=T.TEXT)
        self.today_value.grid(row=0, column=0, sticky="sw")
        self.today_goal = ctk.CTkLabel(amount, text="", font=T.font(16), text_color=T.MUTED)
        self.today_goal.grid(row=0, column=1, sticky="sw", padx=(8, 0), pady=(0, 8))

        self.today_bar = ctk.CTkProgressBar(card, height=8, corner_radius=4, fg_color=T.TRACK, progress_color=T.ACCENT)
        self.today_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(6, 16))

        self.dots_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.dots_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=22)
        self.plan_label = ctk.CTkLabel(card, text="", font=T.font(12), text_color=T.FAINT, anchor="w")
        self.plan_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=22, pady=(4, 12))

        self.today_stats = {}
        cells = (("left", "To go"), ("finish", "Finish around"), ("blocks", "Full blocks"), ("streak", "Goal streak"))
        for i, (key, label) in enumerate(cells):
            cell = ctk.CTkFrame(card, fg_color=T.INPUT, corner_radius=12)
            col = i % 2
            cell.grid(row=5 + i // 2, column=col, sticky="ew",
                      padx=(22, 6) if col == 0 else (6, 22), pady=(0, 12) if i < 2 else (0, 22))
            ctk.CTkLabel(cell, text=label, font=T.font(11), text_color=T.MUTED, anchor="w", height=18).grid(
                row=0, column=0, sticky="w", padx=14, pady=(10, 0))
            value = ctk.CTkLabel(cell, text="–", font=T.font(16, "semibold"), text_color=T.TEXT, anchor="w", height=24)
            value.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
            self.today_stats[key] = value
        return card

    def _build_shield_card(self, parent):
        card = Card(parent)
        card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 0))
        top.grid_columnconfigure(1, weight=1)
        self.shield_icon = ctk.CTkLabel(top, text="", image=T.icon("shield", 20, T.MUTED))
        self.shield_icon.grid(row=0, column=0)
        ctk.CTkLabel(top, text="Distraction shield", font=T.font(15, "semibold"), text_color=T.TEXT).grid(
            row=0, column=1, sticky="w", padx=(10, 0))
        self.shield_pill = ctk.CTkLabel(top, text="", font=T.font(11, "semibold"), corner_radius=8, height=24, width=70)
        self.shield_pill.grid(row=0, column=2, sticky="e")

        self.shield_text = ctk.CTkLabel(card, text="", font=T.font(13), text_color=T.MUTED, anchor="w",
                                        justify="left", wraplength=330)
        self.shield_text.grid(row=1, column=0, sticky="ew", padx=22, pady=(10, 10))
        self.chips = ctk.CTkFrame(card, fg_color="transparent")
        self.chips.grid(row=2, column=0, sticky="w", padx=22)
        self.shield_meta = ctk.CTkLabel(card, text="", font=T.font(12), text_color=T.FAINT, anchor="w",
                                        justify="left", wraplength=330)
        self.shield_meta.grid(row=3, column=0, sticky="ew", padx=22, pady=(10, 20))
        return card

    # ---- progress page ----

    def _build_progress_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        head, _, _ = self._page_header(page, "Progress", "How your study hours are adding up")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 22))
        self.range = ctk.CTkSegmentedButton(head, values=["7 days", "30 days"], font=T.font(13),
                                            command=lambda v: self.refresh_progress(), **T.SEGMENTED)
        self.range.set("7 days")
        self.range.grid(row=0, column=1, rowspan=2, sticky="e")

        tiles = ctk.CTkFrame(page, fg_color="transparent")
        tiles.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        self.kpi = {}
        kpis = (("today", "Today"), ("week", "Last 7 days"), ("avg", "Daily average"), ("streak", "Goal streak"))
        for i, (key, label) in enumerate(kpis):
            tiles.grid_columnconfigure(i, weight=1, uniform="kpi")
            tile = Card(tiles)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 9, 0 if i == len(kpis) - 1 else 9))
            caption(tile, label).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 0))
            value = ctk.CTkLabel(tile, text="–", font=T.font(26, "semibold"), text_color=T.TEXT, anchor="w")
            value.grid(row=1, column=0, sticky="w", padx=20)
            sub = ctk.CTkLabel(tile, text="", font=T.font(12), text_color=T.FAINT, anchor="w")
            sub.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 16))
            self.kpi[key] = (value, sub)

        chart_card = Card(page)
        chart_card.grid(row=2, column=0, sticky="nsew", pady=(0, 18))
        chart_card.grid_columnconfigure(0, weight=1)
        chart_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(chart_card, text="Daily study hours", font=T.font(15, "semibold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))
        self.chart = BarChart(chart_card, height=180)
        self.chart.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))

        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.grid_columnconfigure((0, 1), weight=1, uniform="bottom")
        subj_card = Card(bottom)
        subj_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        subj_card.grid_columnconfigure(0, weight=1)
        self.subjects_title = ctk.CTkLabel(subj_card, text="By subject", font=T.font(15, "semibold"),
                                           text_color=T.TEXT, anchor="w")
        self.subjects_title.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 8))
        self.subjects_box = ctk.CTkFrame(subj_card, fg_color="transparent", height=150)
        self.subjects_box.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 18))
        self.subjects_box.grid_columnconfigure(1, weight=1)

        recent_card = Card(bottom)
        recent_card.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        recent_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(recent_card, text="Recent sessions", font=T.font(15, "semibold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=22, pady=(18, 8))
        self.recent_box = ctk.CTkFrame(recent_card, fg_color="transparent", height=150)
        self.recent_box.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 18))
        self.recent_box.grid_columnconfigure(1, weight=1)
        return page

    # ---- settings page ----

    def _build_settings_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent", scrollbar_button_color=T.BORDER,
                                      scrollbar_button_hover_color=T.TRACK)
        page.grid_columnconfigure(0, weight=1)
        head, _, _ = self._page_header(page, "Settings", "Changes are saved automatically")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 22))

        # Daily goal
        body = self._section(page, 1, "Daily goal", "How many hours of focused study you are aiming for each day.")
        goal_row = ctk.CTkFrame(body, fg_color="transparent")
        goal_row.grid(row=0, column=0, sticky="ew")
        goal_row.grid_columnconfigure(0, weight=1)
        self.goal_slider = ctk.CTkSlider(goal_row, from_=1, to=16, number_of_steps=30, command=self._on_goal,
                                         progress_color=T.ACCENT, fg_color=T.TRACK, button_color=T.TEXT,
                                         button_hover_color="#FFFFFF", height=18)
        self.goal_slider.set(self.cfg["goal_hours"])
        self.goal_slider.grid(row=0, column=0, sticky="ew", padx=(0, 18))
        self.goal_value = ctk.CTkLabel(goal_row, text="", font=T.font(20, "semibold"), text_color=T.TEXT, width=70)
        self.goal_value.grid(row=0, column=1)
        self.goal_hint = ctk.CTkLabel(body, text="", font=T.font(12), text_color=T.FAINT, anchor="w")
        self.goal_hint.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Timer
        body = self._section(page, 2, "Timer", "Pick a preset on the Focus page, or fine-tune every length here.")
        self.steppers = {
            "focus_min": Stepper(body, self.cfg["focus_min"], 5, 180, 5, "min", lambda v: self._on_timer("focus_min", v)),
            "short_break_min": Stepper(body, self.cfg["short_break_min"], 1, 60, 1, "min",
                                       lambda v: self._on_timer("short_break_min", v)),
            "long_break_min": Stepper(body, self.cfg["long_break_min"], 5, 90, 5, "min",
                                      lambda v: self._on_timer("long_break_min", v)),
            "long_break_every": Stepper(body, self.cfg["long_break_every"], 1, 10, 1, "blocks",
                                        lambda v: self._on_timer("long_break_every", v)),
        }
        rows = (("focus_min", "Focus block", "Length of one study block"),
                ("short_break_min", "Short break", "Rest between focus blocks"),
                ("long_break_min", "Long break", "A longer rest every few blocks"),
                ("long_break_every", "Long break after", "Number of focus blocks before a long break"))
        r = 0
        for key, title, hint in rows:
            self._setting_row(body, r, title, hint, self.steppers[key])
            r += 1
        for key, title, hint in (("auto_start_breaks", "Start breaks automatically", "Rolls straight into the break when a block ends"),
                                 ("auto_start_focus", "Start focus automatically", "Starts the next block as soon as a break ends"),
                                 ("confirm_stop", "Ask before ending a block early", "A small speed bump against quitting")):
            self._setting_row(body, r, title, hint, self._switch(body, key))
            r += 1

        # Shield
        body = self._section(page, 3, "Distraction shield",
                             "Sites that get blocked while you study. YouTube is on the list by default.")
        self.sites_box = ctk.CTkFrame(body, fg_color="transparent")
        self.sites_box.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.sites_box.grid_columnconfigure(0, weight=1)

        add_row = ctk.CTkFrame(body, fg_color="transparent")
        add_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        add_row.grid_columnconfigure(0, weight=1)
        self.site_entry = ctk.CTkEntry(add_row, placeholder_text="Add a site, e.g. instagram.com", font=T.font(13),
                                       **T.ENTRY)
        self.site_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.site_entry.bind("<Return>", lambda e: self._add_site(self.site_entry.get()))
        ctk.CTkButton(add_row, text="Add", width=86, height=40, corner_radius=10, font=T.font(13, "semibold"),
                      fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color=T.ON_ACCENT,
                      command=lambda: self._add_site(self.site_entry.get())).grid(row=0, column=1)
        self.site_error = ctk.CTkLabel(body, text="", font=T.font(12), text_color=T.DANGER, anchor="w", height=18)
        self.site_error.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.quick_box = ctk.CTkFrame(body, fg_color="transparent")
        self.quick_box.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 14))

        r = 4
        for key, title, hint in (("block_during_breaks", "Keep blocking during breaks", "Breaks are for resting, not for one quick video"),
                                 ("goal_lock", "Goal lock", "Keep the shield on all day until today's goal is reached"),
                                 ("close_tab", "Close the blocked tab", "Off = minimise the browser window instead")):
            self._setting_row(body, r, title, hint, self._switch(body, key))
            r += 1

        # System-wide blocking
        body = self._section(page, 4, "System-wide blocking",
                             "Blocks the sites in every browser and app through the Windows hosts file. "
                             "Needs administrator rights.")
        status = ctk.CTkFrame(body, fg_color="transparent")
        status.grid(row=0, column=0, columnspan=2, sticky="ew")
        status.grid_columnconfigure(0, weight=1)
        if self.hosts.writable:
            text, color = "Active - the app is running as administrator.", T.BREAK
        else:
            text, color = "Off - only the browser guard is running (it closes blocked tabs).", T.MUTED
        ctk.CTkLabel(status, text=text, font=T.font(13), text_color=color, anchor="w").grid(row=0, column=0, sticky="w")
        if not self.hosts.writable:
            ctk.CTkButton(status, text="Restart as administrator", height=38, corner_radius=10, font=T.font(13),
                          command=self._restart_admin, **T.GHOST).grid(row=0, column=1, sticky="e")

        self._render_site_settings()
        self._sync_settings_widgets()
        return page

    def _section(self, parent, row, title, subtitle):
        card = Card(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 18), padx=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=T.font(16, "semibold"), text_color=T.TEXT, anchor="w").grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 0))
        ctk.CTkLabel(card, text=subtitle, font=T.font(12), text_color=T.MUTED, anchor="w", justify="left",
                     wraplength=640).grid(row=1, column=0, sticky="w", padx=24, pady=(2, 16))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 22))
        body.grid_columnconfigure(0, weight=1)
        return body

    def _setting_row(self, body, row, title, hint, control):
        text = ctk.CTkFrame(body, fg_color="transparent")
        text.grid(row=row, column=0, sticky="w", pady=7)
        ctk.CTkLabel(text, text=title, font=T.font(13), text_color=T.TEXT, anchor="w", height=20).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(text, text=hint, font=T.font(12), text_color=T.FAINT, anchor="w", height=18).grid(
            row=1, column=0, sticky="w")
        control.grid(row=row, column=1, sticky="e", pady=7)

    def _switch(self, parent, key):
        switch = ctk.CTkSwitch(parent, command=lambda: self._on_switch(key, switch), **T.SWITCH)
        if self.cfg[key]:
            switch.select()
        return switch

    # ================================================================ pages

    def show_page(self, name):
        self.current_page = name
        for key, page in self.pages.items():
            if key == name:
                page.grid()
            else:
                page.grid_remove()
        for key, button in self.nav.items():
            selected = key == name
            button.configure(fg_color=T.CARD if selected else "transparent",
                             text_color=T.TEXT if selected else T.MUTED,
                             image=T.icon(key, 18, T.ACCENT if selected else T.MUTED))
        if name == "progress":
            self.refresh_progress()

    def _on_space(self, event):
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self.toggle()
        return "break"

    def _clear_focus(self, event):
        """Clicking outside a text field takes the cursor out of it, so Space works again."""
        widget = event.widget
        if isinstance(widget, str) or isinstance(widget, (tk.Entry, tk.Text)):
            return
        try:
            widget.focus_set()
        except tk.TclError:
            pass

    # ================================================================ timer

    def _phase_minutes(self, phase):
        return self.cfg[{FOCUS: "focus_min", SHORT_BREAK: "short_break_min", LONG_BREAK: "long_break_min"}[phase]]

    def toggle(self):
        """Start / pause / resume - the big button and the Space key."""
        if self.phase is None:
            self.blocks_this_run = 0
            self._enter_phase(FOCUS, start=True)
        elif self.running:
            self.running = False
        else:
            self.running = True
            if self.phase_started is None:
                self.phase_started = datetime.now()
        self._after_state_change()

    def stop(self):
        if self.phase is None:
            return
        if (self.phase == FOCUS and self.cfg["confirm_stop"] and self.phase_started is not None
                and self.phase_elapsed >= 60):
            done = fmt_hm(self.phase_elapsed / 60)
            left = fmt_hm((self.phase_total - self.phase_elapsed) / 60)
            if not messagebox.askyesno("End this focus block?",
                                       f"You've focused for {done} - only {left} left in this block.\n\n"
                                       "End the session now? The time you've done is saved.", parent=self):
                return
        self._log_phase(completed=False)
        self.phase, self.running, self.phase_started, self.phase_elapsed = None, False, None, 0.0
        self.refresh_stats()
        self._after_state_change()

    def skip_break(self):
        if self.phase not in (SHORT_BREAK, LONG_BREAK):
            return
        self._log_phase(completed=False)
        self._enter_phase(FOCUS, start=True)
        self.refresh_stats()
        self._after_state_change()

    def _enter_phase(self, phase, start):
        self.phase = phase
        self.phase_total = self._phase_minutes(phase) * 60
        self.phase_elapsed = 0.0
        self.running = start
        self.phase_started = datetime.now() if start else None

    def _log_phase(self, completed):
        """Save the current phase. Anything shorter than a minute is dropped."""
        if self.phase is None or self.phase_started is None:
            return
        minutes = self.phase_elapsed / 60.0
        if minutes < 1 and not completed:
            return
        store.log_session(self.phase, self.subject.get().strip() or None, self.task.get().strip() or None,
                          self.phase_started, datetime.now(), minutes, completed, self.phase != FOCUS)

    def _complete_phase(self):
        finished = self.phase
        self._log_phase(completed=True)
        if finished == FOCUS:
            self.blocks_this_run += 1
            long_due = self.blocks_this_run % max(1, self.cfg["long_break_every"]) == 0
            self._enter_phase(LONG_BREAK if long_due else SHORT_BREAK, start=self.cfg["auto_start_breaks"])
        else:
            self._enter_phase(FOCUS, start=self.cfg["auto_start_focus"])
        self._notify()
        self.refresh_stats()
        self._after_state_change()

    def _after_state_change(self):
        self._render_timer(force=True)
        self._update_shield()

    def _tick(self):
        try:
            now = time.monotonic()
            delta, self._mono = now - self._mono, now
            if self.running:
                if delta > 5:        # the PC was asleep or the app froze - don't count that time
                    delta = 0
                self.phase_elapsed += delta
                if self.phase_elapsed >= self.phase_total:
                    self.phase_elapsed = self.phase_total
                    self._complete_phase()
            if date.today() != self._today:
                self._today = date.today()
                self.refresh_stats()
            self._render_timer()
        finally:
            self.after(200, self._tick)

    def _notify(self):
        if winsound:
            try:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except RuntimeError:
                pass
        try:
            if self.state() == "iconic":
                self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(600, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass

    # ================================================================ rendering

    def _set(self, label, text):
        if self._texts.get(id(label)) != text:
            self._texts[id(label)] = text
            label.configure(text=text)

    def _render_timer(self, force=False):
        if self.phase is None:
            remaining, progress, color = self.cfg["focus_min"] * 60, 0.0, T.ACCENT
            status, label, hover = "READY TO FOCUS", "Start focus", T.ACCENT_HOVER
        else:
            is_focus = self.phase == FOCUS
            remaining = self.phase_total - self.phase_elapsed
            progress = self.phase_elapsed / self.phase_total if self.phase_total else 0.0
            color, hover = (T.ACCENT, T.ACCENT_HOVER) if is_focus else (T.BREAK, T.BREAK_HOVER)
            name = "FOCUS" if is_focus else PHASE_NAMES[self.phase].upper()
            if self.running:
                status = f"FOCUS  ·  BLOCK {self.stats.get('blocks_today', 0) + 1}" if is_focus else name
                label = "Pause"
            elif self.phase_started is None:
                status = f"UP NEXT  ·  {name}"
                label = "Start focus" if is_focus else "Start break"
            else:
                status, label = "PAUSED", "Resume"

        clock = fmt_clock(remaining)
        self.ring.draw(progress, color, clock, status)

        btn_state = (label, color, self.phase, self.running)
        if force or btn_state != self._btn_state:
            self._btn_state = btn_state
            self.primary_btn.configure(text=f" {label}", fg_color=color, hover_color=hover,
                                       image=T.icon("pause" if self.running else "play", 16, T.ON_ACCENT))
            if self.phase is None:
                self.stop_btn.grid_remove()
            else:
                self.stop_btn.grid()
            if self.phase in (SHORT_BREAK, LONG_BREAK):
                self.skip_spacer.grid_remove()
                self.skip_btn.grid()
            else:
                self.skip_btn.grid_remove()
                if self.phase is None:
                    self.skip_spacer.grid_remove()
                else:
                    self.skip_spacer.grid()

        window_title = f"{clock} · {PHASE_NAMES[self.phase]} - Focus Learn" if self.phase else "Focus Learn"
        if window_title != self._window_title:
            self._window_title = window_title
            self.title(window_title)
        self._render_today()

    def _today_minutes(self):
        live = self.phase_elapsed / 60 if self.phase == FOCUS and self.phase_started is not None else 0.0
        return self.stats.get("today_min", 0) + live

    def _plan_minutes(self, blocks):
        focus, short, long_ = self.cfg["focus_min"], self.cfg["short_break_min"], self.cfg["long_break_min"]
        every = max(1, self.cfg["long_break_every"])
        breaks = sum(long_ if i % every == 0 else short for i in range(1, blocks))
        return blocks * focus + breaks

    def _finish_estimate(self, left_min):
        if left_min <= 0:
            return "Goal met"
        focus, every = self.cfg["focus_min"], max(1, self.cfg["long_break_every"])
        avg_break = (self.cfg["short_break_min"] * (every - 1) + self.cfg["long_break_min"]) / every
        extra = max(0, math.ceil(left_min / focus) - 1) * avg_break
        if self.phase in (SHORT_BREAK, LONG_BREAK):
            extra += (self.phase_total - self.phase_elapsed) / 60
        eta = datetime.now() + timedelta(minutes=left_min + extra)
        return eta.strftime("%H:%M") + (" +1d" if eta.date() > date.today() else "")

    def _render_today(self):
        goal_min = self.cfg["goal_hours"] * 60
        done = self._today_minutes()
        left = max(0.0, goal_min - done)

        self._set(self.today_value, fmt_hm(done))
        self._set(self.today_goal, f"/ {fmt_hm(goal_min)}")
        frac = min(1.0, done / goal_min) if goal_min else 0.0
        if abs(frac - self._bar_frac) > 0.0005:
            self._bar_frac = frac
            fill = T.ACCENT if frac > 0 else T.TRACK   # an empty CTkProgressBar still draws a dot
            for bar in (self.today_bar, self.side_bar):
                bar.configure(progress_color=fill)
                bar.set(frac)

        focus = self.cfg["focus_min"]
        needed = min(36, max(1, math.ceil(goal_min / focus)))
        in_block = self.phase == FOCUS and self.phase_started is not None
        self._render_dots(needed, int(done // focus), in_block)
        self._set(self.plan_label, f"{needed} blocks of {focus} min  ·  about {fmt_hm(self._plan_minutes(needed))} "
                                   "with breaks")

        self._set(self.today_stats["left"], "Done!" if left <= 0 else fmt_hm(left))
        self._set(self.today_stats["finish"], self._finish_estimate(left))
        self._set(self.today_stats["blocks"], str(self.stats.get("blocks_today", 0)))
        streak = self.stats.get("streak_before_today", 0) + (1 if done >= goal_min else 0)
        self._set(self.today_stats["streak"], f"{streak} day" + ("" if streak == 1 else "s"))
        self._set(self.side_today, f"Today  {fmt_hm(done)} of {fmt_hm(goal_min)}")
        self._set(self.tagline, f"{self.cfg['goal_hours']:g} hours a day")

    def _render_dots(self, needed, full, in_block):
        if len(self._dots) != needed:
            for dot in self._dots:
                dot.destroy()
            self._dots = []
            for i in range(needed):
                dot = ctk.CTkFrame(self.dots_frame, width=14, height=14, corner_radius=7, fg_color=T.TRACK)
                dot.grid(row=i // 12, column=i % 12, padx=(0, 8), pady=3)
                dot.color = T.TRACK
                self._dots.append(dot)
        for i, dot in enumerate(self._dots):
            if i < full:
                color = T.ACCENT
            elif i == full and in_block:
                color = "#4B57A8"
            else:
                color = T.TRACK
            if dot.color != color:
                dot.color = color
                dot.configure(fg_color=color)

    def _greet(self):
        now = datetime.now()
        part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
        self._set(self.greeting, f"Good {part}")
        self._set(self.date_label, now.strftime("%A, %d %B").replace(" 0", " "))

    def refresh_stats(self):
        today = date.today()
        self.stats = {
            "today_min": store.focus_minutes_on(today),
            "blocks_today": store.focus_blocks_on(today),
            "streak_before_today": store.goal_streak(self.cfg["goal_hours"] * 60, before=today),
            "blocked_today": store.blocks_on(today),
        }
        self._greet()
        self._render_today()
        self._render_shield_info()
        if self.current_page == "progress":
            self.refresh_progress()

    def _refresh_loop(self):
        try:
            self.refresh_stats()
        finally:
            self.after(30_000, self._refresh_loop)

    # ---- progress page ----

    def refresh_progress(self):
        today = date.today()
        goal_h = self.cfg["goal_hours"]
        days = 7 if self.range.get() == "7 days" else 30
        live = self._today_minutes() - self.stats.get("today_min", 0)

        series = store.daily_minutes(max(days, 7))
        series[-1] = (series[-1][0], series[-1][1] + live)
        shown = series[-days:]
        items = []
        for d, minutes in shown:
            if d == today:
                label = "Today"
            else:
                label = d.strftime("%a") if days == 7 else str(d.day)
            items.append((label, minutes / 60, d == today))
        self.chart.set_data(items, goal_h)

        today_min = series[-1][1]
        week_min = sum(m for _, m in series[-7:])
        avg_min = sum(m for _, m in shown) / days
        streak = self.stats.get("streak_before_today", 0) + (1 if today_min >= goal_h * 60 else 0)
        best = max(store.best_day_minutes(), today_min)
        values = {
            "today": (fmt_hm(today_min), f"{min(100, round(today_min / (goal_h * 60) * 100))}% of your goal"),
            "week": (fmt_hm(week_min), f"of {fmt_hm(goal_h * 7 * 60)} target"),
            "avg": (fmt_hm(avg_min), f"over the last {days} days"),
            "streak": (f"{streak} day" + ("" if streak == 1 else "s"), f"best day {fmt_hm(best)}"),
        }
        for key, (value, sub) in values.items():
            self.kpi[key][0].configure(text=value)
            self.kpi[key][1].configure(text=sub)

        # By subject
        for child in self.subjects_box.winfo_children():
            child.destroy()
        self.subjects_title.configure(text=f"By subject  ·  {days} days")
        rows = store.subject_minutes(today - timedelta(days=days - 1), today)[:5]
        if not rows:
            ctk.CTkLabel(self.subjects_box, text="No study time logged yet.", font=T.font(13),
                         text_color=T.FAINT).grid(row=0, column=0, sticky="w")
        top = rows[0][1] if rows else 1
        for i, (subject, minutes) in enumerate(rows):
            ctk.CTkLabel(self.subjects_box, text=subject, font=T.font(13), text_color=T.TEXT, anchor="w",
                         width=120).grid(row=i, column=0, sticky="w", pady=4)
            bar = ctk.CTkProgressBar(self.subjects_box, height=8, corner_radius=4, fg_color=T.TRACK,
                                     progress_color=T.ACCENT)
            bar.set(minutes / top if top else 0)
            bar.grid(row=i, column=1, sticky="ew", padx=12)
            ctk.CTkLabel(self.subjects_box, text=fmt_hm(minutes), font=T.font(12, "semibold"), text_color=T.MUTED,
                         width=60, anchor="e").grid(row=i, column=2, sticky="e")

        # Recent sessions
        for child in self.recent_box.winfo_children():
            child.destroy()
        sessions = store.recent_sessions(5)
        if not sessions:
            ctk.CTkLabel(self.recent_box, text="Your finished focus blocks will show up here.", font=T.font(13),
                         text_color=T.FAINT).grid(row=0, column=0, columnspan=3, sticky="w")
        for i, (start, subject, task, minutes, completed) in enumerate(sessions):
            if start.date() == today:
                when = start.strftime("Today %H:%M")
            elif start.date() == today - timedelta(days=1):
                when = start.strftime("Yesterday %H:%M")
            else:
                when = start.strftime("%a %d %b").replace(" 0", " ")
            ctk.CTkLabel(self.recent_box, text=when, font=T.font(12), text_color=T.FAINT, anchor="w",
                         width=110).grid(row=i, column=0, sticky="w", pady=4)
            what = subject or "Study"
            if task:
                what += f"  ·  {task[:26]}{'…' if len(task) > 26 else ''}"
            ctk.CTkLabel(self.recent_box, text=what, font=T.font(13), text_color=T.TEXT, anchor="w").grid(
                row=i, column=1, sticky="w", padx=(4, 8))
            ctk.CTkLabel(self.recent_box, text=fmt_hm(minutes), font=T.font(12, "semibold"),
                         text_color=T.BREAK if completed else T.MUTED, anchor="e", width=56).grid(
                row=i, column=2, sticky="e")

    # ================================================================ shield

    def _shield_should_run(self):
        if not self.cfg["block_sites"]:
            return False
        if self.phase is not None and (self.phase == FOCUS or self.cfg["block_during_breaks"]):
            return True
        return bool(self.cfg["goal_lock"]) and self._today_minutes() < self.cfg["goal_hours"] * 60

    def _shield_tick(self):
        try:
            self._update_shield()
        finally:
            self.after(1000, self._shield_tick)

    def _update_shield(self):
        on = self._shield_should_run()
        sites = self.cfg["block_sites"]
        if self.hosts.writable:
            if on:
                self.hosts.block(sites)        # no-op while the list is unchanged
            elif self.hosts.active:
                self.hosts.release()
        self._shield_on = on
        if on:
            hit = self.guard.check(sites)
            if hit:
                self._intercept(hit)
        self._render_shield_info()

    def _intercept(self, hit):
        now = time.monotonic()
        if now - self._last_intercept < 1.5:   # give the browser a moment to close the tab
            return
        self._last_intercept = now
        if self.cfg["close_tab"]:
            self.guard.close_tab(hit.hwnd)
        else:
            self.guard.minimize(hit.hwnd)
        store.log_block(hit.site)
        self.stats["blocked_today"] = self.stats.get("blocked_today", 0) + 1
        self.after(150, lambda: self._show_overlay(hit.site))

    def _overlay_message(self, name):
        goal_min = self.cfg["goal_hours"] * 60
        left = max(0.0, goal_min - self._today_minutes())
        if self.phase == FOCUS:
            return (f"{fmt_clock(self.phase_total - self.phase_elapsed)} left in this focus block.\n"
                    f"{fmt_hm(left)} to go until today's {fmt_hm(goal_min)} goal.")
        if self.phase in (SHORT_BREAK, LONG_BREAK):
            return (f"Breaks are for resting your eyes and mind - {name} will still be there tonight.\n"
                    f"{fmt_hm(left)} to go until today's {fmt_hm(goal_min)} goal.")
        return f"Goal lock is on. {name} unlocks after {fmt_hm(goal_min)} of study today ({fmt_hm(left)} to go)."

    def _show_overlay(self, site):
        name = display_name(site)
        if self._overlay is not None and self._overlay.winfo_exists():
            self._overlay_title.configure(text=f"{name} is blocked while you study")
            self._overlay_text.configure(text=self._overlay_message(name))
            self._overlay.lift()
            return
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.configure(bg=T.BG)
        overlay.geometry(f"{overlay.winfo_screenwidth()}x{overlay.winfo_screenheight()}+0+0")
        overlay.attributes("-topmost", True)

        card = Card(overlay, corner_radius=24)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="", image=T.icon("shield", 46, T.ACCENT)).grid(row=0, column=0, pady=(48, 16))
        self._overlay_title = ctk.CTkLabel(card, text=f"{name} is blocked while you study",
                                           font=T.font(26, "semibold"), text_color=T.TEXT)
        self._overlay_title.grid(row=1, column=0, padx=72)
        self._overlay_text = ctk.CTkLabel(card, text=self._overlay_message(name), font=T.font(14),
                                          text_color=T.MUTED, justify="center")
        self._overlay_text.grid(row=2, column=0, padx=72, pady=(10, 30))
        ctk.CTkButton(card, text="Back to study", width=210, height=48, corner_radius=24, font=T.font(15, "semibold"),
                      fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color=T.ON_ACCENT,
                      command=self._close_overlay).grid(row=3, column=0, pady=(0, 48))
        overlay.bind("<Escape>", lambda e: self._close_overlay())
        overlay.bind("<Return>", lambda e: self._close_overlay())
        overlay.focus_force()
        overlay.after(12_000, self._close_overlay)
        self._overlay = overlay

    def _close_overlay(self):
        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None
            try:
                self.deiconify()
                self.lift()
                self.focus_force()
            except tk.TclError:
                pass

    def _render_shield_info(self):
        sites = list(self.cfg["block_sites"])
        names = [display_name(s) for s in sites]
        if not sites:
            pill, text = ("OFF", T.INPUT, T.MUTED), "Your block list is empty. Add sites in Settings."
        elif self._shield_on:
            verb = "is" if len(names) == 1 else "are"
            pill, text = ("ON", T.OK_SOFT, T.BREAK), f"{join_names(names)} {verb} blocked right now. Stay with it."
        else:
            pill = ("STANDBY", T.INPUT, T.MUTED)
            text = f"{join_names(names)} will be blocked as soon as you start focusing."
        if self.shield_pill.cget("text") != pill[0]:
            self.shield_pill.configure(text=pill[0], fg_color=pill[1], text_color=pill[2])
            self.shield_icon.configure(image=T.icon("shield", 20, T.BREAK if self._shield_on else T.MUTED))
            self.side_shield.configure(text="  Shield on" if self._shield_on else "  Shield standby",
                                       text_color=T.BREAK if self._shield_on else T.MUTED,
                                       image=T.icon("shield", 14, T.BREAK if self._shield_on else T.MUTED))
        self._set(self.shield_text, text)

        attempts = self.stats.get("blocked_today", 0)
        meta = [f"Blocked today: {attempts} attempt" + ("" if attempts == 1 else "s")]
        if self.hosts.writable:
            meta.append("System-wide block: " + ("active in every browser" if self.hosts.active else "ready"))
        else:
            meta.append("Browser guard closes blocked tabs. Run as administrator to block system-wide.")
        if self.stale_hosts_block:
            meta.append("An old block is still in the hosts file - run once as administrator to clear it.")
        self._set(self.shield_meta, "\n".join(meta))

        if self._chip_sites != sites:
            self._chip_sites = sites
            for child in self.chips.winfo_children():
                child.destroy()
            for i, name in enumerate(names[:6]):
                ctk.CTkLabel(self.chips, text=name, font=T.font(12, "semibold"), fg_color=T.INPUT, corner_radius=8,
                             text_color=T.TEXT, height=26, padx=10).grid(row=0, column=i, padx=(0, 6))
            if len(names) > 6:
                ctk.CTkLabel(self.chips, text=f"+{len(names) - 6}", font=T.font(12), text_color=T.MUTED).grid(
                    row=0, column=6)

        rows_key = (tuple(sites), self._shield_on)   # remove buttons lock while the shield is on
        if rows_key != self._site_rows_key:
            self._site_rows_key = rows_key
            self._render_site_settings()

    # ================================================================ settings

    def _sync_settings_widgets(self):
        goal = self.cfg["goal_hours"]
        self.goal_value.configure(text=f"{goal:g} h")
        blocks = math.ceil(goal * 60 / self.cfg["focus_min"])
        self.goal_hint.configure(text=f"That's {blocks} focus blocks of {self.cfg['focus_min']} minutes - "
                                      f"about {fmt_hm(self._plan_minutes(blocks))} including breaks.")
        for key, stepper in self.steppers.items():
            stepper.set(self.cfg[key])
        current = tuple(self.cfg[k] for k in ("focus_min", "short_break_min", "long_break_min", "long_break_every"))
        self.preset.set(next((label for label, values in PRESETS.items() if values == current), CUSTOM))

    def _on_preset(self, label):
        if label == CUSTOM:
            self.show_page("settings")
        else:
            focus, short, long_, every = PRESETS[label]
            self.cfg.update(focus_min=focus, short_break_min=short, long_break_min=long_, long_break_every=every)
        self._sync_settings_widgets()
        self._render_timer(force=True)

    def _on_timer(self, key, value):
        self.cfg.set(key, value)
        self._sync_settings_widgets()
        self._render_timer(force=True)

    def _on_goal(self, value):
        value = round(value * 2) / 2
        if value != self.cfg["goal_hours"]:
            self.cfg.set("goal_hours", value)
            self._sync_settings_widgets()
            self.refresh_stats()

    def _on_switch(self, key, switch):
        self.cfg.set(key, bool(switch.get()))
        self._update_shield()

    def _render_site_settings(self):
        if not hasattr(self, "sites_box"):
            return
        for child in self.sites_box.winfo_children():
            child.destroy()
        sites = self.cfg["block_sites"]
        locked = self._shield_on
        for i, site in enumerate(sites):
            row = ctk.CTkFrame(self.sites_box, fg_color=T.INPUT, corner_radius=10)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="", image=T.icon("shield", 15, T.ACCENT)).grid(row=0, column=0, padx=(14, 10), pady=8)
            ctk.CTkLabel(row, text=display_name(site), font=T.font(13, "semibold"), text_color=T.TEXT).grid(
                row=0, column=1, sticky="w")
            ctk.CTkLabel(row, text=site, font=T.font(12), text_color=T.FAINT).grid(row=0, column=2, padx=10)
            remove = ctk.CTkButton(row, text="", image=T.icon("close", 13, T.FAINT if locked else T.MUTED), width=32,
                                   height=30, corner_radius=8, fg_color="transparent", hover_color=T.CARD_HOVER,
                                   command=lambda s=site: self._remove_site(s))
            remove.grid(row=0, column=3, padx=(0, 6))
            if locked:
                remove.configure(state="disabled")
        if locked and sites:
            ctk.CTkLabel(self.sites_box, text="Sites can't be removed while the shield is on.", font=T.font(12),
                         text_color=T.FAINT, anchor="w").grid(row=len(sites), column=0, sticky="w", pady=(4, 0))

        for child in self.quick_box.winfo_children():
            child.destroy()
        suggestions = [s for s in QUICK_SITES if s not in sites]
        if suggestions:
            ctk.CTkLabel(self.quick_box, text="Quick add", font=T.font(12), text_color=T.FAINT).grid(
                row=0, column=0, padx=(0, 8))
        for i, site in enumerate(suggestions):
            ctk.CTkButton(self.quick_box, text=f"+ {display_name(site)}", height=28, width=0, corner_radius=8,
                          font=T.font(12), command=lambda s=site: self._add_site(s), **T.GHOST).grid(
                row=0, column=i + 1, padx=(0, 6))

    def _add_site(self, raw):
        site = normalize_site(raw)
        if not site:
            self.site_error.configure(text="That doesn't look like a website - try something like instagram.com")
            return
        self.site_error.configure(text="")
        sites = list(self.cfg["block_sites"])
        if site not in sites:
            sites.append(site)
            self.cfg.set("block_sites", sites)
        self.site_entry.delete(0, "end")
        self._chip_sites = None
        self._update_shield()

    def _remove_site(self, site):
        if self._shield_on:
            return
        self.cfg.set("block_sites", [s for s in self.cfg["block_sites"] if s != site])
        self._chip_sites = None
        self._update_shield()

    def _restart_admin(self):
        if self.phase == FOCUS and self.phase_started is not None:
            if not messagebox.askyesno("Restart as administrator?",
                                       "Your current focus block will be saved and the app will restart.", parent=self):
                return
        if relaunch_as_admin(["--elevated"]):
            self._quit()

    # ================================================================ window

    def _tint_title_bar(self):
        """Match the Windows 11 title bar to the app background (ignored on Windows 10)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            colorref = ctypes.c_int(int(T.BG[5:7] + T.BG[3:5] + T.BG[1:3], 16))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))
        except (AttributeError, OSError):
            pass

    def _on_close(self):
        if self.phase == FOCUS and self.phase_started is not None and self.phase_elapsed >= 60:
            if not messagebox.askyesno("Quit Focus Learn?",
                                       f"Your focus block is still running ({fmt_hm(self.phase_elapsed / 60)} done).\n\n"
                                       "Quit and save the time you've studied?", parent=self):
                return
        self._quit()

    def _quit(self):
        self._log_phase(completed=False)
        self.cfg.update(subject=self.subject.get().strip() or self.cfg["subject"], task=self.task.get().strip())
        self.hosts.release()
        self.destroy()


def _single_instance(wait_seconds):
    """Hold a named mutex so two copies never fight over the hosts file.

    Returns the handle, or None if another copy is already running. After a
    "Restart as administrator" the old copy needs a moment to exit, so the
    elevated one waits for it.
    """
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return True   # not Windows
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    deadline = time.monotonic() + wait_seconds
    while True:
        handle = kernel32.CreateMutexW(None, False, "Local\\FocusLearn.SingleInstance")
        error = ctypes.get_last_error()
        if handle and error != 183:          # 183 = ERROR_ALREADY_EXISTS
            return handle
        if handle:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def main(argv=()):
    instance = _single_instance(wait_seconds=8 if "--elevated" in argv else 0)
    if instance is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Focus Learn", "Focus Learn is already open - check your taskbar.")
        root.destroy()
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FocusLearn.StudyTimer")
    except (AttributeError, OSError):
        pass
    ctk.set_appearance_mode("dark")
    FocusLearnApp().mainloop()
