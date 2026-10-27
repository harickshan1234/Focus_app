"""
Build the Windows installer: dist/FocusLearn-Setup-<version>.exe

Needs:
  * PyInstaller        pip install pyinstaller
  * Inno Setup 6       https://jrsoftware.org/isinfo.php  (or: winget install JRSoftware.InnoSetup)

Run with:  python build_installer.py
           python build_installer.py --exe-only     (just dist/FocusLearn/FocusLearn.exe)
"""

import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
sys.path.insert(0, ROOT)

from focuslearn import __version__          # noqa: E402
from focuslearn.theme import app_icon_path  # noqa: E402

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'harickshan1234'),
      StringStruct('FileDescription', 'Focus Learn'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'FocusLearn'),
      StringStruct('OriginalFilename', 'FocusLearn.exe'),
      StringStruct('ProductName', 'Focus Learn'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def find_iscc():
    candidates = [os.environ.get("ISCC", ""), shutil.which("iscc") or ""]
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramFiles", "")):
        if base:
            candidates += glob.glob(os.path.join(base, "Programs", "Inno Setup *", "ISCC.exe"))
            candidates += glob.glob(os.path.join(base, "Inno Setup *", "ISCC.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def build_exe():
    icon = app_icon_path()
    os.makedirs(BUILD, exist_ok=True)
    version_file = os.path.join(BUILD, "version_info.txt")
    nums = tuple(int(p) for p in (__version__.split(".") + ["0", "0", "0"])[:4])
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(VERSION_INFO.format(nums=nums, version=__version__))

    assets = os.path.join(ROOT, "focuslearn", "assets")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", os.path.join(ROOT, "focus_learn.py"),
        "--name", "FocusLearn", "--onedir", "--windowed", "--noconfirm", "--clean",
        "--icon", icon,
        "--version-file", version_file,
        "--add-data", f"{assets}{os.pathsep}focuslearn/assets",
        "--collect-data", "customtkinter",
        "--exclude-module", "numpy",            # Pillow imports it optionally; the app never uses it (-28 MB)
        "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyinstaller"), "--specpath", BUILD,
    ], check=True)
    exe = os.path.join(DIST, "FocusLearn", "FocusLearn.exe")
    print(f"\nApp built: {exe}")
    return exe


def build_installer():
    iscc = find_iscc()
    if not iscc:
        sys.exit("\nInno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php "
                 "(or run: winget install JRSoftware.InnoSetup), then run this script again.")
    subprocess.run([iscc, f"/DAppVersion={__version__}", os.path.join(ROOT, "installer", "FocusLearn.iss")],
                   check=True)
    setup = os.path.join(DIST, f"FocusLearn-Setup-{__version__}.exe")
    print(f"\nInstaller built: {setup}")


if __name__ == "__main__":
    build_exe()
    if "--exe-only" not in sys.argv:
        build_installer()
