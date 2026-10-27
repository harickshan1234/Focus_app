"""Colours, fonts and icons shared by every screen."""

import math
import os
import sys
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

WINDOWS = sys.platform == "win32"

# ---- Palette (dark only) ----
BG = "#0E1014"
SIDEBAR = "#12151B"
CARD = "#171B22"
CARD_HOVER = "#1E232C"
INPUT = "#11141A"
BORDER = "#252B36"
TRACK = "#262C38"
TEXT = "#E8EAF0"
MUTED = "#8B93A7"
FAINT = "#5B6275"
ACCENT = "#7C8CFF"         # focus
ACCENT_HOVER = "#6B7BF2"
ACCENT_SOFT = "#272D4F"    # selected segment, in-progress block dot
BAR_IDLE = "#353D5C"       # chart bars below the goal
ON_ACCENT = "#0E1014"      # text on accent-coloured buttons
BREAK = "#4FD1A5"          # breaks
BREAK_HOVER = "#41BE94"
OK_SOFT = "#173329"
DANGER = "#FF6B6B"

# ---- Fonts ----
FAMILY = "Segoe UI" if WINDOWS else "Helvetica"
SEMIBOLD = "Segoe UI Semibold" if WINDOWS else "Helvetica"
FONTS_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


@lru_cache(maxsize=None)
def font(size, weight="normal"):
    """CTkFont cache. weight: 'normal', 'semibold' or 'bold'. Needs a Tk root."""
    if weight == "semibold":
        return ctk.CTkFont(family=SEMIBOLD, size=size, weight="normal" if WINDOWS else "bold")
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


@lru_cache(maxsize=None)
def pil_font(filename, size):
    """Pillow font for text drawn into images (the timer ring)."""
    for name in (filename, "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(FONTS_DIR, name), size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# ---- Icons (Segoe Fluent Icons / MDL2 glyphs rendered to images) ----
ICONS = {
    "focus": "\uE916",
    "progress": "\uE9D2",
    "settings": "\uE713",
    "shield": "\uEA18",
    "play": "\uE768",
    "pause": "\uE769",
    "stop": "\uE71A",
    "skip": "\uE893",
    "check": "\uE73E",
    "close": "\uE711",
    "add": "\uE710",
}


def _icon_font_path():
    for name in ("SegoeIcons.ttf", "segmdl2.ttf"):
        path = os.path.join(FONTS_DIR, name)
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=None)
def icon(name, size=18, color=TEXT):
    """CTkImage of an icon glyph, or None when the icon font isn't installed."""
    path = _icon_font_path()
    if path is None:
        return None
    px = size * 3
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    glyph_font = ImageFont.truetype(path, int(px * 0.86))
    glyph = ICONS[name]
    left, top, right, bottom = draw.textbbox((0, 0), glyph, font=glyph_font)
    draw.text(((px - (right - left)) / 2 - left, (px - (bottom - top)) / 2 - top),
              glyph, font=glyph_font, fill=color)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def _draw_logo(size):
    """App mark: a rounded tile with a three-quarter progress ring."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.24), fill=CARD, outline=BORDER, width=max(1, s // 64))
    pad, width = s * 0.22, int(s * 0.1)
    box = (pad, pad, s - pad, s - pad)
    d.ellipse(box, outline=TRACK, width=width)
    d.arc(box, start=-90, end=180, fill=ACCENT, width=width)
    # round caps on the arc
    c, r = s / 2, (s - 2 * pad) / 2 - width / 2
    for angle in (-90, 180):
        a = math.radians(angle)
        x, y = c + r * math.cos(a), c + r * math.sin(a)
        d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def logo(size=32):
    img = _draw_logo(size * 2)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def app_icon_path():
    """Path to the window/taskbar .ico, generated on first run."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "focuslearn.ico")
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _draw_logo(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        except OSError:
            return None
    return path


# ---- Shared widget styles ----
SEGMENTED = dict(fg_color=INPUT, selected_color=ACCENT_SOFT, selected_hover_color="#2F3760",
                 unselected_color=INPUT, unselected_hover_color=CARD_HOVER, text_color=TEXT,
                 corner_radius=10, height=34)
COMBO = dict(fg_color=INPUT, border_color=BORDER, button_color=BORDER, button_hover_color=TRACK,
             dropdown_fg_color=CARD, dropdown_hover_color=CARD_HOVER, dropdown_text_color=TEXT,
             text_color=TEXT, border_width=1, corner_radius=10, height=40)
ENTRY = dict(fg_color=INPUT, border_color=BORDER, border_width=1, text_color=TEXT,
             placeholder_text_color=FAINT, corner_radius=10, height=40)
GHOST = dict(fg_color="transparent", hover_color=CARD_HOVER, border_width=1, border_color=BORDER, text_color=TEXT)
SWITCH = dict(text="", width=48, progress_color=ACCENT, fg_color=TRACK, button_color=TEXT, button_hover_color="#FFFFFF")
