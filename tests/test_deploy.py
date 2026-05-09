import json
import pytest
from pathlib import Path
from skill_tracker.deploy import deploy, wire_hooks, _dest_path, _load_settings
from skill_tracker.manifest import Skill, SkillFile, HookDeclaration


@pytest.fixture
def skill():
    return Skill(
        name="caveman",
        repo="JuliusBrussee/caveman",
        branch="main",
        files=[
            SkillFile(remote="skills/caveman/SKILL.md", type="skill"),
            SkillFile(remote="commands/caveman.toml", type="command"),
            SkillFile(remote="scripts/run.sh", type="script"),
        ],
    )


@pytest.fixture
def upstream(tmp_path, skill):
    base = tmp_path / "upstream" / skill.name
    for f in skill.files:
        dest = base / f.remote
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f"content of {f.remote}")
    return tmp_path / "upstream"


class TestDestPath:
    def test_skill_goes_to_skills_subdir(self, tmp_path):
        sf = SkillFile(remote="skills/caveman/SKILL.md", type="skill")
        dest = _dest_path(sf, tmp_path)
        assert dest == tmp_path / ".claude" / "skills" / "caveman" / "SKILL.md"

    def test_command_goes_to_commands(self, tmp_path):
        sf = SkillFile(remote="commands/caveman.toml", type="command")
        dest = _dest_path(sf, tmp_path)
        assert dest == tmp_path / ".claude" / "commands" / "caveman.toml"

    def test_script_goes_to_scripts(self, tmp_path):
        sf = SkillFile(remote="scripts/run.sh", type="script")
        dest = _dest_path(sf, tmp_path)
        assert dest == tmp_path / ".claude" / "scripts" / "run.sh"

    def test_agent_goes_to_agents(self, tmp_path):
        sf = SkillFile(remote="AGENT.md", type="agent")
        dest = _dest_path(sf, tmp_path)
        assert dest == tmp_path / ".claude" / "agents" / "AGENT.md"

    def test_other_goes_to_claude_root(self, tmp_path):
        sf = SkillFile(remote="some/file.txt", type="other")
        dest = _dest_path(sf, tmp_path)
        assert dest == tmp_path / ".claude" / "file.txt"


class TestDeploy:
    def test_files_are_copied(self, tmp_path, skill, upstream):
        target = tmp_path / "myproject"
        target.mkdir()
        deployed = deploy(skill, upstream, target)
        assert len(deployed) == 3

    def test_skill_lands_in_correct_dir(self, tmp_path, skill, upstream):
        target = tmp_path / "myproject"
        target.mkdir()
        deploy(skill, upstream, target)
        assert (target / ".claude" / "skills" / "caveman" / "SKILL.md").exists()

    def test_command_lands_in_correct_dir(self, tmp_path, skill, upstream):
        target = tmp_path / "myproject"
        target.mkdir()
        deploy(skill, upstream, target)
        assert (target / ".claude" / "commands" / "caveman.toml").exists()

    def test_script_is_executable(self, tmp_path, skill, upstream):
        target = tmp_path / "myproject"
        target.mkdir()
        deploy(skill, upstream, target)
        script = target / ".claude" / "scripts" / "run.sh"
        assert script.exists()
        assert script.stat().st_mode & 0o111

    def test_missing_source_raises(self, tmp_path, skill):
        empty_upstream = tmp_path / "empty_upstream"
        target = tmp_path / "myproject"
        target.mkdir()
        with pytest.raises(FileNotFoundError):
            deploy(skill, empty_upstream, target)

    def test_hook_lands_in_hooks_dir(self, tmp_path):
        skill = Skill(
            name="guardrails",
            repo="owner/repo",
            branch="main",
            files=[SkillFile(remote="scripts/block.sh", type="hook")],
        )
        src = tmp_path / "upstream" / "guardrails" / "scripts" / "block.sh"
        src.parent.mkdir(parents=True)
        src.write_text("#!/bin/sh")
        target = tmp_path / "myproject"
        target.mkdir()
        deploy(skill, tmp_path / "upstream", target)
        dest = target / ".claude" / "hooks" / "block.sh"
        assert dest.exists()
        assert dest.stat().st_mode & 0o111

    def test_symlink_source_raises(self, tmp_path, skill, upstream):
        target = tmp_path / "myproject"
        target.mkdir()
        # Replace the skill file with a symlink
        real_src = upstream / skill.name / skill.files[0].remote
        real_src.unlink()
        real_src.symlink_to("/etc/passwd")
        with pytest.raises(ValueError, match="symlink"):
            deploy(skill, upstream, target)

    def test_path_traversal_raises(self, tmp_path, monkeypatch):
        import skill_tracker.deploy as mod
        skill = Skill(
            name="evil",
            repo="owner/repo",
            branch="main",
            files=[SkillFile(remote="file.sh", type="script")],
        )
        src = tmp_path / "upstream" / "evil" / "file.sh"
        src.parent.mkdir(parents=True)
        src.write_text("bad")
        target = tmp_path / "myproject"
        target.mkdir()
        # Force _dest_path to return a path outside .claude/ to verify the guard catches it
        monkeypatch.setattr(mod, "_dest_path", lambda sf, t: tmp_path / "outside" / "evil.sh")
        with pytest.raises(ValueError, match="Unsafe path"):
            deploy(skill, tmp_path / "upstream", target)


