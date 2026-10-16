"""Start Atlas:  python app.py"""
import sys

from atlas.core import appbase
from atlas.window import MainWindow

if __name__ == "__main__":
    sys.exit(appbase.run(MainWindow))
