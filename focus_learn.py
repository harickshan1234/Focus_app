"""
Focus Learn - study up to 10 hours a day, with YouTube blocked while you focus.

Run with:        python focus_learn.py
No console:      pythonw focus_learn.py
"""

import sys

from focuslearn.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
