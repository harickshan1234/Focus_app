"""Reusable widgets: cards, the timer ring, steppers and the bar chart."""

import math
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import theme as T


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", T.CARD)
        kwargs.setdefault("corner_radius", 16)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.BORDER)
        super().__init__(master, **kwargs)


def caption(master, text):
    """Small uppercase heading used at the top of cards."""
    return ctk.CTkLabel(master, text=text.upper(), font=T.font(11, "semibold"), text_color=T.MUTED, anchor="w")


class ProgressRing(ctk.CTkLabel):
    """Smooth progress ring with the time in the middle.

    Drawn with Pillow at 4x and scaled down, because Tk canvas arcs are jagged.
    """

    def __init__(self, master, size=300, thickness=12, **kwargs):
        super().__init__(master, text="", **kwargs)
        self.size = size
        self.thickness = thickness
        self._state = None
        self._ring_image = None

    def draw(self, progress, color, big_text, small_text):
        state = (round(progress, 3), color, big_text, small_text)
        if state == self._state:
            return
        self._state = state

        out = self.size * 2            # 2x bitmap so it stays sharp on HiDPI screens
        w = out * 2                    # drawn at 2x again, then downsampled for anti-aliasing
        t = self.thickness * 4
        pad = 4
        img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        box = (pad, pad, w - pad, w - pad)
        d.ellipse(box, outline=T.TRACK, width=t)

        p = max(0.0, min(1.0, progress))
        if p > 0:
            end = -90 + 360 * p
            d.arc(box, start=-90, end=end, fill=color, width=t)
            c, r = w / 2, (w - 2 * pad) / 2 - t / 2
            for angle in (-90, end):  # round caps
                a = math.radians(angle)
                x, y = c + r * math.cos(a), c + r * math.sin(a)
                d.ellipse((x - t / 2, y - t / 2, x + t / 2, y + t / 2), fill=color)

        d.text((w / 2, w / 2 - w * 0.025), big_text, font=T.pil_font("segoeuisl.ttf", int(w * 0.2)),
               fill=T.TEXT, anchor="mm")
        d.text((w / 2, w / 2 + w * 0.135), small_text, font=T.pil_font("seguisb.ttf", int(w * 0.043)),
               fill=T.MUTED, anchor="mm")

        img = img.resize((out, out), Image.LANCZOS)
        self._ring_image = ctk.CTkImage(light_image=img, dark_image=img, size=(self.size, self.size))
        self.configure(image=self._ring_image)


class Stepper(ctk.CTkFrame):
    """[-] value [+] control for small whole-number settings."""

    def __init__(self, master, value, low, high, step=1, unit="", command=None):
        super().__init__(master, fg_color=T.INPUT, corner_radius=10, border_width=1, border_color=T.BORDER)
        self.value, self.low, self.high, self.step, self.unit = value, low, high, step, unit
        self.command = command
        style = dict(width=34, height=32, corner_radius=8, fg_color="transparent", hover_color=T.CARD_HOVER,
                     text_color=T.TEXT, font=T.font(17))
        ctk.CTkButton(self, text="−", command=lambda: self._bump(-1), **style).grid(row=0, column=0, padx=3, pady=3)
        self.label = ctk.CTkLabel(self, text="", width=76, font=T.font(13, "semibold"), text_color=T.TEXT)
        self.label.grid(row=0, column=1)
        ctk.CTkButton(self, text="+", command=lambda: self._bump(1), **style).grid(row=0, column=2, padx=3, pady=3)
        self._show()

    def _bump(self, direction):
        new = min(self.high, max(self.low, self.value + direction * self.step))
        if new != self.value:
            self.value = new
            self._show()
            if self.command:
                self.command(new)

    def _show(self):
        self.label.configure(text=f"{self.value:g} {self.unit}".strip())

    def set(self, value):
        self.value = value
        self._show()


class BarChart(tk.Canvas):
    """Daily study hours with a dashed goal line. Redraws itself on resize."""

    def __init__(self, master, height=220):
        super().__init__(master, height=height, bg=T.CARD, highlightthickness=0, bd=0)
        self.items = []   # [(label, hours, is_today)]
        self.goal = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set_data(self, items, goal):
        self.items, self.goal = items, goal
        self._draw()

    def _bar(self, x0, y0, x1, y1, radius, color):
        r = min(radius, (x1 - x0) / 2, y1 - y0)
        if r < 1:
            self.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
            return
        pts = [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y0 + r,
               x1, y1, x1, y1, x0, y1, x0, y1, x0, y0 + r, x0, y0 + r, x0, y0]
        self.create_polygon(pts, smooth=True, fill=color, outline="")

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 60 or not self.items:
            return
        s = self.winfo_fpixels("1i") / 96.0   # DPI scale
        small = (T.FAMILY, 9)
        left, right, top, bottom = 34 * s, 8 * s, 16 * s, 26 * s
        plot_w, plot_h = w - left - right, h - top - bottom
        peak = max([v for _, v, _ in self.items] + [self.goal, 1.0]) * 1.12

        def y(v):
            return top + plot_h * (1 - v / peak)

        step = next(n for n in (1, 2, 4, 5, 10, 20) if peak / n <= 6)
        v = step
        while v < peak:
            self.create_line(left, y(v), w - right, y(v), fill=T.TRACK)
            self.create_text(left - 8 * s, y(v), text=f"{v}h", anchor="e", fill=T.FAINT, font=small)
            v += step
        self.create_line(left, y(0), w - right, y(0), fill=T.BORDER)

        n = len(self.items)
        slot = plot_w / n
        bar_w = max(3 * s, min(30 * s, slot * 0.58))
        for i, (label, hours, is_today) in enumerate(self.items):
            cx = left + slot * (i + 0.5)
            if hours > 0:
                met = self.goal and hours >= self.goal - 1e-6
                color = T.ACCENT if met else ("#4B57A8" if is_today else T.BAR_IDLE)
                self._bar(cx - bar_w / 2, y(hours), cx + bar_w / 2, y(0), 5 * s, color)
                if n <= 14:
                    self.create_text(cx, y(hours) - 8 * s, text=f"{hours:.1f}", fill=T.MUTED, font=(T.FAMILY, 8))
            if n <= 14 or i % 5 == 0 or is_today:
                self.create_text(cx, h - bottom / 2, text=label, fill=T.TEXT if is_today else T.FAINT,
                                 font=(T.SEMIBOLD, 9) if is_today else small)

        if self.goal:
            gy = y(self.goal)
            self.create_line(left, gy, w - right, gy, fill=T.ACCENT, dash=(4, 4))
            self.create_text(w - right, gy - 4 * s, text=f"goal {self.goal:g}h", anchor="se", fill=T.ACCENT, font=small)
