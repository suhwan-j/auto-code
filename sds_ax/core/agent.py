"""SDS-AX agent factory — wraps create_deep_agent()"""
import os
from pathlib import Path
from datetime import datetime

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from sds_ax.tools import git_tool, bash_tool, web_search_tool, fetch_url_tool, ask_user_tool
from sds_ax.config.schema import AgentConfig


CORE_SYSTEM_PROMPT = """You are SDS-AX, a CLI coding agent. You help users with software development tasks
by reading, writing, and editing code, running commands, searching the web,
and managing git repositories.

Key behaviors:
- Always read a file before editing it
- Use edit_file for targeted changes, write_file only for new files or complete rewrites
- Never commit without explicit user request
- Never run destructive git commands (push --force, reset --hard) without user approval
- Use task to delegate sub-tasks to specialized sub-agents when beneficial
- Use ask_user when you need clarification or approval
- Use bash to run shell commands for building, testing, and verifying your work
- When creating projects, create all necessary files and verify they work
"""


def create_sds_ax_agent(config: AgentConfig):
    """Create the SDS-AX agent wrapping create_deep_agent().

    DeepAgents provides automatically:
    - Built-in tools: write_todos, ls, read_file, write_file, edit_file, glob, grep, task
    - Middleware: TodoList, Filesystem, SubAgent, HITL, Skills, Memory

    SDS-AX adds:
    - Custom tools: git, bash, web_search, fetch_url, ask_user
    - Subagent type definitions
    - CompositeBackend for memory routing
    - interrupt_on for HITL on destructive tools
    """
    custom_tools = [git_tool, bash_tool, web_search_tool, fetch_url_tool, ask_user_tool]

    # NOTE: Subagents require model + actual tool objects (not string names).
    # For MVP, we skip subagents — the main agent handles everything.
    # Subagents will be added in Phase 3 once tool resolution is implemented.
    subagent_configs = None

    checkpointer = MemorySaver()
    store = InMemoryStore()

    # HITL: destructive tools require approval (unless auto_approve mode)
    if config.permissions.mode == "auto_approve":
        hitl_config = {}
    else:
        hitl_config = {
            "write_file": True,
            "edit_file": True,
            "bash": True,
            # git excluded — has internal safety rules with selective interrupt
        }

    system_prompt = _build_system_prompt(config)

    # Resolve model — support OpenRouter via OPENROUTER_API_KEY
    model = _resolve_model(config.model)

    agent = create_deep_agent(
        name="sds-ax",
        model=model,
        tools=custom_tools,
        system_prompt=system_prompt,
        subagents=subagent_configs,
        backend=lambda rt: CompositeBackend(
            default=StateBackend(rt),
            routes={
                "/memories/": StoreBackend(rt),
                "/project/": StoreBackend(rt),
            },
        ),
        interrupt_on=hitl_config if hitl_config else None,
        checkpointer=checkpointer,
        store=store,
    )

    return agent, checkpointer, store


def _build_system_prompt(config: AgentConfig) -> str:
    """Assemble the system prompt."""
    sections = [CORE_SYSTEM_PROMPT]

    sections.append(f"""
# Environment
- Working directory: {Path(config.project_root).resolve()}
- Current date: {datetime.now().strftime('%Y-%m-%d')}
""")

    agents_md = _load_agents_md(config.project_root)
    if agents_md:
        # Truncate if too large
        if len(agents_md) > 16000:
            agents_md = agents_md[:16000] + "\n... (truncated)"
        sections.append(f"# Project Rules (AGENTS.md)\n{agents_md}")

    return "\n\n".join(sections)


def _load_agents_md(project_root: str) -> str | None:
    """Load AGENTS.md from project root if it exists."""
    path = Path(project_root) / "AGENTS.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
