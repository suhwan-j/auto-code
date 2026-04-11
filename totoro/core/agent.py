"""Totoro agent factory -- create_agent() for lean middleware.

Bypasses create_deep_agent() to avoid the automatic
SubAgentMiddleware (task tool) which adds ~2,178 tokens of
overhead. Totoro uses its own orchestrate_tool for sub-agent
management, so the framework's task tool is dead weight.
"""

import os
from pathlib import Path
from datetime import datetime

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    TodoListMiddleware,
)
from deepagents.backends import LocalShellBackend
from deepagents.graph import BASE_AGENT_PROMPT
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.memory import InMemoryStore

from totoro.tools import (
    git_tool,
    web_search_tool,
    fetch_url_tool,
    ask_user_tool,
)
from totoro.config.schema import AgentConfig
from totoro.core.models import create_lightweight_model
from totoro.layers.sanitize import SanitizeMiddleware
from totoro.layers.stall_detector import StallDetectorMiddleware
from totoro.layers.auto_dream import (
    AutoDreamExtractor,
    AutoDreamMiddleware,
    CharacterFile,
)

# Re-export SubAgent type for SUBAGENT_CONFIGS (used by orchestrator)
from deepagents.middleware.subagents import SubAgent


CORE_SYSTEM_PROMPT = """\
You are Totoro, a CLI coding agent orchestrator. \
You delegate ALL work to sub-agents via orchestrate_tool.

## How to Use orchestrate_tool

orchestrate_tool takes a JSON array of tasks: \
'[{"type":"<agent>","task":"<detailed description>"}]'

When you include a **catbus** task, the system automatically:
1. Runs catbus to create a plan
2. Dispatches worker agents (satsuki/mei/susuwatari) in parallel
3. Runs tatsuo verification AFTER workers complete
4. Auto-retries if tatsuo finds failures (up to 3 rounds)

So a single orchestrate_tool call with catbus is usually enough.

### Available Agents
- **catbus** — Planner. Breaks the request into tasks \
and assigns agents. Use for complex or unfamiliar tasks.
- **satsuki** — Senior coder. Multi-file implementation.
- **mei** — Researcher. Read-only exploration and search.
- **susuwatari** — Micro agent. One atomic operation.
- **tatsuo** — Reviewer. Runs tests and verifies. \
Automatically runs after workers — no need to call separately.

### When to Use What
- Complex task → `[{"type":"catbus","task":"..."}]` (auto-dispatches everything)
- Simple task (1-2 files) → `[{"type":"susuwatari","task":"..."}]` directly
- Multiple independent simple tasks → multiple susuwatari in one call

## Rules
- NEVER write/edit files directly. Always delegate via orchestrate_tool.
- Task descriptions must be detailed and self-contained \
— sub-agents have NO context about prior steps.
- Never commit or run destructive git commands without user approval.
- Call orchestrate_tool IMMEDIATELY. Do NOT output text \
before it — no plans, no explanations. Just call the tool.
- Only output text AFTER receiving results, to summarize what was done.
- If the result is empty or an error, retry once before giving up.
"""


