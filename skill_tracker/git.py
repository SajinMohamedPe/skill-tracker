from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommitInfo:
    sha: str
    author: str
    date: str
    message: str


def _run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)

# Detects the default branch of a remote Git repository by inspecting the HEAD reference
def detect_default_branch(clone_url: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", "--symref", clone_url, "HEAD"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("refs/heads/")[1].split("\t")[0]
    return "main"

# Performs a sparse clone of the specified paths from the given repository and branch
def sparse_clone(clone_url: str, dest: Path, paths: list[str], branch: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], cwd=dest)
    _run(["git", "remote", "add", "origin", clone_url], cwd=dest)
    _run(["git", "config", "core.sparseCheckout", "true"], cwd=dest)
    sparse_file = dest / ".git" / "info" / "sparse-checkout"
    sparse_file.write_text("\n".join(paths) + "\n")
    _run(["git", "fetch", "--depth=1", "origin", branch, "-q"], cwd=dest)
    _run(["git", "checkout", "-b", branch, "FETCH_HEAD", "-q"], cwd=dest)


def get_head_commit(repo_path: Path) -> CommitInfo:
    def log(fmt: str) -> str:
        return _run(["git", "log", "-1", f"--format={fmt}"], cwd=repo_path).stdout.strip()
    return CommitInfo(
        sha=_run(["git", "rev-parse", "HEAD"], cwd=repo_path).stdout.strip(),
        author=log("%an"),
        date=log("%ci"),
        message=log("%s"),
    )


def fetch(repo_path: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "fetch", "--depth=1", "origin", branch, "-q"],
        cwd=repo_path, capture_output=True,
    )
    return result.returncode == 0

# Returns the SHA of FETCH_HEAD after a successful fetch
def get_fetch_head_sha(repo_path: Path) -> str:
    return _run(["git", "rev-parse", "FETCH_HEAD"], cwd=repo_path).stdout.strip()

# Checks if a file exists at a specific ref (commit or branch)
def file_exists_at_ref(repo_path: Path, ref: str, file_path: str) -> bool:
    result = subprocess.run(
        ["git", "show", f"{ref}:{file_path}"],
        cwd=repo_path, capture_output=True,
    )
    return result.returncode == 0

# Returns the diff of a file between two refs (e.g., commits or branches)
def get_diff(repo_path: Path, base: str, head: str, file_path: str) -> str:
    return subprocess.run(
        ["git", "diff", f"{base}..{head}", "--", file_path],
        cwd=repo_path, capture_output=True, text=True,
    ).stdout

# Returns a list of commits between two refs (e.g., commits or branches)
def get_new_commits(repo_path: Path, base: str, head: str) -> list[CommitInfo]:
    result = subprocess.run(
        ["git", "log", f"{base}..{head}", "--format=%H\t%an\t%ci\t%s"],
        cwd=repo_path, capture_output=True, text=True,
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            sha, author, date, message = line.split("\t", 3)
            commits.append(CommitInfo(sha=sha, author=author, date=date, message=message))
    return commits

# Resets the current branch to FETCH_HEAD, discarding any local changes
def apply_update(repo_path: Path) -> None:
    _run(["git", "reset", "--hard", "FETCH_HEAD", "-q"], cwd=repo_path)
