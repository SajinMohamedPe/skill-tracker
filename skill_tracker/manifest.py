from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillFile:
    remote: str
    type: str  # skill | command | script | agent | other


@dataclass
class HookDeclaration:
    event: str    # e.g. "PreToolUse"
    matcher: str  # e.g. "Bash"
    command: str  # e.g. '"$CLAUDE_PROJECT_DIR"/.claude/scripts/block-dangerous-git.sh'


@dataclass
class Skill:
    name: str
    repo: str
    branch: str
    files: list[SkillFile]
    deployed_to: list[str] = field(default_factory=list)
    hooks: list[HookDeclaration] = field(default_factory=list)


@dataclass
class LockEntry:
    repo: str
    commit: str
    committed_by: str
    committed_at: str
    locked_at: str


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._skills: dict[str, Skill] = {}
        if path.exists():
            self._load()

    # Loads the manifest from disk, populating the _skills dictionary with Skill objects based on the JSON data
    def _load(self) -> None:
        data = json.loads(self.path.read_text())
        for s in data.get("skills", []):
            skill = Skill(
                name=s["name"],
                repo=s["repo"],
                branch=s["branch"],
                files=[SkillFile(**f) for f in s.get("files", [])],
                deployed_to=s.get("deployed_to", []),
                hooks=[HookDeclaration(**h) for h in s.get("hooks", [])],
            )
            self._skills[skill.name] = skill

    # Saves the manifest to disk in a pretty-printed JSON format
    def save(self) -> None:
        data = {
            "skills": [
                {
                    "name": s.name,
                    "repo": s.repo,
                    "branch": s.branch,
                    "files": [{"remote": f.remote, "type": f.type} for f in s.files],
                    "deployed_to": s.deployed_to,
                    "hooks": [{"event": h.event, "matcher": h.matcher, "command": h.command} for h in s.hooks],
                }
                for s in self._skills.values()
            ]
        }
        self.path.write_text(json.dumps(data, indent=2) + "\n")
        self.path.chmod(0o600)

    # Returns the Skill with the given name, or None if it doesn't exist in the manifest
    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    # Returns a list of all skills in the manifest
    def all(self) -> list[Skill]:
        return list(self._skills.values())
    
    # Checks if a skill with the given name exists in the manifest
    def exists(self, name: str) -> bool:
        return name in self._skills

    # Adds a new skill to the manifest, ensuring no duplicate names, and saves the manifest
    def add(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' already exists")
        self._skills[skill.name] = skill
        self.save()

    # Removes a skill from the manifest by name and saves
    def remove(self, name: str) -> None:
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found")
        del self._skills[name]
        self.save()

    # Registers a deployment of a skill to a target (e.g., project name), updates the manifest, and saves it
    def register_deployment(self, name: str, target: str) -> None:
        skill = self._skills[name]
        if target not in skill.deployed_to:
            skill.deployed_to.append(target)
            self.save()


class LockFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        if path.exists():
            self._data = json.loads(path.read_text())

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2) + "\n")
        self.path.chmod(0o600)

    def update(self, name: str, entry: LockEntry) -> None:
        self._data[name] = {
            "repo": entry.repo,
            "commit": entry.commit,
            "committed_by": entry.committed_by,
            "committed_at": entry.committed_at,
            "locked_at": entry.locked_at,
        }
        self.save()

    def get(self, name: str) -> LockEntry | None:
        if d := self._data.get(name):
            return LockEntry(**d)
        return None

    # Removes the lock entry for a skill by name and saves
    def remove(self, name: str) -> None:
        self._data.pop(name, None)
        self.save()