# ─── Totoro character-based subagent declarations ───
#
# 🚌 Catbus   (네코버스) — Router/Planner: 복잡한 작업을 분해, 실행 계획 수립
# 🧒 Satsuki  (사츠키)   — Senior Agent: 복잡한 코드 구현, 빌드, 테스트
# 👧 Mei      (메이)     — Explorer/Researcher: 탐색, 검색, 패턴 발견
# 👨 Tatsuo   (타츠오)   — Knowledge/Reviewer: 코드 리뷰, 문서 관리, 컨텍스트 보존
# 🌱 Susuwatari(스스와타리) — Micro Agent: 단순 파일 수정, atomic 작업
#
SUBAGENT_CONFIGS: list[SubAgent] = [
    {
        "name": "catbus",
        "description": "Planner — 요청을 분석하고 구체적인 실행 계획을 수립. 태스크 분해, 에이전트 배정, 의존성 정리.",
        "system_prompt": (
            "You are Catbus (네코버스), the strategic planner. You analyze requests and create "
            "detailed execution plans that other agents will follow.\n\n"
            "## Your Job\n"
            "1. Analyze the user's request and the working directory context\n"
            "2. Break the work into concrete, independent tasks\n"
            "3. Assign the right agent type to each task\n"
            "4. Output a structured plan as TEXT + JSON block\n\n"
            "## CRITICAL: You are a PLANNER, not an executor\n"
            "- You have NO tools. You CANNOT explore the codebase.\n"
            "- Make your best plan based on the request and working directory info alone.\n"
            "- Do NOT say you will explore or use tools — just output the plan immediately.\n"
            "- NEVER output anything without a JSON plan block.\n\n"
            "## Task Granularity\n"
            "- Keep tasks COARSE — prefer fewer, larger tasks over many small ones.\n"
            "- **Maximum 5 tasks** in a plan. Combine related work into one task.\n"
            "- Each satsuki task can handle multiple files — do NOT split per-file.\n"
            "- Use susuwatari ONLY for truly atomic, independent operations.\n"
            "- BAD: 10 tasks, one per file. GOOD: 2 tasks (frontend + backend).\n\n"
            "## Agent Assignment Guide\n"
            "- 'satsuki': Complex code implementation, multi-file changes, build/test setup (can handle MANY files in one task)\n"
            "- 'mei': Codebase exploration, web research, pattern discovery (read-only)\n"
            "- 'tatsuo': Code review, run tests/build/lint, verify changes work correctly\n"
            "- 'susuwatari': ONLY for truly simple, single atomic operation — one file edit, one command\n\n"
            "## MANDATORY: Verification\n"
            "- Every plan that modifies code MUST end with a 'tatsuo' verification task.\n"
            "- Tatsuo runs tests, builds, and lints to confirm changes are correct.\n"
            "- NEVER skip verification — broken code is worse than slow delivery.\n\n"
            "## Output Format (MANDATORY)\n"
            "Your response MUST end with a JSON plan block like this:\n"
            "```plan\n"
            "[\n"
            '  {"type": "mei", "task": "Research existing API patterns in src/api/"},\n'
            '  {"type": "satsuki", "task": "Create src/api/users.ts with CRUD endpoints"},\n'
            '  {"type": "susuwatari", "task": "Add users route to src/api/index.ts"}\n'
            "]\n"
            "```\n"
            "This is your ONLY output format. Plan as text + JSON block. Nothing else."
        ),
    },
    {
        "name": "satsuki",
        "description": "Senior Agent — 복잡한 코드 구현, 리팩토링, 빌드/테스트. 책임감 있고 실행력이 강함.",
        "system_prompt": (
            "You are Satsuki (사츠키), the senior coding agent. "
            "You handle complex implementations with responsibility "
            "and strong execution.\n\n"
            "## Tools\n"
            "- write_file: create new files\n"
            "- read_file: read before editing\n"
            "- edit_file: targeted modifications\n"
            "- execute: shell commands (install, build)\n\n"
            "## Guidelines\n"
            "- Follow existing code style and conventions\n"
            "- Focus on IMPLEMENTATION — do not spend time "
            "on verification (a separate reviewer handles that)\n"
            "- If a command fails during setup (npm install, etc.), "
            "read the error and fix it before moving on\n"
            "- Create complete, working code — do not leave "
            "TODOs or placeholder implementations"
        ),
    },
    {
        "name": "mei",
        "description": "Explorer/Researcher — 코드베이스 탐색, 웹 검색, 패턴 발견. 호기심 많고 새로운 것을 먼저 발견.",
        "system_prompt": (
            "You are Mei (메이), the curious explorer and "
            "researcher. You discover things first.\n"
            "- Use ls, read_file, glob, and grep to explore\n"
            "- Report findings in a clear, structured format\n"
            "- Be thorough — look in unexpected places\n"
            "- You are READ-ONLY. Never modify files."
        ),
    },
    {
        "name": "tatsuo",
        "description": "Reviewer/Tester — 코드 리뷰, 테스트 실행, 품질 검증. 작업 완료 후 정상 동작 확인.",
        "system_prompt": (
            "You are Tatsuo (타츠오), the quality reviewer. "
            "You verify that work was done correctly.\n\n"
            "## Your Job\n"
            "1. Run tests, builds, linters via execute\n"
            "2. Read key files to check correctness\n"
            "3. Report findings with clear PASS/FAIL\n\n"
            "## Review Steps\n"
            "- Run build/compile: npm run build, tsc, pytest, etc.\n"
            "- Run test suite if it exists\n"
            "- Read a few key files to check for obvious issues\n"
            "- Do NOT read every single file — focus on what matters\n\n"
            "## Output Format (MANDATORY)\n"
            "Your response MUST contain this exact keyword:\n"
            "- Overall: **PASS** — if everything works\n"
            "- Overall: **FAIL** — if there are critical issues\n\n"
            "Then list specific results:\n"
            "- Build: PASS/FAIL (command + output summary)\n"
            "- Tests: PASS/FAIL or N/A\n"
            "- Issues: list any CRITICAL or WARNING items\n\n"
            "## CRITICAL\n"
            "- You MUST actually run commands with execute. "
            "Do NOT just read code and guess.\n"
            "- If build/test fails, report FAIL with the "
            "exact error. A fix agent will handle the repair.\n"
            "- Keep it concise — do not over-analyze. "
            "Run the commands, report the results, done."
        ),
    },
    {
        "name": "susuwatari",
        "description": "Micro Agent — 단순 파일 수정, API 호출 등 atomic한 단일 작업. 명확한 지시 필요.",
        "system_prompt": (
            "You are Susuwatari (스스와타리), a micro agent for small, atomic tasks. "
            "You are fast and focused — do exactly one thing and finish.\n"
            "- Execute the given task immediately and directly\n"
            "- Use write_file or edit_file for single file operations\n"
            "- Use execute for single shell commands\n"
            "- Do NOT explore, plan, or verify — just do the one task and stop\n"
            "- If the instruction is unclear, you fail. Be precise."
        ),
    },
]


