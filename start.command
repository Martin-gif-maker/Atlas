#!/bin/bash
# Atlas - double-click to start. The first start sets everything up (takes a minute or two).
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Setting up Atlas (only the first time)..."
    PYBIN=""
    for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
            PYBIN="$c"; break
        fi
    done
    if [ -z "$PYBIN" ]; then
        echo "Atlas needs Python 3.10 or newer: https://www.python.org/downloads/macos/"
        open "https://www.python.org/downloads/macos/" 2>/dev/null
        exit 1
    fi
    "$PYBIN" -m venv .venv || exit 1
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt || { rm -rf .venv; echo "Setup failed - see above."; exit 1; }
    echo "Done."
fi

mkdir -p "$HOME/Library/Logs"
nohup .venv/bin/python app.py >> "$HOME/Library/Logs/Atlas.log" 2>&1 &
disown
