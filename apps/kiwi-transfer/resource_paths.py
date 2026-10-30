"""Resolve bundled assets without importing the optional command interface."""
from pathlib import Path
import sys


def resource_path(relative, source_dir=None):
    base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else source_dir or Path(__file__).parent
    return str(base / relative)
