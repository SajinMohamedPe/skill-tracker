from __future__ import annotations

import subprocess
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

_LABEL = "com.skill-tracker.check"


def _plist_string(parent: Element, key: str, value: str) -> None:
    SubElement(parent, "key").text = key
    SubElement(parent, "string").text = value


def _plist_integer(parent: Element, key: str, value: int) -> None:
    SubElement(parent, "key").text = key
    SubElement(parent, "integer").text = str(value)


def install(executable: str, log_dir: Path) -> Path:
    """Install a launchd job to run 'skill-tracker check' daily at 09:00."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    log_dir.mkdir(parents=True, exist_ok=True)

    root = Element("plist", version="1.0")
    d = SubElement(root, "dict")

    _plist_string(d, "Label", _LABEL)

    SubElement(d, "key").text = "ProgramArguments"
    arr = SubElement(d, "array")
    SubElement(arr, "string").text = executable
    SubElement(arr, "string").text = "check"

    SubElement(d, "key").text = "StartCalendarInterval"
    interval = SubElement(d, "dict")
    _plist_integer(interval, "Hour", 9)
    _plist_integer(interval, "Minute", 0)

    _plist_string(d, "StandardOutPath", str(log_dir / "check.log"))
    _plist_string(d, "StandardErrorPath", str(log_dir / "check-error.log"))

    SubElement(d, "key").text = "RunAtLoad"
    SubElement(d, "false")

    tree = ElementTree(root)
    indent(tree, space="    ")
    plist_path.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    )
    with plist_path.open("ab") as f:
        tree.write(f, encoding="utf-8", xml_declaration=False)
        f.write(b"\n")

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def uninstall() -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    if plist_path.exists():
        plist_path.unlink()
