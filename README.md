# skill-tracker

Track and manage third-party Claude Code skills sourced from GitHub. Detects upstream updates, flags deleted files as security signals, and deploys skills to any number of Claude Code projects.

## Why

Claude Code skills are just files — `SKILL.md`, `.toml` commands, scripts. Most people copy them manually with no way to know when the original author pushes a fix or, more importantly, removes a file entirely (a common signal that something is wrong upstream).

skill-tracker solves this with:
- **Sparse shallow clones** — pulls only the exact files you care about, not whole repos
- **Lockfile pinning** — records the commit SHA you're on, like `package-lock.json`
- **Change detection** — compares your pinned SHA against upstream on every check
- **Security alerts** — if a tracked file disappears upstream, it flags it and refuses to auto-update
- **Multi-project deployment** — register a skill once, deploy to many projects, auto-redeploy on update

## Installation

Requires Python 3.10+ and `git`.

```bash
git clone https://github.com/SajinMohamedPe/skill-tracker
cd skill-tracker
pip install -e .
```

For a development install with test dependencies:

```bash
pip install -e ".[dev]"
```

## Setup

```bash
cp skills-manifest.json.template skills-manifest.json
cp skills.lock.template skills.lock
```

These two files are gitignored — they stay private so no one can infer which skills you're tracking or which versions you're pinned to.

### Setting your root directory

skill-tracker locates your manifest by walking up from your current directory. To use it from anywhere without needing to `cd` into the project first, add this to your `~/.zshrc`:

```bash
export SKILL_TRACKER_HOME=>/path/to/skill-tracker
```

Then reload your shell:

```bash
source ~/.zshrc
```

Without this, you must run all `skill-tracker` commands from inside the project directory.

## Usage

### Add a skill

```bash
skill-tracker add <name> <owner/repo> <path> [path ...]
```

Example:

```bash
skill-tracker add caveman JuliusBrussee/caveman \
  skills/caveman/SKILL.md \
  commands/caveman.toml \
  commands/caveman-commit.toml \
  commands/caveman-review.toml
```

Accepts any GitHub URL format: `owner/repo`, `https://github.com/owner/repo`, or a full tree URL. File types are inferred automatically:

| File | Inferred type |
|------|--------------|
| `SKILL.md` | skill |
| `*.toml` | command |
| `AGENT.md` | agent |
| `*.sh`, `*.py`, `*.js` | script |

Use `--branch` to track a specific branch instead of the repo default.

### Deploy to a project

```bash
skill-tracker deploy caveman /path/to/my-project
```

Files land in the correct subdirectory of the target project's `.claude/`:

| Type | Destination |
|------|------------|
| skill | `.claude/skills/<name>/` |
| command | `.claude/commands/` |
| agent | `.claude/agents/` |
| script | `.claude/scripts/` |

The project is registered in the manifest. Future `skill-tracker update` calls automatically re-deploy there.

### Check for updates

```bash
skill-tracker check
```

For each tracked skill:
- **Up to date** — no action needed
- **Update available** — shows commit author, message, and a diff of your tracked files
- **File deleted or moved upstream** — flagged as a security signal; your local copy is left intact

Exit code `0` if all skills are up to date, `1` if any action is needed — useful in CI.

### Apply an update

```bash
skill-tracker update caveman
```

Shows the full diff and prompts for confirmation before applying. If any tracked file has been deleted upstream, the command aborts without touching your local copy. Use `--yes` to skip the confirmation prompt in scripted contexts.

### List tracked skills

```bash
skill-tracker list
```

Shows a table of all tracked skills, their pinned commit, when they were last locked, and which projects they are deployed to.

### Schedule daily background checks (macOS)

```bash
skill-tracker schedule
```

Installs a launchd job that runs `skill-tracker check` every day at 09:00 and sends a macOS notification if any skill has updates or security alerts. Logs are written to `logs/check.log`.