class TestDestPath:
    def test_hook_goes_to_hooks(self, tmp_path):
        sf = SkillFile(remote="scripts/block.sh", type="hook")
        dest = _dest_path(sf, tmp_path)
        assert dest == tmp_path / ".claude" / "hooks" / "block.sh"


class TestLoadSettings:
    def test_missing_file_returns_empty(self, tmp_path):
        result = _load_settings(tmp_path / "nonexistent.json")
        assert result == {}

    def test_valid_settings_returned(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"hooks": {"PreToolUse": []}}))
        result = _load_settings(p)
        assert result == {"hooks": {"PreToolUse": []}}

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text("not json{{")
        assert _load_settings(p) == {}

    def test_non_dict_root_returns_empty(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text("[1, 2, 3]")
        assert _load_settings(p) == {}

    def test_non_dict_hooks_value_reset(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"hooks": "bad"}))
        result = _load_settings(p)
        assert result["hooks"] == {}

    def test_non_list_event_reset(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"hooks": {"PreToolUse": "bad"}}))
        result = _load_settings(p)
        assert result["hooks"]["PreToolUse"] == []


class TestWireHooks:
    def _skill_with_hook(self, command: str) -> Skill:
        return Skill(
            name="guardrails",
            repo="owner/repo",
            branch="main",
            files=[],
            hooks=[HookDeclaration(event="PreToolUse", matcher="Bash", command=command)],
        )

    def test_creates_settings_json(self, tmp_path):
        target = tmp_path / "myproject"
        target.mkdir()
        skill = self._skill_with_hook('"$CLAUDE_PROJECT_DIR"/.claude/hooks/block.sh')
        wire_hooks(skill, target)
        assert (target / ".claude" / "settings.json").exists()

    def test_hook_entry_written(self, tmp_path):
        target = tmp_path / "myproject"
        target.mkdir()
        cmd = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/block.sh'
        wire_hooks(self._skill_with_hook(cmd), target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        hooks = settings["hooks"]["PreToolUse"][0]["hooks"]
        assert {"type": "command", "command": cmd} in hooks

    def test_wire_hooks_is_idempotent(self, tmp_path):
        target = tmp_path / "myproject"
        target.mkdir()
        cmd = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/block.sh'
        skill = self._skill_with_hook(cmd)
        wire_hooks(skill, target)
        wire_hooks(skill, target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        hooks = settings["hooks"]["PreToolUse"][0]["hooks"]
        assert hooks.count({"type": "command", "command": cmd}) == 1

    def test_no_hooks_returns_empty(self, tmp_path):
        target = tmp_path / "myproject"
        target.mkdir()
        skill = Skill(name="x", repo="o/r", branch="main", files=[], hooks=[])
        result = wire_hooks(skill, target)
        assert result == []

    def test_preserves_existing_settings(self, tmp_path):
        target = tmp_path / "myproject"
        (target / ".claude").mkdir(parents=True)
        settings_path = target / ".claude" / "settings.json"
        settings_path.write_text(json.dumps({"model": "claude-opus"}))
        cmd = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/block.sh'
        wire_hooks(self._skill_with_hook(cmd), target)
        result = json.loads(settings_path.read_text())
        assert result["model"] == "claude-opus"
        assert "hooks" in result
