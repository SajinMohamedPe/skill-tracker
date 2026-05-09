import pytest
from skill_tracker.utils import parse_github_url, infer_type


class TestParseGithubUrl:
    def test_full_https_url(self):
        assert parse_github_url("https://github.com/owner/repo") == "owner/repo"

    def test_full_https_url_with_git_suffix(self):
        assert parse_github_url("https://github.com/owner/repo.git") == "owner/repo"

    def test_short_form(self):
        assert parse_github_url("owner/repo") == "owner/repo"

    def test_url_with_tree_path(self):
        assert parse_github_url("https://github.com/owner/repo/tree/main/subdir") == "owner/repo"

    def test_no_scheme(self):
        assert parse_github_url("github.com/owner/repo") == "owner/repo"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_github_url("notarepo")


class TestInferType:
    def test_skill_md(self):
        assert infer_type("skills/caveman/SKILL.md") == "skill"

    def test_toml_is_command(self):
        assert infer_type("commands/caveman.toml") == "command"

    def test_sh_is_script(self):
        assert infer_type("scripts/run.sh") == "script"

    def test_py_is_script(self):
        assert infer_type("scripts/compress.py") == "script"

    def test_js_is_script(self):
        assert infer_type("hooks/caveman.js") == "script"

    def test_agent_md(self):
        assert infer_type("AGENT.md") == "agent"

    def test_unknown_is_other(self):
        assert infer_type("some/random/file.txt") == "other"
