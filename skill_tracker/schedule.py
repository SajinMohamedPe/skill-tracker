from __future__ import annotations

import subprocess
from pathlib import Path

_LABEL = "com.skill-tracker.check"


def install(executable: str, log_dir: Path) -> Path:
    """Install a launchd job to run 'skill-tracker check' daily at 09:00."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist_path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{executable}</string>
        <string>check</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir / "check.log"}</string>
    <key>StandardErrorPath</key>
    <string>{log_dir / "check-error.log"}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
""")
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def uninstall() -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    if plist_path.exists():
        plist_path.unlink()
