from tkinter import Label, messagebox
import tkinter as tk
import pygetwindow as gw
import time
import os 
import sys
import customtkinter as ctk
import csv
import sqlalchemy
from tkinter import ttk 


class FocusApp:
    def __init__(self, root):
        self.root = root

        self.ctk = ctk
        self.ctk.set_default_color_theme("dark-blue")
        self.root.title("Focus App")
        self.root.resizable(True, True)
        self.ctk.set_appearance_mode("dark")
        self.root.geometry("300x500")
        self.root.resizable(False, False)
        self.session_time = 0
        self.time_is_running = False
        self.tabcontrol = ttk.Notebook(root)
        self.label = self.ctk.CTkLabel(
            self.root,
            text="Focus App",
            font=("Arial", 16)
        )
        self.label.pack(pady=20)

        self.time_label = self.ctk.CTkLabel(
            self.root,
            text="00:00",
            font=("Arial", 24)
        )
        self.time_label.pack(pady=20)

        self.reset_button = self.ctk.CTkButton(
            self.root,
            text="Reset Timer",
            command=self.reset_timer,
            font=("Arial", 12)
        )
        self.reset_button.pack(pady=10)
        self.start_session()
        
        self.focus_check_loop()
        self.extra_time_button = self.ctk.CTkButton(
            self.root,
            text="Add 5 Minutes",
            command=lambda: self.add_extra_time(5),
            font=("Arial", 12)
        )
        self.extra_time_button.pack(pady=10)
        self.make_window_topmost()
        self.window_smaller()
        # self.daily_analysis()
        
    def start_session(self):
        self.time_var = self.ctk.StringVar()

        self.timer_entry = self.ctk.CTkEntry(
            self.root,
            textvariable=self.time_var,
            font=("Arial", 12)
        )
        self.timer_entry.pack(pady=10)

        self.start_button = self.ctk.CTkButton(
            self.root,
            text="Start Session",
            command=self.start_timer,
            font=("Arial", 12)
        ) 
        self.start_button.pack(pady=10)

        self.stop_button = self.ctk.CTkButton(
            self.root,
            text="Stop Session",
            command=self.stop_timer,
            font=("Arial", 12)
        )
        self.stop_button.pack(pady=10)

    def start_timer(self):
        time_str = self.timer_entry.get()

        if time_str.isdigit():
            self.original_session_time = int(time_str) * 60
            self.session_time = self.original_session_time

        if not self.time_is_running:
            self.time_is_running = True
            self.update_timer()
     
    def focus_check_loop(self):
        if self.time_is_running:
            self.check_focus()
            
        self.root.after(1000,self.focus_check_loop)

    def check_focus(self):
        active_window = gw.getActiveWindow()

        if active_window is not None  and active_window.title != "Focus App":

            self.stop_timer()
    
        
    def update_timer(self):
        if self.time_is_running and self.session_time > 0:

            minutes = self.session_time // 60
            seconds = self.session_time % 60

            self.time_label.configure(
                text=f"{minutes:02}:{seconds:02}"
            )

            self.session_time -= 1

            self.root.after(1000, self.update_timer)

        elif self.session_time <= 0:
            self.time_label.configure(text="Session Complete!")

            self.daily_log(self.original_session_time // 60)

            messagebox.showinfo(
                "Session Complete",
                "Your focus session has ended!"
            )

            self.root.bell()
            self.time_is_running = False
    def stop_timer(self):
        self.time_is_running = False

    

    def youtube_check_loop(self):
        while self.time_is_running:
            active_window = gw.getActiveWindow()

            if active_window and active_window.title and "YouTube" in active_window.title:
                self.stop_timer()

                messagebox.showwarning(
                    "Focus Alert",
                    "You have navigated to YouTube. Focus session stopped!"
                )

                self.root.bell()
                break

            time.sleep(1)

    def daily_log(self, session_time):
        with open("day.csv", "a", newline="") as csvfile:
            log_writer = csv.writer(csvfile)
            log_writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), session_time])

    def daily_analysis(self):
        total_time = 0
        with open("day.csv", "r") as csvfile:
            log_reader = csv.reader(csvfile)
            for row in log_reader:
                if len(row) == 2 and row[1].isdigit():
                    total_time += int(row[1])
        return total_time

    def add_extra_time(self, extra_minutes):
        if self.time_is_running:
            self.session_time += extra_minutes * 60
        if not self.time_is_running:
            messagebox.showwarning("Timer Not Running", "Start the timer before adding extra time.")

    def make_window_topmost(self):
        self.root.attributes("-topmost", True)
    
    def window_smaller(self):
        self.root.geometry("200x300")


    def reset_timer(self):
        self.session_time = 0
        self.time_label.configure(text="00:00")
        self.time_is_running = False

    def sqlalchemy_add_log(self, session_time):
        engine = sqlalchemy.create_engine("sqlite:///focus.db")
        with engine.connect() as connection:
            connection.execute("create table if not exists focus (taimestamp text, session_time integer)")
 
    def enough_teller(self,session_time):
        0
    
root = ctk.CTk()

app = FocusApp(root)

root.mainloop()