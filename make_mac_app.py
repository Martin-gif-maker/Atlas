"""Make a real Mac app for this project in ~/Applications, so it opens from Spotlight, Launchpad or the Dock.

    python make_mac_app.py

The app is a small launcher: it runs app.py with the project's own Python environment (.venv). If that does
not exist yet, it opens start.command in Terminal first, which sets everything up and then starts the app.
Run this again if you move the project folder.
"""
from __future__ import annotations

import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = next(p for p in sorted(HERE.iterdir()) if (p / "__init__.py").exists() and p.name != "tests")
sys.path.insert(0, str(HERE))
info = __import__(PACKAGE.name)
NAME, VERSION = info.APP_NAME, info.__version__
GLYPH = getattr(info, "ICON", "")
MIC_TEXT = getattr(info, "MICROPHONE_USE", "")
_qt = None                    # the Qt application used to draw the icon


def draw_icon(path: Path) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    global _qt
    _qt = QGuiApplication.instance() or QGuiApplication(["icon", "-platform", "offscreen"])
    appicon = __import__(f"{PACKAGE.name}.core.appicon", fromlist=["image"])
    img = appicon.image(GLYPH, 1024)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / f"{NAME}.iconset"
        iconset.mkdir()
        for px in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{px}x{px}{'@2x' if scale == 2 else ''}.png"
                img.scaled(px * scale, px * scale, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation).save(str(iconset / name))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(path)], check=True)


def make() -> Path:
    apps = Path.home() / "Applications"
    apps.mkdir(exist_ok=True)
    target = apps / f"{NAME}.app"
    build = apps / f".{NAME}-build.app"                 # osacompile only makes an applet if the name ends in .app
    shutil.rmtree(build, ignore_errors=True)

    folder = shlex.quote(str(HERE))
    launch = (
        "#!/bin/bash\n"
        f"cd {folder} 2>/dev/null || {{ osascript -e 'display alert \"{NAME}\" message "
        f"\"The {NAME} folder has moved. Run make_mac_app.py again from its new place.\"'; exit 1; }}\n"
        "mkdir -p \"$HOME/Library/Logs\"\n"
        "if [ -x .venv/bin/python ]; then\n"
        f"  exec .venv/bin/python app.py >> \"$HOME/Library/Logs/{NAME}.log\" 2>&1\n"
        "else\n"
        "  open -a Terminal start.command        # first start: set up, then open the app\n"
        "fi\n")
    applet = ('on run\n'
              '  set launcher to (POSIX path of (path to me)) & "Contents/Resources/launch.sh"\n'
              '  do shell script "nohup " & quoted form of launcher & " >/dev/null 2>&1 &"\n'
              'end run\n'
              'on reopen\n'
              '  run\n'
              'end reopen\n')
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:
        f.write(applet)
    try:
        subprocess.run(["osacompile", "-o", str(build), f.name], check=True, capture_output=True)
    finally:
        Path(f.name).unlink()
    res = build / "Contents" / "Resources"
    (res / "launch.sh").write_text(launch)
    (res / "launch.sh").chmod(0o755)
    draw_icon(res / "applet.icns")

    plist = build / "Contents" / "Info.plist"
    data = plistlib.loads(plist.read_bytes())
    data.update({"CFBundleName": NAME, "CFBundleDisplayName": NAME,
                 "CFBundleIdentifier": f"com.martingenov.{NAME.lower()}",
                 "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION, "LSUIElement": False})
    if MIC_TEXT:
        data["NSMicrophoneUsageDescription"] = MIC_TEXT
    plist.write_bytes(plistlib.dumps(data))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(build)], capture_output=True)

    shutil.rmtree(target, ignore_errors=True)
    build.rename(target)
    target.touch()                                      # makes Finder show the new icon
    return target


if __name__ == "__main__":
    if sys.platform != "darwin":
        sys.exit("This makes a macOS app. On Windows or Linux, start the app with:  python app.py")
    path = make()
    print(f"{NAME}.app is ready in {path.parent}.")
    print(f"Open it with Spotlight (⌘Space, type {NAME}) or drag it to your Dock.")
