# 🧠 Cyber Focus Dashboard Pro

A modern productivity application built with **Python** and **CustomTkinter** designed for developers, cybersecurity learners, bug bounty hunters, and students who want to eliminate distractions and track deep work sessions.

The application combines a **Pomodoro timer**, **focus enforcement**, **session analytics**, **SQLite database logging**, and **study statistics** into one desktop application.

---

# ✨ Features

## ⏱ Smart Focus Timer

* 25/5 Pomodoro Mode
* 50/10 Deep Work Mode
* 90/30 Long Session Mode
* Custom Timer
* Pause
* Stop
* Reset
* Add Extra Time

---

## 🎯 Focus Protection

The application continuously monitors the active window.

Features include:

* Detect active application
* Stop timer when focus is lost
* Detect YouTube usage
* Entertainment detection using page titles
* Warning popups
* Audible alerts

Example:

```
Watching:
Python Flask API Tutorial

→ Programming

Watching:
Funny Cat Compilation 😂

→ Entertainment
```

---

# 📊 Productivity Dashboard

The dashboard displays:

* Today's focus minutes
* Weekly study time
* Longest session
* Recent study history

Sessions are displayed inside a table for quick review.

---

# 📈 Analytics

Generate visual reports of your learning habits.

Current analytics include:

* Pie chart of study categories
* Time spent per subject

Built using:

* Matplotlib

---

# 📂 Study Categories

Track learning across different topics.

Examples:

* Linux
* Python
* Backend Development
* Bug Bounty
* PortSwigger Labs
* English
* Programming

More categories can easily be added.

---

# 💾 SQLite Database

Study sessions are permanently stored using SQLAlchemy.

Each session stores:

* Date
* Duration
* Category

Example:

| Date       | Category   | Duration |
| ---------- | ---------- | -------- |
| 2026-06-20 | Linux      | 50       |
| 2026-06-21 | Python     | 90       |
| 2026-06-22 | Bug Bounty | 25       |

---

# 🔔 Desktop Notifications

When a session finishes the application sends a Windows notification.

Example:

```
Focus Complete

Session saved successfully.
```

---

# 🖥 System Tray Support

The application can minimize to the Windows system tray.

Functions include:

* Restore
* Exit

Perfect for running silently in the background.

---

# 🔒 Focus Mode

A distraction-free fullscreen mode designed for long study sessions.

---

# 📉 CSV Logging

Sessions can also be exported into CSV files.

Example:

```
Date,Minutes
2026-06-20 10:30,25
2026-06-20 11:45,50
```

---

# 🎨 Modern UI

Built completely using:

* CustomTkinter
* ttk
* Dark Theme

Features:

* Sidebar Navigation
* Progress Bar
* Category Selector
* Session Table
* Responsive Layout

---

# 🏗 Built With

* Python
* CustomTkinter
* Tkinter
* SQLAlchemy
* SQLite
* Matplotlib
* PyGetWindow
* Plyer Notifications
* PyStray
* Pillow

---

# 📁 Project Structure

```
Cyber-Focus-Dashboard/

│
├── focus.py
├── focus.db
├── day.csv
├── requirements.txt
├── README.md
└── assets/
```

---

# 🚀 Installation

Clone the repository

```bash
git clone https://github.com/yourusername/Cyber-Focus-Dashboard.git
```

Move into the project

```bash
cd Cyber-Focus-Dashboard
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run

```bash
python focus.py
```

---

# 📦 Required Packages

```
customtkinter
sqlalchemy
matplotlib
pygetwindow
plyer
pystray
Pillow
```

Install manually:

```bash
pip install customtkinter sqlalchemy matplotlib pygetwindow plyer pystray pillow
```

---

# 🚧 Planned Features

* AI distraction detection
* Browser history monitoring
* Website blocker
* Daily goals
* Weekly goals
* Monthly reports
* Streak tracking
* XP system
* Achievement badges
* Leaderboard
* Music integration
* Automatic break reminders
* Focus score
* Heatmaps
* Productivity predictions
* Calendar integration
* Cloud synchronization
* Export reports to PDF
* Mobile companion app

---

# 🎯 Target Users

* Cybersecurity Students
* Ethical Hackers
* Bug Bounty Hunters
* Developers
* University Students
* Competitive Programmers
* Self-learners

---

# 🤝 Contributing

Contributions are welcome.

Feel free to:

* Fork the repository
* Create feature branches
* Submit pull requests
* Report bugs
* Suggest new features

---

# 📜 License

This project is licensed under the MIT License.

---

# ⭐ Support

If you find this project useful, consider giving it a ⭐ on GitHub.

It helps others discover the project and motivates future development.
