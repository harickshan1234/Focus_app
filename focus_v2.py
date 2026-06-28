import tkinter as tk

import customtkinter as ctk
from tkinter import ttk, messagebox
import datetime
import threading
import matplotlib.pyplot as plt
import pygetwindow as gw
import time
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.orm import declarative_base, sessionmaker
import csv
from plyer import notification
import pystray
from PIL import Image, ImageDraw
import winreg

DB_URL = "sqlite:///focus.db"
Base = declarative_base()
engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()



class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    date = Column(String)
    duration = Column(Integer)
    category = Column(String)


Base.metadata.create_all(engine)



class FocusApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cyber Focus Dashboard Pro v4")
        self.root.geometry("1100x750")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.running = False
        self.remaining = 0
        self.total = 0

        self.mode = "25/5"

        self.categories = [
            "Linux", "backend", "english","python",
            "Bug Bounty", "portswigger", "Programming"
        ]

        self.blocked = ["youtube", "discord", "facebook", "instagram", "tiktok"]

        self.setup_ui()
        self.focus_loop()

    def setup_ui(self):

        self.sidebar = ctk.CTkFrame(self.root, width=200)
        self.sidebar.pack(side="left", fill="y")

        self.main = ctk.CTkFrame(self.root)
        self.main.pack(side="right", expand=True, fill="both")

        ctk.CTkButton(self.sidebar, text="Dashboard").pack(pady=10)
        ctk.CTkButton(self.sidebar, text="Analytics", command=self.show_analytics).pack(pady=10)
        ctk.CTkButton(self.sidebar, text="Focus Mode", command=self.fullscreen_lock).pack(pady=10)
        ctk.CTkButton(self.sidebar, text="Tray Mode", command=self.minimize_to_tray).pack(pady=10)
        ctk.CTkButton(self.sidebar , text="side panel",command= self.side_tray ).pack(pady=10)

        self.timer_label = ctk.CTkLabel(self.main, text="00:00", font=("Arial", 40))
        self.timer_label.pack(pady=10)

        self.progress = ctk.CTkProgressBar(self.main, width=400)
        self.progress.pack(pady=10)

        self.mode_selector = ctk.CTkComboBox(self.main, values=["25/5", "50/10", "90/30","Custom"])
        self.mode_selector.set("25/5")
        self.mode_selector.pack()

        self.entry = ctk.CTkEntry(self.main, placeholder_text="Minutes (custom)")
        self.entry.pack(pady=5)

        self.category = ctk.CTkComboBox(self.main, values=self.categories)
        self.category.set("Web Security")
        self.category.pack()

        btns = ctk.CTkFrame(self.main)
        btns.pack(pady=10)

        ctk.CTkButton(btns, text="Start", command=self.start).pack(side="left", padx=5)
        ctk.CTkButton(btns, text="Stop", command=self.stop).pack(side="left", padx=5)
        ctk.CTkButton(btns, text="Reset", command=self.reset).pack(side="left", padx=5)

    
        self.stats = ctk.CTkFrame(self.main)
        self.stats.pack(pady=20, fill="x")

        self.today = ctk.CTkLabel(self.stats, text="Today: 0 min")
        self.today.pack()

        self.week = ctk.CTkLabel(self.stats, text="Week: 0 min")
        self.week.pack()

        self.longest = ctk.CTkLabel(self.stats, text="Longest: 0 min")
        self.longest.pack()

        self.tree = ttk.Treeview(self.main, columns=("date","cat","min"), show="headings")
        self.tree.heading("date", text="Date")
        self.tree.heading("cat", text="Category")
        self.tree.heading("min", text="Minutes")
        self.tree.pack(expand=True, fill="both")

    def start(self):
        if self.running:
            return

        mode = self.mode_selector.get()

        if mode == "25/5":
            self.total = 25 * 60
        elif mode == "50/10":
            self.total = 50 * 60
        elif mode == "90/30":
            self.total  = 90 * 60
        else:
            if not self.entry.get().isdigit():
                messagebox.showerror("Error", "Enter valid minutes")
                return
            self.total = int(self.entry.get()) * 60

        self.remaining = self.total
        self.running = True
        self.tick()

    def tick(self):
        if not self.running:
            return

        if self.remaining > 0:
            m, s = divmod(self.remaining, 60)
            self.timer_label.configure(text=f"{m:02}:{s:02}")
            self.progress.set(self.remaining / self.total)
            self.remaining -= 1
            self.root.after(1000, self.tick)
        else:
            self.complete()

    def stop(self):
        self.running = False

    def reset(self):
        self.running = False
        self.remaining = 0
        self.timer_label.configure(text="00:00")
        self.progress.set(0)

    def complete(self):
        self.running = False

        s = Session(
            date=str(datetime.date.today()),
            duration=self.total // 60,
            category=self.category.get()
        )
        db.add(s)
        db.commit()

        notification.notify(
            title="Focus Complete",
            message="Session saved successfully"
        )

        self.refresh()
    

    def refresh(self):
        today = db.query(Session).filter(Session.date == str(datetime.date.today())).all()
        week = db.query(Session).all()

        self.today.configure(text=f"Today: {sum(x.duration for x in today)} min")
        self.week.configure(text=f"Week: {sum(x.duration for x in week)} min")

        longest = max([x.duration for x in week], default=0)
        self.longest.configure(text=f"Longest: {longest} min")

        self.tree.delete(*self.tree.get_children())

        for x in week[-50:]:
            self.tree.insert("", "end", values=(x.date, x.category, x.duration))
        
    def daily_log(self, session_time):
        with open("day.csv", "a", newline="") as csvfile:
            log_writer = csv.writer(csvfile)
            log_writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), session_time])

    def show_analytics(self):
        data = db.query(Session).all()

        if not data:
            return

        cats = {}
        for d in data:
            cats[d.category] = cats.get(d.category, 0) + d.duration

        plt.figure()
        plt.pie(cats.values(), labels=cats.keys(), autopct="%1.1f%%")
        plt.title("Category Distribution")
        plt.show()

    def fullscreen_lock(self):
        self.root.attributes("-fullscreen", True)

    def side_tray(self):
        self.root.geometry("200x200")
        self.sidebar.destroy()
        self.root.resizable(False,False)

    def minimize_to_tray(self):
        image = Image.new("RGB", (64, 64), "black")
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 54, 54), fill="green")

        icon = pystray.Icon("Focus", image, menu=pystray.Menu(
            pystray.MenuItem("Restore", self.restore),
            pystray.MenuItem("Exit", self.exit_app)
        ))

        threading.Thread(target=icon.run, daemon=True).start()
        self.root.withdraw()

    def enough_time(self,complete):
        self.today = 5
        if self.complete >self.today:
            tk.Message("do another session")
            
    def shorting(self,title):
        self.scores = {
            "cybersecurity": 0,
            "programming": 0,
            "entertainment": 0,
            "problem_solving": 0
        }

        title = title.lower()

        if any(word in title for word in ["kali linux", "hacking", "bug"]):
            self.scores["cybersecurity"] += 3

        if any(word in title for word in ["python", "api", "development"]):
            self.scores["programming"] += 3

        if any(word in title for word in ["interview", "music", "😂", "🤣", "❤️", "🔥"]):
            self.scores["entertainment"] += 4

        if any(word in title for word in ["solution", "error"]):
            self.scores["problem_solving"] += 2

        return max(self.scores, key=self.scores.get)
       


    def focus_loop(self):
        w = gw.getActiveWindowTitle()
        if w and "youtube" in w.lower():
            category = self.shorting(w)
            print("Full title:", w, "Category:", category)
            if category == "entertainment":
                messagebox.showwarning("Blocked", "Detected entertainment content in Chrome, please stop")
                self.running = False
        self.root.after(2000, self.focus_loop)

    def restore(self):
        self.root.deiconify()

    def exit_app(self):
        self.root.destroy()

    def enable_autostart(self):
        path = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Software\Microsoft\Windows\CurrentVersion\Run",
                              0, winreg.KEY_SET_VALUE)

        winreg.SetValueEx(path, "FocusApp", 0, winreg.REG_SZ, sys.executable)


if __name__ == "__main__":
    root = ctk.CTk()
    app = FocusApp(root)
    root.mainloop()