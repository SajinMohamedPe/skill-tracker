import pytest
from pathlib import Path
from skill_tracker.deploy import deploy, _dest_path
from skill_tracker.manifest import Skill, SkillFile


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
