import json
import pytest
from pathlib import Path
from skill_tracker.manifest import Manifest, LockFile, Skill, SkillFile, LockEntry


@pytest.fixture
def tmp_manifest(tmp_path):
    return Manifest(tmp_path / "skills-manifest.json")


@pytest.fixture
def tmp_lockfile(tmp_path):
    return LockFile(tmp_path / "skills.lock")


@pytest.fixture
def sample_skill():
    return Skill(
        name="caveman",
        repo="JuliusBrussee/caveman",
        branch="main",
        files=[
            SkillFile(remote="skills/caveman/SKILL.md", type="skill"),
            SkillFile(remote="commands/caveman.toml", type="command"),
        ],
    )


class TestManifest:
    def test_empty_on_init(self, tmp_manifest):
        assert tmp_manifest.all() == []

    def test_add_and_get(self, tmp_manifest, sample_skill):
        tmp_manifest.add(sample_skill)
        result = tmp_manifest.get("caveman")
        assert result is not None
        assert result.name == "caveman"
        assert result.repo == "JuliusBrussee/caveman"

    def test_add_duplicate_raises(self, tmp_manifest, sample_skill):
        tmp_manifest.add(sample_skill)
        with pytest.raises(ValueError, match="already exists"):
            tmp_manifest.add(sample_skill)

    def test_exists(self, tmp_manifest, sample_skill):
        assert not tmp_manifest.exists("caveman")
        tmp_manifest.add(sample_skill)
        assert tmp_manifest.exists("caveman")

    def test_get_unknown_returns_none(self, tmp_manifest):
        assert tmp_manifest.get("nope") is None

    def test_save_and_reload(self, tmp_path, sample_skill):
        path = tmp_path / "skills-manifest.json"
        m1 = Manifest(path)
        m1.add(sample_skill)

        m2 = Manifest(path)
        skill = m2.get("caveman")
        assert skill is not None
        assert len(skill.files) == 2
        assert skill.files[0].type == "skill"

    def test_register_deployment(self, tmp_manifest, sample_skill):
        tmp_manifest.add(sample_skill)
        tmp_manifest.register_deployment("caveman", "/some/project")
        skill = tmp_manifest.get("caveman")
        assert "/some/project" in skill.deployed_to

    def test_register_deployment_no_duplicate(self, tmp_manifest, sample_skill):
        tmp_manifest.add(sample_skill)
        tmp_manifest.register_deployment("caveman", "/some/project")
        tmp_manifest.register_deployment("caveman", "/some/project")
        assert tmp_manifest.get("caveman").deployed_to.count("/some/project") == 1


class TestLockFile:
    def test_empty_on_init(self, tmp_lockfile):
        assert tmp_lockfile.get("anything") is None

    def test_update_and_get(self, tmp_lockfile):
        entry = LockEntry(
            repo="owner/repo",
            commit="abc123",
            committed_by="Alice",
            committed_at="2026-01-01",
            locked_at="2026-05-09T00:00:00+00:00",
        )
        tmp_lockfile.update("myskill", entry)
        result = tmp_lockfile.get("myskill")
        assert result is not None
        assert result.commit == "abc123"
        assert result.committed_by == "Alice"

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "skills.lock"
        lf1 = LockFile(path)
        lf1.update("s", LockEntry("r", "sha1", "Bob", "2026-01-01", "2026-05-09"))

        lf2 = LockFile(path)
        assert lf2.get("s").commit == "sha1"
