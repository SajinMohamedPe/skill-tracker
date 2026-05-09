---
name: skill-tracker
description: >
  Manages third-party Claude Code skills sourced from GitHub. Add, check, update, and deploy
  skills to Claude Code projects. Triggers when user provides a GitHub URL to track as a skill,
  or asks to check/update/deploy tracked skills.
---

You manage Claude Code skills sourced from GitHub using the `skill-tracker` CLI.
The tracker stores sparse shallow clones in `upstream/` and tracks them via
`skills-manifest.json` and `skills.lock` (both gitignored — never reveal their contents).

## Adding a skill

When the user provides a GitHub URL and path(s):

**1. Parse the URL** — extract `owner/repo` from any form:
- `https://github.com/owner/repo`, `github.com/owner/repo`, `owner/repo`
- `https://github.com/owner/repo/tree/main/subdir` → repo is `owner/repo`, subdir hints at paths

**2. Determine a skill name** — use the skill directory name if a `SKILL.md` path is given
(e.g. `skills/caveman/SKILL.md` → name `caveman`). Otherwise use the repo name. Ask if ambiguous.

**3. Identify files to track** — the user may specify exact paths or describe what they want:
- `skills/<name>/SKILL.md` → type: skill
- `commands/<name>.toml` → type: command
- `*.sh`, `*.py`, `*.js` → type: script
- `*AGENT.md` → type: agent

**4. Run:**
```
skill-tracker add <name> <owner/repo> <path1> [path2 ...]
```

**5. Offer to deploy** — ask which project, then run:
```
skill-tracker deploy <name> <absolute-project-path>
```

## Checking skills

```
skill-tracker check
```
Summarise output. Flag deleted/moved files as security concerns — never suggest removing the local copy.

## Updating a skill

```
skill-tracker update <name>
```
The CLI shows the diff and prompts for confirmation in the terminal. If a tracked file is deleted
upstream the command aborts automatically — explain this to the user.

## Deploying a skill

```
skill-tracker deploy <name> <absolute-path-to-project>
```
Files land in `.claude/skills/`, `.claude/commands/`, or `.claude/scripts/` based on their type.
The target is registered in the manifest so future updates auto-redeploy.

## Listing tracked skills

```
skill-tracker list
```

## Scheduling background checks (macOS)

```
skill-tracker schedule          # install daily launchd job at 09:00
skill-tracker schedule --uninstall
```

## Rules

- Never print or summarise the contents of `skills-manifest.json` or `skills.lock`.
- Never suggest committing manifest or lockfile.
- Never auto-apply updates without user confirmation.
- If a tracked file is deleted upstream, treat it as a security signal.
