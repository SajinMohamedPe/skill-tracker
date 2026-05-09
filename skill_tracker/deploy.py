from __future__ import annotations

import json
import shutil
from pathlib import Path

from .manifest import Skill, SkillFile

# Deploy a skill's files to a target directory, returning a list of (source, destination) paths.
def deploy(skill: Skill, upstream_dir: Path, target: Path) -> list[tuple[str, Path]]:
    """Copy tracked skill files into the target project's .claude/ directory."""
    deployed = []
    for skill_file in skill.files:
        src = upstream_dir / skill.name / skill_file.remote
        if not src.exists():
            raise FileNotFoundError(
                f"Source not found: {src}\nRun 'skill-tracker check' to verify upstream state."
            )
        dest = _dest_path(skill_file, target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if skill_file.type in ("script", "hook"):
            dest.chmod(dest.stat().st_mode | 0o111)
        deployed.append((skill_file.remote, dest))
    return deployed

# Loads and validates settings.json, returning a safe dict. Returns {} on missing/malformed file.
def _load_settings(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    try:
        data = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        data["hooks"] = {}
    else:
        for event, matchers in list(hooks.items()):
            if not isinstance(matchers, list):
                hooks[event] = []
            else:
                hooks[event] = [m for m in matchers if isinstance(m, dict)]
    return data


# Merges skill's hook declarations into target/.claude/settings.json. Returns list of commands added.
def wire_hooks(skill: Skill, target: Path) -> list[str]:
    if not skill.hooks:
        return []
    settings_path = target / ".claude" / "settings.json"
    settings = _load_settings(settings_path)
    settings.setdefault("hooks", {})
    added = []
    for h in skill.hooks:
        matchers = settings["hooks"].setdefault(h.event, [])
        block = next((m for m in matchers if m.get("matcher") == h.matcher), None)
        if block is None:
            block = {"matcher": h.matcher, "hooks": []}
            matchers.append(block)
        entry = {"type": "command", "command": h.command}
        if entry not in block["hooks"]:
            block["hooks"].append(entry)
            added.append(h.command)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return added


# Determines the destination path for a skill file based on its type and remote path
def _dest_path(skill_file: SkillFile, target: Path) -> Path:
    remote = Path(skill_file.remote)
    filename = remote.name
    match skill_file.type:
        case "skill":
            # Preserve the skill's subdirectory name (e.g. skills/caveman/SKILL.md → .claude/skills/caveman/)
            skill_subdir = remote.parent.name
            dest = target / ".claude" / "skills" / skill_subdir / filename
        case "command":
            dest = target / ".claude" / "commands" / filename
        case "script":
            dest = target / ".claude" / "scripts" / filename
        case "hook":
            dest = target / ".claude" / "hooks" / filename
        case "agent":
            dest = target / ".claude" / "agents" / filename
        case _:
            dest = target / ".claude" / filename

    resolved = dest.resolve()
    allowed = (target / ".claude").resolve()
    if not resolved.is_relative_to(allowed):
        raise ValueError(
            f"Unsafe path detected: '{skill_file.remote}' resolves outside .claude/ — aborting."
        )
    return dest