```bash
skill-tracker schedule --uninstall   # remove the job
```

## Project structure

```
skill-tracker/
├── skill_tracker/
│   ├── cli.py          ← entry point
│   ├── manifest.py     ← Manifest + LockFile dataclasses
│   ├── git.py          ← sparse clone, fetch, diff, apply
│   ├── deploy.py       ← file routing to .claude/ subdirectories
│   ├── sanitise.py     ← prompt injection defence for all upstream content
│   ├── schedule.py     ← macOS launchd install/uninstall
│   └── utils.py        ← URL parser, type inferrer, notifier
├── .claude/
│   ├── skills/skill-tracker/SKILL.md   ← interactive Claude skill
│   └── commands/                        ← /skill-add, /skill-check, /skill-update, /skill-deploy
├── tests/
├── pyproject.toml
├── skills-manifest.json.template
└── skills.lock.template
```

## Using with Claude Code

Open Claude Code in this project directory and the skill-tracker skill is available. You can manage skills interactively:

- `/skill-add https://github.com/owner/repo path/to/SKILL.md` — Claude parses the URL, confirms the paths, runs the add, and asks where to deploy
- `/skill-check` — runs a check and summarises results
- `/skill-update <name>` — walks you through reviewing and applying an update
- `/skill-deploy <name> <project-path>` — deploys to a target project

## Running tests

```bash
pytest
```

56 tests covering manifest read/write, file routing, URL parsing, type inference, and prompt injection sanitisation.

## Security model

- `skills-manifest.json` and `skills.lock` are gitignored — your dependency list and version pins are private
- Updates are never applied automatically — every change requires explicit confirmation with a diff
- If a tracked file disappears from upstream, `check` and `update` both refuse to proceed and flag it prominently
- `upstream/` directories are gitignored — the sparse clones are local only

### Prompt injection protection

All untrusted content from upstream passes through `sanitise.py` before being displayed. This matters because skill-tracker output is often read by Claude Code, making commit messages and file diffs a potential injection vector.

Three layers of protection:

**Rich markup escaping** — all upstream text has `[` escaped to `\[` before being passed to the terminal renderer, preventing console injection via crafted markup. This applies to commit messages, author names, file paths, and skill metadata from the manifest.

**Injection pattern detection** — commit messages and author names are scanned against patterns like `ignore previous instructions`, `you are now`, `SYSTEM:`, `<system>`, `[INST]`, and similar. Matching content is replaced with a visible redaction warning rather than silently dropped.

**Diff sanitisation** — only added lines (`+`) in a diff are scanned, since removed lines are your own previous content. If a suspicious pattern is found on an added line, that line is redacted individually rather than the entire diff.

**Prompt file warning** — when a diff touches a `.md` file (which is itself a prompt — `SKILL.md`, `AGENT.md`), a warning is shown before the diff so you know you are reviewing a change to instructions that Claude will follow.

The test suite in `tests/test_sanitise.py` covers all patterns and edge cases.

### Deploy-time safety

**Symlink rejection** — before copying any upstream file, skill-tracker checks whether it is a symlink. A compromised upstream repository could plant a symlink pointing to a sensitive system file to exfiltrate its contents into your project. Any symlink found during deploy raises an error and aborts immediately.

**Path traversal prevention** — all destination paths are resolved and verified to remain inside the target project's `.claude/` directory before any file is written. A crafted remote path like `../../.bashrc` is rejected outright.

### Notification safety

macOS notifications triggered by skill-tracker (update available, security alerts) use `shlex.quote()` to escape skill names and messages before passing them to `osascript`, preventing an upstream-controlled commit message from injecting arbitrary AppleScript.

### Schedule file safety

The macOS launchd plist is generated using `xml.etree.ElementTree` rather than string interpolation, ensuring that special characters in the executable path (`&`, `<`, `>`) cannot break the XML structure or inject malicious plist entries.
