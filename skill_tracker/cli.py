from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import deploy, git, sanitise, schedule
from .manifest import HookDeclaration, LockEntry, LockFile, Manifest, Skill, SkillFile
from .utils import get_root, infer_type, notify, parse_github_url

out = Console()
err = Console(stderr=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace, root: Path) -> None:
    manifest = Manifest(root / "skills-manifest.json")
    lockfile = LockFile(root / "skills.lock")

    try:
        repo = parse_github_url(args.repo)
    except ValueError as e:
        err.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if manifest.exists(args.name):
        err.print(f"[red]Error:[/red] skill '{args.name}' already exists. Use 'update' to update it.")
        sys.exit(1)

    upstream = root / "upstream" / args.name
    if upstream.exists():
        err.print(f"[red]Error:[/red] upstream directory already exists: {upstream}")
        sys.exit(1)

    clone_url = f"https://github.com/{repo}.git"

    out.print(f"[bold]Detecting default branch for {repo}...[/bold]")
    branch = args.branch or git.detect_default_branch(clone_url)
    out.print(f"  Branch: {branch}")

    out.print(f"[bold]Cloning (sparse, depth=1)...[/bold]")
    try:
        git.sparse_clone(clone_url, upstream, args.paths, branch)
    except Exception as e:
        err.print(f"[red]Clone failed:[/red] {e}")
        sys.exit(1)

    missing = [p for p in args.paths if not (upstream / p).exists()]
    if missing:
        out.print(f"[yellow]Warning — paths not found in repo:[/yellow]")
        for m in missing:
            out.print(f"  • {m}")

    commit = git.get_head_commit(upstream)

    skill_files = [SkillFile(remote=p, type=infer_type(p)) for p in args.paths]
    hook_declarations = []
    for i, sf in enumerate(skill_files):
        if sf.type == "script":
            script_name = Path(sf.remote).name
            try:
                answer = input(f"Wire '{script_name}' as a PreToolUse/Bash hook? [y/N] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                answer = ""
            if answer == "y":
                skill_files[i] = SkillFile(remote=sf.remote, type="hook")
                hook_declarations.append(HookDeclaration(
                    event="PreToolUse",
                    matcher="Bash",
                    command=f'"$CLAUDE_PROJECT_DIR"/.claude/hooks/{script_name}',
                ))

    skill = Skill(
        name=args.name,
        repo=repo,
        branch=branch,
        files=skill_files,
        hooks=hook_declarations,
    )
    manifest.add(skill)
    lockfile.update(
        args.name,
        LockEntry(
            repo=repo,
            commit=commit.sha,
            committed_by=commit.author,
            committed_at=commit.date,
            locked_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    safe = sanitise.sanitise_commit(commit)
    out.print(f"\n[green]✓ Skill '{args.name}' added[/green]")
    out.print(f"  Repo:   {repo}")
    out.print(f"  Commit: {commit.sha[:12]}  {safe.author}  {safe.message}")
    out.print(f"  Files:")
    for f in skill.files:
        out.print(f"    • [{f.type}] {f.remote}")
    out.print(f"\n  To deploy: skill-tracker deploy {args.name} /path/to/project")


def cmd_check(args: argparse.Namespace, root: Path) -> None:
    manifest = Manifest(root / "skills-manifest.json")
    skills = manifest.all()

    if not skills:
        out.print("No skills tracked yet. Use 'skill-tracker add' to add one.")
        return

    upstream_dir = root / "upstream"
    updates_found = False

    out.print(f"[bold]Checking {len(skills)} skill(s)...[/bold]\n")

    for skill in skills:
        upstream = upstream_dir / skill.name
        sname = sanitise.sanitise_text(skill.name)
        srepo = sanitise.sanitise_text(skill.repo)

        if not (upstream / ".git").exists():
            out.print(f"  [yellow]⚠ {sname}[/yellow]: upstream missing — re-add with 'skill-tracker add'")
            updates_found = True
            continue

        if not git.fetch(upstream, skill.branch):
            out.print(f"  [red]✖ {sname}[/red] ({srepo}): FETCH FAILED")
            out.print(f"    [red]Repo may be deleted, renamed, or made private.[/red]")
            out.print(f"    Local copy intact — do not remove until you confirm the reason.")
            notify("Skill Tracker", f"{skill.name}: upstream repo unreachable")
            updates_found = True
            continue

        local_sha = git.get_head_commit(upstream).sha
        remote_sha = git.get_fetch_head_sha(upstream)

        if local_sha == remote_sha:
            out.print(f"  [green]✓ {sname}[/green]: up to date")
            continue

        deleted = [f.remote for f in skill.files if not git.file_exists_at_ref(upstream, "FETCH_HEAD", f.remote)]
        changed = [
            f.remote for f in skill.files
            if f.remote not in deleted and git.get_diff(upstream, "HEAD", "FETCH_HEAD", f.remote).strip()
        ]

        if deleted:
            updates_found = True
            out.print(f"  [red bold]✖ {sname}[/red bold]: TRACKED FILE(S) DELETED OR MOVED UPSTREAM")
            for d in deleted:
                out.print(f"    [red]• {sanitise.sanitise_text(d)}[/red]")
            out.print(f"    [yellow]Security: review upstream before updating. Local copy is intact.[/yellow]")
            notify("Skill Tracker — SECURITY", f"{skill.name}: tracked file deleted upstream")

        if changed:
            updates_found = True
            commits = git.get_new_commits(upstream, "HEAD", "FETCH_HEAD")
            out.print(f"  [yellow]⬆ {sname}[/yellow]: update available ({len(commits)} commit(s))")
            for c in commits:
                safe = sanitise.sanitise_commit(c)
                out.print(f"    {c.sha[:8]}  {safe.author} — {safe.message}")
            out.print(f"    Changed: {', '.join(sanitise.sanitise_text(f) for f in changed)}")
            out.print(f"    Run: [bold]skill-tracker update {sname}[/bold]")
            notify("Skill Tracker", f"{skill.name} has updates available")

        if not changed and not deleted:
            out.print(f"  [green]✓ {sname}[/green]: up to date (upstream has unrelated commits)")

    out.print()
    if not updates_found:
        out.print("[green]All skills up to date.[/green]")

    sys.exit(1 if updates_found else 0)


def cmd_update(args: argparse.Namespace, root: Path) -> None:
    manifest = Manifest(root / "skills-manifest.json")
    lockfile = LockFile(root / "skills.lock")

    skill = manifest.get(args.name)
    if not skill:
        err.print(f"[red]Error:[/red] skill '{args.name}' not found.")
        sys.exit(1)

    upstream = root / "upstream" / skill.name

    if not git.fetch(upstream, skill.branch):
        err.print("[red]Error:[/red] fetch failed — repo may be unreachable.")
        sys.exit(1)

    local_sha = git.get_head_commit(upstream).sha
    remote_sha = git.get_fetch_head_sha(upstream)

    sname = sanitise.sanitise_text(skill.name)

    if local_sha == remote_sha:
        out.print(f"[green]✓ {sname}[/green] is already up to date.")
        return

    deleted = [f.remote for f in skill.files if not git.file_exists_at_ref(upstream, "FETCH_HEAD", f.remote)]
    if deleted:
        err.print(f"[red bold]Aborting:[/red bold] tracked file(s) deleted upstream:")
        for d in deleted:
            err.print(f"  • {sanitise.sanitise_text(d)}")
        err.print("[yellow]Review upstream changes manually before updating.[/yellow]")
        sys.exit(1)

    commits = git.get_new_commits(upstream, "HEAD", "FETCH_HEAD")
    out.print(f"[bold]Incoming commits for {sname}:[/bold]")
    for c in commits:
        safe = sanitise.sanitise_commit(c)
        out.print(f"  {c.sha[:8]}  {safe.author}  {c.date[:10]}  {safe.message}")
    out.print()

    has_diff = False
    for f in skill.files:
        diff = git.get_diff(upstream, "HEAD", "FETCH_HEAD", f.remote)
        if diff.strip():
            has_diff = True
            safe_diff, is_prompt_file = sanitise.sanitise_diff(diff, f.remote)
            out.print(f"[bold]--- {sanitise.sanitise_text(f.remote)} ---[/bold]")
            if is_prompt_file:
                out.print("[yellow]⚠ This file is a prompt/skill — review carefully before applying.[/yellow]")
            out.print(safe_diff)

    if not has_diff:
        out.print("[dim]No changes to tracked files.[/dim]")

    if not args.yes:
        try:
            confirm = input("\nApply update? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            out.print("\nAborted.")
            sys.exit(0)
        if confirm != "y":
            out.print("Aborted.")
            sys.exit(0)

    git.apply_update(upstream)
    commit = git.get_head_commit(upstream)

    lockfile.update(
        skill.name,
        LockEntry(
            repo=skill.repo,
            commit=commit.sha,
            committed_by=commit.author,
            committed_at=commit.date,
            locked_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    out.print(f"\n[green]✓ {sname} updated to {commit.sha[:12]}[/green]")

    if skill.deployed_to:
        out.print("\nRe-deploying to registered targets:")
        for target_str in skill.deployed_to:
            target = Path(target_str)
            if not target.exists():
                out.print(f"  [yellow]⚠ Skipping {target} — directory not found[/yellow]")
                continue
            deployed = deploy.deploy(skill, root / "upstream", target)
            for remote, dest in deployed:
                out.print(f"  [green]✓[/green] {remote} → {dest}")
            deploy.wire_hooks(skill, target)


def cmd_deploy(args: argparse.Namespace, root: Path) -> None:
    manifest = Manifest(root / "skills-manifest.json")

    skill = manifest.get(args.name)
    if not skill:
        err.print(f"[red]Error:[/red] skill '{args.name}' not found.")
        sys.exit(1)

    target = Path(args.project).resolve()
    if not target.exists():
        err.print(f"[red]Error:[/red] target project '{target}' does not exist.")
        sys.exit(1)

    out.print(f"[bold]Deploying {sanitise.sanitise_text(skill.name)} → {target}[/bold]")
    try:
        deployed = deploy.deploy(skill, root / "upstream", target)
    except (FileNotFoundError, ValueError) as e:
        err.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    for remote, dest in deployed:
        out.print(f"  [green]✓[/green] {sanitise.sanitise_text(remote)} → {dest}")

    wired = deploy.wire_hooks(skill, target)
    for cmd in wired:
        out.print(f"  [green]✓[/green] Hook wired: {cmd}")

    manifest.register_deployment(skill.name, str(target))
    out.print(f"\n[green]✓ Done[/green] — restart Claude Code in the target project to activate.")


def _remove_deployed_files(skill, root: Path) -> None:
    """Delete deployed skill files and clean up settings.json hooks from each target project."""
    import json as _json
    import shutil as _shutil

    script_names = {Path(f.remote).name for f in skill.files if f.type in ("script", "hook")}

    for target_str in skill.deployed_to:
        target = Path(target_str)
        claude_dir = target / ".claude"

        # Remove skill directory
        for f in skill.files:
            dest = deploy._dest_path(f, target)
            try:
                dest.unlink()
                out.print(f"  [green]✓[/green] Removed {dest.relative_to(target)}")
            except FileNotFoundError:
                pass
            # Remove parent dir if empty
            try:
                dest.parent.rmdir()
            except OSError:
                pass

        # Scrub hook entries from settings.json that reference any of this skill's scripts
        settings_path = claude_dir / "settings.json"
        if settings_path.exists() and script_names:
            try:
                settings = deploy._load_settings(settings_path)
                hooks_changed = False
                for event, matchers in list(settings.get("hooks", {}).items()):
                    new_matchers = []
                    for matcher_block in matchers:
                        new_hooks = [
                            h for h in matcher_block.get("hooks", [])
                            if not any(name in h.get("command", "") for name in script_names)
                        ]
                        if len(new_hooks) != len(matcher_block.get("hooks", [])):
                            hooks_changed = True
                        if new_hooks:
                            new_matchers.append({**matcher_block, "hooks": new_hooks})
                        else:
                            hooks_changed = True
                    if new_matchers:
                        settings["hooks"][event] = new_matchers
                    else:
                        del settings["hooks"][event]
                        hooks_changed = True
                if not settings.get("hooks"):
                    settings.pop("hooks", None)
                if hooks_changed:
                    settings_path.write_text(_json.dumps(settings, indent=2) + "\n")
                    out.print(f"  [green]✓[/green] Cleaned hook entries from {settings_path.relative_to(target)}")
            except Exception as e:
                out.print(f"  [yellow]⚠ Could not update {settings_path}: {e}[/yellow]")


def cmd_remove(args: argparse.Namespace, root: Path) -> None:
    manifest = Manifest(root / "skills-manifest.json")
    lockfile = LockFile(root / "skills.lock")

    skill = manifest.get(args.name)
    if not skill:
        err.print(f"[red]Error:[/red] skill '{args.name}' not found.")
        sys.exit(1)

    if skill.deployed_to and not args.yes:
        out.print(f"[yellow]This skill is deployed to:[/yellow]")
        for t in skill.deployed_to:
            out.print(f"  • {t}")
        try:
            confirm = input(f"\nRemove '{args.name}' and all deployed files? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            out.print("\nAborted.")
            sys.exit(0)
        if confirm != "y":
            out.print("Aborted.")
            sys.exit(0)

    import shutil
    upstream = root / "upstream" / args.name
    if upstream.exists():
        shutil.rmtree(upstream)
        out.print(f"  [green]✓[/green] Deleted upstream clone: {upstream}")

    if skill.deployed_to:
        _remove_deployed_files(skill, root)

    manifest.remove(args.name)
    lockfile.remove(args.name)
    out.print(f"[green]✓ '{args.name}' removed.[/green]")


def cmd_list(args: argparse.Namespace, root: Path) -> None:
    manifest = Manifest(root / "skills-manifest.json")
    lockfile = LockFile(root / "skills.lock")
    skills = manifest.all()

    if not skills:
        out.print("No skills tracked. Use 'skill-tracker add' to add one.")
        return

    table = Table(title="Tracked Skills", show_lines=True)
    table.add_column("Name", style="bold cyan")
    table.add_column("Repo")
    table.add_column("Branch")
    table.add_column("Commit", style="dim")
    table.add_column("Locked At", style="dim")
    table.add_column("Deployed To")

    for skill in skills:
        lock = lockfile.get(skill.name)
        commit = lock.commit[:12] if lock else "—"
        locked_at = lock.locked_at[:10] if lock else "—"
        targets = "\n".join(Path(t).name for t in skill.deployed_to) or "—"
        table.add_row(skill.name, skill.repo, skill.branch, commit, locked_at, targets)

    out.print(table)


def cmd_schedule(args: argparse.Namespace, root: Path) -> None:
    if args.uninstall:
        schedule.uninstall()
        out.print("[green]✓ Scheduled job removed.[/green]")
        return

    import shutil
    executable = shutil.which("skill-tracker")
    if not executable:
        err.print("[red]Error:[/red] 'skill-tracker' not found in PATH. Install with 'pip install -e .' first.")
        sys.exit(1)

    try:
        hour, minute = (int(p) for p in args.time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        err.print("[red]Error:[/red] --time must be HH:MM (e.g. 09:00)")
        sys.exit(1)

    plist = schedule.install(executable, root / "logs", hour=hour, minute=minute)
    out.print(f"[green]✓ Scheduled job installed[/green] (daily at {hour:02d}:{minute:02d})")
    out.print(f"  Plist: {plist}")
    out.print(f"  Log:   {root / 'logs' / 'check.log'}")
    out.print(f"\n  To run now: launchctl start com.skill-tracker.check")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="skill-tracker",
        description="Track and manage third-party Claude Code skills from GitHub.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a skill from GitHub")
    p_add.add_argument("name", help="Local name for the skill")
    p_add.add_argument("repo", help="GitHub repo (owner/repo or full URL)")
    p_add.add_argument("paths", nargs="+", metavar="path", help="File paths within the repo to track")
    p_add.add_argument("--branch", help="Branch to track (default: auto-detect)")

    sub.add_parser("check", help="Check all skills for upstream changes")

    p_update = sub.add_parser("update", help="Update a tracked skill to the latest upstream version")
    p_update.add_argument("name", help="Skill name")
    p_update.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    p_deploy = sub.add_parser("deploy", help="Deploy a skill to a Claude Code project")
    p_deploy.add_argument("name", help="Skill name")
    p_deploy.add_argument("project", help="Path to the target Claude Code project")

    sub.add_parser("list", help="List all tracked skills")

    p_remove = sub.add_parser("remove", help="Remove a tracked skill")
    p_remove.add_argument("name", help="Skill name")
    p_remove.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    p_sched = sub.add_parser("schedule", help="Install the daily background check (macOS launchd)")
    p_sched.add_argument("--uninstall", action="store_true", help="Remove the scheduled job")
    p_sched.add_argument("--time", default="09:00", metavar="HH:MM", help="Time to run daily check (default: 09:00)")

    args = parser.parse_args()
    root = get_root()

    match args.command:
        case "add":      cmd_add(args, root)
        case "check":    cmd_check(args, root)
        case "update":   cmd_update(args, root)
        case "deploy":   cmd_deploy(args, root)
        case "list":     cmd_list(args, root)
        case "remove":   cmd_remove(args, root)
        case "schedule": cmd_schedule(args, root)