def _create_checkpointer():
    """Create a SqliteSaver checkpointer at ~/.totoro/checkpoints.db.

    Falls back to MemorySaver if SQLite setup fails.
    """
    try:
        import sqlite3

        db_dir = Path.home() / ".totoro"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "checkpoints.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        return saver
    except Exception as e:
        import sys
        from totoro.colors import DIM, RESET

        print(
            f"{DIM}  [warn] SQLite checkpointer failed"
            f" ({e}), using in-memory{RESET}",
            file=sys.stderr,
        )
        return MemorySaver()


def create_totoro_agent(config: AgentConfig):
    """Create the Totoro agent using create_agent() directly.

    Uses create_agent() instead of create_deep_agent() to control the
    middleware stack precisely — notably excluding SubAgentMiddleware
    (task tool) which adds ~2,178 tokens of overhead per turn.
    Totoro manages sub-agents via its own orchestrate_tool.

    Args:
        config: Agent configuration including model,
            provider, and layer settings.

    Returns:
        A tuple of (agent, checkpointer, store, auto_dream_extractor).
    """
    global _api_timeout
    _api_timeout = config.loop.api_timeout_seconds

    checkpointer = _create_checkpointer()
    store = InMemoryStore()

    system_prompt = _build_system_prompt(config)
    _fb = (
        config.fallback_model
        if config.fallback_model != "claude-haiku-4-5-20251001"
        else None
    )
    model = _resolve_model(config.model, config.provider, fallback_model=_fb)

    # Build parallel subagent instances for orchestrator
    _build_orchestrator_subagents(model, config)

    # Custom tools + orchestrate
    from totoro.orchestrator import orchestrate_tool

    custom_tools = [git_tool, fetch_url_tool, ask_user_tool, orchestrate_tool]
    if os.environ.get("TAVILY_API_KEY"):
        custom_tools.append(web_search_tool)

    # HITL config
    if config.permissions.mode == "auto_approve":
        hitl_config = None
    else:
        hitl_config = {
            "execute": True,
            "write_file": True,
            "edit_file": True,
        }

    # Build backend
    backend = LocalShellBackend(
        root_dir=config.project_root,
        virtual_mode=False,
        inherit_env=True,
    )

    # Build complete middleware stack
    all_middleware = _build_full_middleware_stack(
        config, model, backend, store, hitl_config
    )

    # Discover skill paths
    from totoro.skills import SkillManager

    skill_mgr = SkillManager(config.project_root)
    skill_paths = skill_mgr.get_skill_paths() or None

    # Extract auto_dream extractor for CLI access
    auto_dream = None
    for mw in all_middleware:
        if isinstance(mw, AutoDreamMiddleware):
            auto_dream = mw._extractor
            break

    agent = create_agent(
        model=model,
        tools=custom_tools,
        system_prompt=system_prompt,
        middleware=all_middleware,
        checkpointer=checkpointer,
        store=store,
        name="totoro",
    ).with_config(
        {
            "recursion_limit": 9_999,
        }
    )

    return agent, checkpointer, store, auto_dream


