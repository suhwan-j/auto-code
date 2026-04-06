from langchain_core.tools import tool
from langgraph.types import interrupt
from typing import Optional
import asyncio
import shlex

GIT_READ_ONLY = frozenset({"status", "diff", "log", "blame", "show", "branch --list", "remote -v", "tag --list", "stash list", "rev-parse"})
GIT_DESTRUCTIVE = frozenset({"add", "commit", "checkout", "switch", "merge", "stash", "stash pop", "stash drop", "branch -d", "branch -m", "tag", "restore", "reset --soft", "reset --mixed"})
GIT_DANGEROUS = frozenset({"push", "push --force", "push --force-with-lease", "reset --hard", "clean -f", "clean -fd", "branch -D", "rebase", "rebase -i"})
GIT_FORBIDDEN = frozenset({"config"})
SENSITIVE_PATTERNS = {".env", "credentials", "secret", ".pem", ".key", "token"}

@tool
async def git_tool(subcommand: str, args: Optional[str] = None, no_verify: bool = False) -> str:
    """Execute git commands with built-in safety rules.

    Args:
        subcommand: Git subcommand (e.g., "status", "diff", "commit")
        args: Additional arguments (e.g., "-m 'fix bug'", "--staged")
        no_verify: Skip git hooks — only when explicitly requested by user
    """
    full_args = f"{subcommand} {args}" if args else subcommand
    parsed_subcmd = subcommand.split()[0]

    if parsed_subcmd in GIT_FORBIDDEN:
        return f"Blocked: 'git {parsed_subcmd}' is not allowed."

    if "--no-verify" in (args or "") and not no_verify:
        return "Blocked: --no-verify requires explicit opt-in via no_verify=True."

    # Force push to main/master blocked
    if parsed_subcmd == "push" and args:
        if "--force" in args or "--force-with-lease" in args:
            target = _extract_push_target(args)
            if target in ("main", "master"):
                return f"Blocked: force push to '{target}' is not allowed."

    danger_level = _classify_git_command(subcommand, args or "")

    if danger_level == "dangerous":
        approval = interrupt({"type": "permission_request", "tool": "git", "input": f"git {full_args}", "message": f"Dangerous git command: 'git {full_args}'. Allow?"})
        if not approval:
            return f"User denied: git {full_args}"

    if parsed_subcmd == "add" and args:
        sensitive = _detect_sensitive_files(args)
        if sensitive:
            approval = interrupt({"type": "permission_request", "tool": "git", "input": f"git add {args}", "message": f"Staging potentially sensitive files: {sensitive}. Allow?"})
            if not approval:
                return f"User denied staging sensitive files: {sensitive}"

    proc = await asyncio.create_subprocess_shell(f"git {full_args}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        return "Git command timed out after 60s"
    output = stdout.decode() + stderr.decode()
    return output.strip() or "(no output)"


def _classify_git_command(subcommand: str, args: str) -> str:
    full_cmd = f"{subcommand} {args}".strip()
    for pattern in GIT_DANGEROUS:
        if full_cmd.startswith(pattern) or subcommand.startswith(pattern):
            return "dangerous"
    for pattern in GIT_DESTRUCTIVE:
        if full_cmd.startswith(pattern) or subcommand.startswith(pattern):
            return "destructive"
    return "read_only"


def _detect_sensitive_files(args: str) -> list[str]:
    if args.strip() in ("-A", "--all", "."):
        return [f"'{args.strip()}' stages all files — review before committing"]
    files = shlex.split(args)
    return [f for f in files if any(p in f.lower() for p in SENSITIVE_PATTERNS)]


def _extract_push_target(args: str) -> str:
    parts = shlex.split(args)
    non_flag = [p for p in parts if not p.startswith("-")]
    if len(non_flag) >= 2:
        return non_flag[1]
    return ""
