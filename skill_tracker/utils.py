from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

# Normalises any GitHub URL format to owner/repo
def parse_github_url(url: str) -> str:
    """Return 'owner/repo' from any GitHub URL format."""
    url = url.strip().removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    parts = url.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Cannot parse GitHub repo from: {url!r}")
    return f"{parts[0]}/{parts[1]}"

# Infer the Claude file type from the remote path, based on filename conventions and extensions
def infer_type(remote_path: str) -> str:
    """Infer the Claude file type from the remote path."""
    name = Path(remote_path).name
    suffix = Path(remote_path).suffix.lower()
    if name == "SKILL.md":
        return "skill"
    if name.upper() in ("AGENT.MD", "AGENTS.MD"):
        return "agent"
    if suffix == ".toml":
        return "command"
    if suffix in (".sh", ".py", ".js", ".ts", ".rb"):
        return "script"
    return "other"

#Finds the skill-tracker root directory — checks SKILL_TRACKER_HOME env var first, then walks up from cwd looking for skills-manifest.json
def get_root() -> Path:
    """Find the skill-tracker root directory."""
    if home := os.environ.get("SKILL_TRACKER_HOME"):
        return Path(home)
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "skills-manifest.json").exists() or \
           (parent / "skills-manifest.json.template").exists():
            return parent
    return cwd

# Sends a macOS notification via osascript. Silent no-op if it fails or isn't on macOS
def notify(title: str, message: str) -> None:
    """Send a macOS notification. Silently does nothing on other platforms."""
    try:
        safe_msg = shlex.quote(message)
        safe_title = shlex.quote(title)
        script = f"display notification {safe_msg} with title {safe_title}"
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass
