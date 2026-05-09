from __future__ import annotations

import platform
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


def _install_macos(executable: str, log_dir: Path, hour: int, minute: int) -> Path:
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
    _plist_integer(interval, "Hour", hour)
    _plist_integer(interval, "Minute", minute)

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


def _install_linux(executable: str, log_dir: Path, hour: int, minute: int) -> Path:
    """Install a systemd user timer for Linux."""
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    service_path = systemd_dir / "skill-tracker-check.service"
    timer_path = systemd_dir / "skill-tracker-check.timer"

    service_path.write_text(
        "[Unit]\n"
        "Description=skill-tracker daily check\n\n"
        "[Service]\n"
        f"ExecStart={executable} check\n"
        f"StandardOutput=append:{log_dir / 'check.log'}\n"
        f"StandardError=append:{log_dir / 'check-error.log'}\n"
    )
    timer_path.write_text(
        "[Unit]\n"
        "Description=skill-tracker daily check timer\n\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\n"
        "Persistent=true\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "skill-tracker-check.timer"], check=True)
    return timer_path


def _uninstall_linux() -> None:
    subprocess.run(["systemctl", "--user", "disable", "--now", "skill-tracker-check.timer"], capture_output=True)
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    for name in ("skill-tracker-check.service", "skill-tracker-check.timer"):
        p = systemd_dir / name
        if p.exists():
            p.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def install(executable: str, log_dir: Path, hour: int = 9, minute: int = 0) -> Path:
    """Install a scheduled job to run 'skill-tracker check' daily at the given time (default 09:00).
    Uses launchd on macOS and systemd on Linux."""
    system = platform.system()
    if system == "Darwin":
        return _install_macos(executable, log_dir, hour, minute)
    if system == "Linux":
        return _install_linux(executable, log_dir, hour, minute)
    raise NotImplementedError(f"Scheduling is not supported on {system}.")


def uninstall() -> None:
    system = platform.system()
    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        if plist_path.exists():
            plist_path.unlink()
    elif system == "Linux":
        _uninstall_linux()
    else:
        raise NotImplementedError(f"Scheduling is not supported on {system}.")