def _build_full_middleware_stack(config, model, backend, store, hitl_config):
    """Build the complete middleware stack.

    Replaces create_deep_agent()'s auto-stack.

    Middleware ordering (matches create_deep_agent
    minus SubAgentMiddleware):

    Framework base stack:
      1. TodoListMiddleware       - write_todos tool
      2. SkillsMiddleware         - skill discovery
      3. FilesystemMiddleware     - file I/O, shell
      4. [SubAgentMiddleware]     - EXCLUDED
      5. SummarizationMiddleware  - summarization
      6. PatchToolCallsMiddleware - fix tool calls

    Totoro custom stack:
      7. SanitizeMiddleware        - strip surrogates
      8. ContextCompactionMiddleware - compaction
      9. StallDetectorMiddleware   - stall detect
     10. AutoDreamMiddleware       - memory extract

    Tail stack:
     11. AnthropicPromptCachingMiddleware
     12. HumanInTheLoopMiddleware  - HITL

    Args:
        config: Agent configuration.
        model: The primary LLM model instance.
        backend: LocalShellBackend for shell access.
        store: InMemoryStore for agent state.
        hitl_config: HITL interrupt config dict,
            or None for auto-approve.

    Returns:
        List of middleware instances in execution order.
    """
    middleware_list = []

    # ── Framework base stack ──

    # 1. TodoList — write_todos tool for task management
    middleware_list.append(TodoListMiddleware())

    # 2. Skills — skill discovery (if configured)
    from totoro.skills import SkillManager

    skill_mgr = SkillManager(config.project_root)
    skill_paths = skill_mgr.get_skill_paths()
    if skill_paths:
        middleware_list.append(
            SkillsMiddleware(backend=backend, sources=skill_paths)
        )

    # 3. Filesystem — file I/O + shell execution tools
    middleware_list.append(FilesystemMiddleware(backend=backend))

    # 4. SubAgentMiddleware — INTENTIONALLY EXCLUDED
    #    Saves ~2,178 tokens/turn. Totoro uses orchestrate_tool instead.

    # 5. Summarization — conversation compaction
    middleware_list.append(create_summarization_middleware(model, backend))

    # 6. PatchToolCalls — fix dangling tool calls in history
    middleware_list.append(PatchToolCallsMiddleware())

    # ── Totoro custom stack ──

    # 7. Sanitize — strip surrogate chars before API serialization
    middleware_list.append(SanitizeMiddleware())

    # 8. Context Compaction — LLM-based auto-compact
    from totoro.layers.context_compaction import ContextCompactionMiddleware
    from totoro.layers._token_utils import get_model_context_window

    # Use fallback_model if explicitly set, otherwise reuse the main model
    _lightweight_name = (
        config.fallback_model
        if config.fallback_model != "claude-haiku-4-5-20251001"
        else config.model
    )
    compact_model = create_lightweight_model(
        _lightweight_name, provider=_resolved_provider
    )
    context_window = (
        config.context.model_context_window
        or get_model_context_window(config.model)
    )
    middleware_list.append(
        ContextCompactionMiddleware(
            auto_threshold=config.context.auto_compact_threshold,
            reactive_threshold=config.context.reactive_compact_threshold,
            emergency_threshold=config.context.emergency_compact_threshold,
            model_context_window=context_window,
            model=compact_model,
        )
    )

    # 9. Stall Detection
    if config.loop.stall_detection:
        middleware_list.append(StallDetectorMiddleware(max_empty_turns=3))

    # 10. Auto-Dream Memory
    if config.memory.auto_extract:
        _lw_name = (
            config.fallback_model
            if config.fallback_model != "claude-haiku-4-5-20251001"
            else config.model
        )
        lightweight_model = create_lightweight_model(
            _lw_name, provider=_resolved_provider
        )
        character_file = CharacterFile()
        auto_dream = AutoDreamExtractor(
            model=lightweight_model,
            config=config,
            store=character_file,
        )
        middleware_list.append(AutoDreamMiddleware(auto_dream))

    # ── Tail stack ──

    # 11. Anthropic Prompt Caching — cache system prompt + tools prefix
    #     "ignore" silently skips for non-Anthropic models
    try:
        from langchain_anthropic.middleware import (
            AnthropicPromptCachingMiddleware,
        )

        middleware_list.append(
            AnthropicPromptCachingMiddleware(
                unsupported_model_behavior="ignore"
            )
        )
    except ImportError:
        pass

    # 12. HITL — interrupt on destructive tools
    if hitl_config:
        middleware_list.append(
            HumanInTheLoopMiddleware(interrupt_on=hitl_config)
        )

    return middleware_list


