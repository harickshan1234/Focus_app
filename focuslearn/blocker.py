"""Distraction blocking.

Two layers work together while the shield is on:

* WindowGuard - watches the foreground window. When it is a browser showing a
  blocked site (e.g. "Some video - YouTube - Google Chrome") it closes that tab
  with Ctrl+W, or minimises the browser. Works without admin rights.
* HostsBlocker - points blocked domains at 0.0.0.0 in the Windows hosts file so
  they don't load in any browser or app. Needs the app to run as administrator.
  The block lives in a marked section that is removed as soon as the shield
  turns off, and cleaned up on the next start if the app ever crashes.
"""

import ctypes
import os
import re
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
    "arc.exe", "chromium.exe", "thorium.exe", "librewolf.exe", "waterfox.exe", "floorp.exe",
    "zen.exe", "iexplore.exe", "yandex.exe", "browser.exe",
}

SITE_NAMES = {
    "youtube": "YouTube", "instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok",
    "reddit": "Reddit", "x": "X", "twitter": "Twitter", "netflix": "Netflix", "twitch": "Twitch",
    "primevideo": "Prime Video", "hotstar": "Hotstar", "discord": "Discord", "snapchat": "Snapchat",
}

# Every hostname that belongs to a site, for the hosts-file block.
SITE_DOMAINS = {
    "youtube.com": ["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
                    "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"],
    "x.com": ["x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"],
    "twitter.com": ["twitter.com", "www.twitter.com", "mobile.twitter.com", "x.com", "www.x.com"],
    "facebook.com": ["facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"],
    "reddit.com": ["reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"],
}

# Names a site uses in its page titles, longest first.
TITLE_NAMES = {
    "youtube": ["youtube music", "youtube kids", "youtube studio", "youtube"],
    "x": ["x", "twitter"],
    "twitter": ["twitter", "x"],
}

# A site name only counts when it stands alone between title separators, e.g.
# "Video - YouTube - Google Chrome" or "(3) YouTube", but not "youtube notes - Google Docs".
_SEP = r"[-–—|/·•]"
_TITLE_TEMPLATE = (r"(?:^(?:\(\d+\+?\)\s*)?|\s" + _SEP + r"\s)(?:{names})"
                   r"(?=\s*$|\s" + _SEP + r"\s|\s+and\s+\d+\s+more\s+pages?)")

_DOMAIN_RE = re.compile(r"^(?=.{3,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_site(text):
    """'https://www.YouTube.com/watch?v=1' -> 'youtube.com'. None if it isn't a domain."""
    s = text.strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)
    s = re.split(r"[/?#:]", s, maxsplit=1)[0].strip(".")
    for prefix in ("www.", "m."):
        if s.startswith(prefix) and "." in s[len(prefix):]:
            s = s[len(prefix):]
    if s and "." not in s and s.isalnum():
        s += ".com"
    return s if _DOMAIN_RE.match(s) else None


def site_key(site):
    return site.split(".")[0]


def display_name(site):
    return SITE_NAMES.get(site_key(site), site)


def domains_for(site):
    return SITE_DOMAINS.get(site) or [site, "www." + site, "m." + site]


def title_pattern(site):
    names = TITLE_NAMES.get(site_key(site), [site_key(site)])
    alternatives = "|".join(re.escape(n).replace(r"\ ", r"\s+") + r"(?:\.[a-z]{2,})?" for n in names)
    return re.compile(_TITLE_TEMPLATE.format(names=alternatives), re.IGNORECASE)


# ------------------------------------------------------------ Win32 helpers

if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32")

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.LPCWSTR, ctypes.c_int]
    _shell32.ShellExecuteW.restype = ctypes.c_void_p

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
KEYEVENTF_KEYUP = 0x0002
VK_SHIFT, VK_CONTROL, VK_MENU, VK_W = 0x10, 0x11, 0x12, 0x57
SW_MINIMIZE = 6


def _process_name(pid):
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def foreground_window():
    """(hwnd, title, process name) of the window the user is looking at, or None."""
    if not IS_WINDOWS:
        return None
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return hwnd, buf.value, _process_name(pid.value)


