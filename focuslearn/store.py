"""SQLite storage.

Uses the same `sessions` and `settings` tables as main.py (focus_dashboard.db),
so study time logged in the old dashboard still counts toward your daily goal.
Focus Learn's own settings are stored with a "focuslearn." key prefix.

The installed app (a frozen FocusLearn.exe) can't write to its install folder,
so it keeps its database in %LOCALAPPDATA%/FocusLearn instead.
"""

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta

if getattr(sys, "frozen", False):
    _DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FocusLearn")
else:
    _DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_DATA_DIR, "focus_dashboard.db")

SETTINGS_PREFIX = "focuslearn."
DEFAULTS = {
    "goal_hours": 10.0,
    "focus_min": 50,
    "short_break_min": 10,
    "long_break_min": 20,
    "long_break_every": 3,
    "auto_start_breaks": True,
    "auto_start_focus": False,
    "block_sites": ["youtube.com"],
    "block_during_breaks": True,
    "goal_lock": False,
    "close_tab": True,
    "confirm_stop": True,
    "subject": "Python",
    "task": "",
}


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _scalar(sql, params=()):
    with _db() as c:
        row = c.execute(sql, params).fetchone()
    return row[0] if row and row[0] is not None else 0


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _db() as c:
        # Same schema as main.py, so both apps can share one database.
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                project TEXT,
                subject TEXT,
                task TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_minutes REAL NOT NULL,  -- actual elapsed minutes
                completed INTEGER NOT NULL,      -- 1 = ran to the end, 0 = stopped early
                is_break INTEGER NOT NULL,       -- breaks are excluded from study hours
                is_deep_work INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # One row per distraction the shield intercepted.
        c.execute("""
            CREATE TABLE IF NOT EXISTS block_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL,
                site TEXT NOT NULL
            )
        """)


class Settings:
    """Typed key/value settings backed by the `settings` table."""

    def __init__(self):
        self._values = dict(DEFAULTS)
        with _db() as c:
            rows = c.execute("SELECT key, value FROM settings WHERE key LIKE ?", (SETTINGS_PREFIX + "%",)).fetchall()
        for key, raw in rows:
            name = key[len(SETTINGS_PREFIX):]
            if name not in DEFAULTS:
                continue
            try:
                value = json.loads(raw)
            except (TypeError, ValueError):
                continue
            default = DEFAULTS[name]
            if isinstance(value, type(default)) or (isinstance(default, float) and isinstance(value, int)):
                self._values[name] = value

    def __getitem__(self, key):
        return self._values[key]

    def set(self, key, value):
        self.update(**{key: value})

    def update(self, **values):
        with _db() as c:
            for key, value in values.items():
                self._values[key] = value
                c.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                          (SETTINGS_PREFIX + key, json.dumps(value)))


# ---------------------------------------------------------------- sessions

def log_session(mode, subject, task, start, end, minutes, completed, is_break):
    with _db() as c:
        c.execute(
            "INSERT INTO sessions (mode, project, subject, task, start_time, end_time, "
            "duration_minutes, completed, is_break, is_deep_work) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (mode, None, subject, task, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"),
             round(minutes, 2), int(completed), int(is_break)),
        )


def focus_minutes_on(d):
    return _scalar("SELECT SUM(duration_minutes) FROM sessions WHERE is_break = 0 AND date(start_time) = ?",
                   (d.isoformat(),))


def focus_blocks_on(d):
    """Focus blocks that ran to the end on day d."""
    return _scalar("SELECT COUNT(*) FROM sessions WHERE is_break = 0 AND completed = 1 AND date(start_time) = ?",
                   (d.isoformat(),))


def _minutes_by_day(where="", params=()):
    with _db() as c:
        rows = c.execute("SELECT date(start_time), SUM(duration_minutes) FROM sessions "
                         f"WHERE is_break = 0 {where} GROUP BY 1", params).fetchall()
    return dict(rows)


def daily_minutes(days, end=None):
    """[(date, minutes)] for the last `days` days, oldest first, gaps filled with 0."""
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    totals = _minutes_by_day("AND date(start_time) BETWEEN ? AND ?", (start.isoformat(), end.isoformat()))
    return [(start + timedelta(days=i), totals.get((start + timedelta(days=i)).isoformat(), 0.0)) for i in range(days)]


def goal_streak(goal_minutes, before):
    """Consecutive days right before `before` on which the daily goal was met."""
    totals = _minutes_by_day("AND date(start_time) < ?", (before.isoformat(),))
    streak, d = 0, before - timedelta(days=1)
    while totals.get(d.isoformat(), 0) >= goal_minutes - 1e-6:
        streak += 1
        d -= timedelta(days=1)
    return streak


def best_day_minutes():
    return _scalar("SELECT MAX(total) FROM (SELECT SUM(duration_minutes) AS total FROM sessions "
                   "WHERE is_break = 0 GROUP BY date(start_time))")


def subject_minutes(start, end):
    """[(subject, minutes)] between two dates, biggest first."""
    with _db() as c:
        return c.execute(
            "SELECT COALESCE(NULLIF(TRIM(subject), ''), 'Other'), SUM(duration_minutes) FROM sessions "
            "WHERE is_break = 0 AND date(start_time) BETWEEN ? AND ? GROUP BY 1 ORDER BY 2 DESC",
            (start.isoformat(), end.isoformat()),
        ).fetchall()


def recent_sessions(limit=5):
    """[(start datetime, subject, task, minutes, completed)] newest first."""
    with _db() as c:
        rows = c.execute("SELECT start_time, subject, task, duration_minutes, completed FROM sessions "
                         "WHERE is_break = 0 ORDER BY start_time DESC LIMIT ?", (limit,)).fetchall()
    return [(datetime.fromisoformat(s), subj, task, mins, bool(done)) for s, subj, task, mins, done in rows]


# ------------------------------------------------------------ block events

def log_block(site):
    with _db() as c:
        c.execute("INSERT INTO block_events (time, site) VALUES (?, ?)",
                  (datetime.now().isoformat(timespec="seconds"), site))


def blocks_on(d):
    return _scalar("SELECT COUNT(*) FROM block_events WHERE date(time) = ?", (d.isoformat(),))