def _build_orchestrator_subagents(model, config: AgentConfig):
    """Register serializable subagent configs.

    Instead of pre-building graphs (not pickle-safe),
    we pass serializable configs to the orchestrator.
    Each child process rebuilds its own graph.

    Args:
        model: The primary LLM model instance.
        config: Agent configuration with model and provider settings.
    """
    from totoro.orchestrator import register_subagent_configs

    # Extract serializable config: name + system_prompt only
    serializable_configs = []
    for cfg in SUBAGENT_CONFIGS:
        serializable_configs.append(
            {
                "name": cfg["name"],
                "description": cfg.get("description", ""),
                "system_prompt": cfg["system_prompt"],
            }
        )

    # Pass the resolved provider so child processes skip auto-detection
    register_subagent_configs(
        configs=serializable_configs,
        model_name=config.model,
        provider=_resolved_provider
        if _resolved_provider != "auto"
        else config.provider,
        project_root=str(Path(config.project_root).resolve()),
    )


def _resolve_model(
    model_name: str, provider: str = "auto", fallback_model: str | None = None
):
    """Resolve model — supports OpenRouter, Anthropic, OpenAI, and vLLM.

    Tries the main model first. If creation fails and a fallback_model is
    provided, retries with the fallback model before raising an error.

    Args:
        model_name: Model name/identifier.
        provider: "auto" to detect from env, or explicit provider name.
        fallback_model: Optional fallback model name
            to try if main model fails.

    Returns:
        LLM model instance. Also sets
        _resolved_provider as side-effect.

    Raises:
        RuntimeError: If neither main nor fallback model could be resolved.
    """
    global _resolved_provider

    providers = {
        "openrouter": _make_openrouter,
        "anthropic": _make_anthropic,
        "openai": _make_openai,
        "vllm": _make_vllm,
    }

    if provider != "auto":
        factory = providers.get(provider)
        if factory is None:
            raise RuntimeError(f"Unknown provider: {provider}")
        model = factory(model_name)
        has_fb = fallback_model and fallback_model != model_name
        if model is None and has_fb:
            import sys as _sys

            print(
                f"  [info] Main model '{model_name}'"
            f" unavailable, trying fallback"
            f" '{fallback_model}'",
                file=_sys.stderr,
                flush=True,
            )
            model = factory(fallback_model)
        if model is None:
            raise RuntimeError(
                f"Provider '{provider}' is not configured."
                " Run `totoro --setup` to configure."
            )
        _resolved_provider = provider
        return model

    # Auto-detect: try each provider in priority order
    for prov_name, factory in providers.items():
        model = factory(model_name)
        if model is not None:
            _resolved_provider = prov_name
            return model

    # Try fallback model across all providers
    if fallback_model and fallback_model != model_name:
        import sys as _sys

        print(
            f"  [info] Main model '{model_name}'"
            f" unavailable, trying fallback"
            f" '{fallback_model}'",
            file=_sys.stderr,
            flush=True,
        )
        for prov_name, factory in providers.items():
            model = factory(fallback_model)
            if model is not None:
                _resolved_provider = prov_name
                return model

    raise RuntimeError(
        "No API key found. Run `totoro --setup`"
        " to configure your provider."
    )