def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        return bool(_shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin(extra_args=()):
    """Restart this script elevated (UAC prompt). True if the new process started."""
    if not IS_WINDOWS:
        return False
    args = [a for a in sys.argv[1:] if a not in extra_args] + list(extra_args)
    if getattr(sys, "frozen", False):          # installed FocusLearn.exe
        exe, params = sys.executable, subprocess.list2cmdline(args)
        workdir = os.path.dirname(sys.executable)
    else:                                      # python focus_learn.py
        script = os.path.abspath(sys.argv[0])
        exe = sys.executable
        windowed = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(windowed):
            exe = windowed
        params = subprocess.list2cmdline([script] + args)
        workdir = os.path.dirname(script)
    result = _shell32.ShellExecuteW(None, "runas", exe, params, workdir, 1)
    return (result or 0) > 32


def flush_dns():
    if not IS_WINDOWS:
        return
    try:
        subprocess.Popen(["ipconfig", "/flushdns"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        pass


# ------------------------------------------------------------ Window guard

@dataclass
class Hit:
    hwnd: int
    site: str
    title: str


class WindowGuard:
    def __init__(self):
        self._patterns = {}

    def match(self, title, sites):
        """The first blocked site a browser window title belongs to, or None."""
        for site in sites:
            pattern = self._patterns.get(site)
            if pattern is None:
                pattern = self._patterns[site] = title_pattern(site)
            if pattern.search(title):
                return site
        return None

    def check(self, sites):
        win = foreground_window()
        if not win:
            return None
        hwnd, title, process = win
        if process not in BROWSER_PROCESSES or not title:
            return None
        site = self.match(title, sites)
        return Hit(hwnd, site, title) if site else None

    @staticmethod
    def close_tab(hwnd):
        """Send Ctrl+W to the browser, if it is still the foreground window."""
        if not IS_WINDOWS or _user32.GetForegroundWindow() != hwnd:
            return False
        # A held Shift would turn Ctrl+W into Ctrl+Shift+W (close the whole window).
        for vk in (VK_SHIFT, VK_MENU):
            if _user32.GetAsyncKeyState(vk) & 0x8000:
                _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        _user32.keybd_event(VK_CONTROL, 0, 0, 0)
        _user32.keybd_event(VK_W, 0, 0, 0)
        _user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
        _user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        return True

    @staticmethod
    def minimize(hwnd):
        if IS_WINDOWS:
            _user32.ShowWindow(hwnd, SW_MINIMIZE)


# ------------------------------------------------------------ Hosts file

HOSTS_PATH = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
BEGIN_MARK = "# >>> Focus Learn study block (removed automatically when the session ends) >>>"
END_MARK = "# <<< Focus Learn study block <<<"


def strip_block(text):
    """hosts file text without the Focus Learn section."""
    out, inside = [], False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == BEGIN_MARK:
            inside = True
        elif inside:
            inside = stripped != END_MARK
        else:
            out.append(line)
    return "".join(out)


class HostsBlocker:
    def __init__(self, path=HOSTS_PATH):
        self.path = path
        self.domains = frozenset()   # what is blocked right now
        self._failed = None          # domain set whose last write failed (don't retry every second)
        self.writable = self._probe()

    @property
    def active(self):
        return bool(self.domains)

    def _probe(self):
        try:
            with open(self.path, "a", encoding="utf-8"):
                return True
        except OSError:
            return False

    def _read(self):
        with open(self.path, encoding="utf-8", errors="surrogateescape", newline="") as f:
            return f.read()

    def _write(self, text):
        with open(self.path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(text)

    def has_block(self):
        try:
            return BEGIN_MARK in self._read()
        except OSError:
            return False

    def block(self, sites):
        wanted = frozenset(d for s in sites for d in domains_for(s))
        if not wanted:
            return self.release()
        if wanted == self.domains or wanted == self._failed:
            return wanted == self.domains
        try:
            text = strip_block(self._read())
            nl = "\r\n" if "\r\n" in text else "\n"
            lines = [BEGIN_MARK]
            for domain in sorted(wanted):
                lines += [f"0.0.0.0 {domain}", f"::1 {domain}"]
            lines.append(END_MARK)
            self._write(text.rstrip("\r\n") + nl + nl + nl.join(lines) + nl)
        except OSError:
            self._failed = wanted
            return False
        self.domains, self._failed = wanted, None
        flush_dns()
        return True

    def release(self):
        """Remove the block (no-op when nothing is blocked). Safe to call any time."""
        try:
            text = self._read()
            if BEGIN_MARK in text:
                self._write(strip_block(text).rstrip("\r\n") + ("\r\n" if "\r\n" in text else "\n"))
                flush_dns()
        except OSError:
            return False
        self.domains, self._failed = frozenset(), None
        return True
