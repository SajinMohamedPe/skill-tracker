from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .git import CommitInfo

# Patterns that suggest someone is trying to hijack an LLM reading this output.
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|prior|all)\s+(instructions?|prompts?|context)",
    r"disregard\s+(previous|above|prior|all)",
    r"forget\s+(your|all|previous)",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?\s*:",
    r"system\s*prompt\s*:",
    r"act\s+as\s+(a\s+)?(?!git|commit|author)",  # "act as a" but not "act as author"
    r"<\s*/?(?:system|user|assistant|instruction)\s*>",
    r"^\s*(?:SYSTEM|USER|ASSISTANT)\s*:",
    r"\[\s*(?:INST|SYS|SYSTEM)\s*\]",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _INJECTION_PATTERNS]

_REDACTED = "[yellow bold]⚠ REDACTED — suspicious content detected[/yellow bold]"

# Checks if any of the injection patterns are found in the given text
def _has_injection(text: str) -> bool:
    return any(p.search(text) for p in _COMPILED)

# Sanitises a string by redacting it if it contains potential prompt injection patterns, otherwise escaping rich markup characters
def _escape_rich(text: str) -> str:
    """Prevent rich from interpreting brackets as markup."""
    return text.replace("[", "\\[")

# Public functions
def sanitise_text(text: str) -> str:
    """Sanitise a single string for safe display via rich Console."""
    if _has_injection(text):
        return _REDACTED
    return _escape_rich(text)

# Sanitises a CommitInfo object by redacting the author and message if they contain potential prompt injection patterns
def sanitise_commit(commit: CommitInfo) -> CommitInfo:
    """Return a copy of CommitInfo with author and message sanitised."""
    return replace(
        commit,
        author=sanitise_text(commit.author),
        message=sanitise_text(commit.message),
    )

# Sanitises a diff string for safe display, and detects if it's a prompt file based on the filename
# Sanitises added lines (+) only in a diff, flags .md files as prompt files so the caller can warn the user │
def sanitise_diff(diff: str, file_path: str) -> tuple[str, bool]:
    """
    Sanitise a diff string for safe display.

    Returns (sanitised_diff, is_prompt_file).
    is_prompt_file is True when the file is a .md skill/agent file — the caller
    should warn the user they are reviewing a prompt change.
    """
    is_prompt_file = Path(file_path).name.upper().endswith(".MD")

    lines = []
    injection_found = False
    for line in diff.splitlines():
        # Only scan added lines (+) — removed lines are your own previous content
        if line.startswith("+") and _has_injection(line[1:]):
            lines.append(f"+[yellow bold]⚠ REDACTED — suspicious content on this line[/yellow bold]")
            injection_found = True
        else:
            lines.append(_escape_rich(line))

    result = "\n".join(lines)
    return result, is_prompt_file


# Avoid circular import — import Path here
from pathlib import Path  # noqa: E402
