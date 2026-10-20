"""Collect license notices for the Python/Tcl/Tk runtime used in a build."""
from pathlib import Path
import hashlib
import sys
import tkinter


def write_runtime_licenses(destination):
    if sys.version_info[:3] != (3, 13, 2):
        raise ValueError("Use Python 3.13.2 or update the runtime license collection first.")
    if tkinter.Tcl().call("info", "patchlevel") != "8.6.15":
        raise ValueError("Update the Tcl runtime license before building with this runtime.")
    tcl = Path(__file__).with_name("tcl-8.6.15-LICENSE.terms")
    if hashlib.sha256(tcl.read_bytes()).hexdigest() != "c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16":
        raise ValueError("Tcl license SHA-256 mismatch")
    sources = [("Python 3.13.2", Path(sys.base_prefix) / "LICENSE.txt"),
               ("Tcl 8.6.15", tcl),
               ("Tk 8.6.15", Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms")]
    notices = []
    for title, path in sources:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"Empty {title} license")
        notices.append(f"=== {title} ===\n" + text)
    Path(destination).write_text("\n\n".join(notices), encoding="utf-8")