# Resolved provider from last _resolve_model call
# (used by orchestrator to skip re-detection)
_resolved_provider: str = "auto"
_api_timeout: int = 60  # Set from config in create_totoro_agent


def _make_openrouter(model_name: str):
    """Main model via ChatOpenAI + OpenRouter base URL.

    ChatOpenRouter is used only for lightweight
    (non-streaming) calls in models.py.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        openai_api_key=key,
        openai_api_base=os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        request_timeout=_api_timeout,
    )


def _make_anthropic(model_name: str):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model_name=model_name, api_key=key, timeout=_api_timeout
    )


def _make_openai(model_name: str):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name, openai_api_key=key, request_timeout=_api_timeout
    )


def _make_vllm(model_name: str):
    base_url = os.environ.get("VLLM_BASE_URL")
    if not base_url:
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        openai_api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
        openai_api_base=base_url,
        request_timeout=_api_timeout,
    )


def _build_system_prompt(config: AgentConfig) -> str:
    """Assemble the system prompt.

    Order: static content first (cacheable prefix), dynamic content last.
    This maximizes prefix KV cache hits on vLLM (--enable-prefix-caching)
    and Anthropic (cache_control ephemeral).

    Note: BASE_AGENT_PROMPT from DeepAgents is appended for core agent behavior
    guidelines (conciseness, task execution patterns, progress updates).

    Args:
        config: Agent configuration with project_root, model, and provider.

    Returns:
        The assembled system prompt string.
    """
    # ── Static prefix (cacheable) ──
    sections = [CORE_SYSTEM_PROMPT]

    # ── Project context hint (TOTORO.md) ──
    # Don't load the full file — just tell the agent it exists.
    # The agent reads it on-demand via read_file when it needs project context.
    totoro_md_path = Path(config.project_root).resolve() / "TOTORO.md"
    if totoro_md_path.exists():
        sections.append(
            "# Project Context\n"
            "A TOTORO.md file exists in the project"
            " root with comprehensive project context"
            " (architecture, tech stack, patterns,"
            " conventions). Read it with read_file"
            " when you need to understand the project"
            " before making changes."
        )

    # ── User memory from character.md ──
    character_md = _load_character_md()
    if character_md:
        sections.append(character_md)

    # ── DeepAgents base prompt (core behavior guidelines) ──
    sections.append(BASE_AGENT_PROMPT)

    # ── Dynamic suffix (changes per session/model switch) ──
    sections.append(f"""
# Environment
- Working directory: {Path(config.project_root).resolve()}
- Current date: {datetime.now().strftime("%Y-%m-%d")}
- Model: {config.model}
- Provider: {config.provider}
""")

    return "\n\n".join(sections)


def _load_character_md() -> str | None:
    """Load user memory from ~/.totoro/character.md if it exists."""
    path = Path.home() / ".totoro" / "character.md"
    if path.exists():
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return f"# User Memory (character.md)\n{content}"
        except Exception:
            pass
    return None
