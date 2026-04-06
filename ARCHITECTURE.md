# SDS-AX Architecture

> **구현 스택**: Python 3.11+ / LangGraph / LangChain / DeepAgents  
> **이 문서**: 기술적 구현 청사진. 무엇을 만들지는 AGENTS.md, 어떻게 만들지는 이 문서.

---

## 1. 시스템 개요

```
┌──────────────────────────────────────────────────────────────────┐
│                         SDS-AX CLI                               │
│                                                                  │
│  ┌────────────┐  ┌───────────────┐  ┌────────────────────────┐  │
│  │ Textual UI │  │ Non-Interactive│  │ LangGraph API Server   │  │
│  │ (TUI)      │  │ Mode          │  │ (Programmatic Access)  │  │
│  └─────┬──────┘  └──────┬────────┘  └──────────┬─────────────┘  │
│        │                │                       │                │
│        └────────────────┼───────────────────────┘                │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Core Agent (LangGraph StateGraph)            │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │              Middleware Stack                      │   │   │
│  │  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │   │   │
│  │  │  │ Model      │ │ Permission │ │ Memory       │ │   │   │
│  │  │  │ Middleware  │ │ Middleware │ │ Middleware   │ │   │   │
│  │  │  └────────────┘ └────────────┘ └──────────────┘ │   │   │
│  │  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │   │   │
│  │  │  │ SubAgent   │ │ TodoList   │ │ HITL         │ │   │   │
│  │  │  │ Middleware  │ │ Middleware │ │ Middleware   │ │   │   │
│  │  │  └────────────┘ └────────────┘ └──────────────┘ │   │   │
│  │  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │   │   │
│  │  │  │ Filesystem │ │ Hook       │ │ Stall        │ │   │   │
│  │  │  │ Middleware  │ │ Middleware │ │ Detector     │ │   │   │
│  │  │  └────────────┘ └────────────┘ └──────────────┘ │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │              Tool Registry                        │   │   │
│  │  │  Built-in Tools + MCP Tools + Skill Tools         │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                        │
│          ┌──────────────┼──────────────┐                        │
│          ▼              ▼              ▼                         │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐                │
│  │ Composite    │ │ LLM      │ │ LangSmith    │                │
│  │ Backend      │ │ Provider │ │ Tracing      │                │
│  │ (Storage)    │ │ (API)    │ │ (Telemetry)  │                │
│  └──────────────┘ └──────────┘ └──────────────┘                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 디렉토리 구조

```
sds-ax/
├── pyproject.toml                 # 프로젝트 메타데이터, 의존성
├── AGENTS.md                      # 에이전트 사양/행동 규칙
├── ARCHITECTURE.md                # 이 문서
├── .env.example                   # 환경변수 템플릿
│
├── sds_ax/                        # 메인 패키지
│   ├── __init__.py
│   ├── __main__.py                # python -m sds_ax 진입점
│   ├── cli.py                     # CLI 파서 (argparse), 모드 라우팅
│   │
│   ├── core/                      # 핵심 에이전트 엔진
│   │   ├── __init__.py
│   │   ├── agent.py               # create_agent() — StateGraph 조립
│   │   ├── graph.py               # StateGraph 정의, 노드/엣지 구성
│   │   ├── state.py               # AgentState TypedDict + reducer
│   │   ├── loop.py                # Agentic Loop (쿼리 루프) 구현
│   │   └── models.py              # LLM 프로바이더 초기화, 폴백 체인
│   │
│   ├── tools/                     # 도구 시스템
│   │   ├── __init__.py
│   │   ├── registry.py            # 도구 레지스트리, 등록/조회
│   │   ├── base.py                # BaseTool 인터페이스
│   │   ├── executor.py            # 도구 실행 파이프라인, 동시성 파티셔닝
│   │   ├── builtin/               # 내장 도구
│   │   │   ├── __init__.py
│   │   │   ├── file_read.py       # read_file
│   │   │   ├── file_write.py      # write_file
│   │   │   ├── file_edit.py       # edit_file
│   │   │   ├── bash.py            # bash (셸 명령)
│   │   │   ├── grep.py            # grep (ripgrep 래퍼)
│   │   │   ├── glob_tool.py       # glob
│   │   │   ├── ls.py              # ls (디렉토리 목록)
│   │   │   ├── web_search.py      # web_search (Tavily)
│   │   │   ├── fetch_url.py       # fetch_url
│   │   │   ├── ask_user.py        # ask_user (interrupt)
│   │   │   └── todos.py           # write_todos
│   │   └── mcp/                   # MCP 도구 통합
│   │       ├── __init__.py
│   │       ├── client.py          # MCP 클라이언트
│   │       ├── config.py          # MCP 서버 설정 로드
│   │       └── trust.py           # MCP 서버 신뢰 관리
│   │
│   ├── subagents/                 # 동적 서브에이전트 시스템
│   │   ├── __init__.py
│   │   ├── manager.py             # SubAgentManager — 생성/추적/소멸
│   │   ├── types.py               # 서브에이전트 타입 정의 (explorer, coder, ...)
│   │   ├── factory.py             # 서브에이전트 동적 생성 팩토리
│   │   ├── lifecycle.py           # 생명주기 관리 (spawn → run → report → destroy)
│   │   └── task_tool.py           # task() 도구 구현 (메인→서브 위임)
│   │
│   ├── memory/                    # 장기 메모리 시스템
│   │   ├── __init__.py
│   │   ├── store.py               # MemoryStore — LangGraph Store 래퍼
│   │   ├── extractor.py           # 자동 메모리 추출 (Auto-Dream)
│   │   ├── retriever.py           # 쿼리 시 관련 메모리 검색
│   │   ├── types.py               # 메모리 엔트리 스키마
│   │   ├── index.py               # MEMORY_INDEX.md 관리
│   │   └── backends/              # 스토리지 백엔드
│   │       ├── __init__.py
│   │       ├── sqlite_store.py    # SQLite 기반 (개발/단독)
│   │       └── postgres_store.py  # PostgreSQL 기반 (프로덕션)
│   │
│   ├── middleware/                 # 미들웨어 스택
│   │   ├── __init__.py
│   │   ├── model.py               # ConfigurableModelMiddleware
│   │   ├── permissions.py         # PermissionMiddleware
│   │   ├── memory.py              # MemoryMiddleware (자동 추출/주입)
│   │   ├── hooks.py               # HookMiddleware (pre/post 훅)
│   │   ├── stall_detector.py      # StallDetectorMiddleware (멈춤 감지)
│   │   └── context_manager.py     # ContextManagementMiddleware (컴팩션)
│   │
│   ├── permissions/               # 권한 시스템
│   │   ├── __init__.py
│   │   ├── engine.py              # 권한 판정 엔진
│   │   ├── rules.py               # 규칙 파서/매처
│   │   └── config.py              # 권한 설정 로더
│   │
│   ├── skills/                    # 스킬 시스템
│   │   ├── __init__.py
│   │   ├── loader.py              # 스킬 발견/로드 (파일시스템 스캔)
│   │   ├── invoker.py             # 스킬 실행 (포크된 서브에이전트)
│   │   └── builtin/               # 내장 스킬
│   │       ├── remember/SKILL.md  # 메모리 저장 스킬
│   │       └── explore/SKILL.md   # 코드베이스 탐색 스킬
│   │
│   ├── commands/                  # 슬래시 커맨드
│   │   ├── __init__.py
│   │   ├── registry.py            # 커맨드 등록/발견
│   │   ├── help.py
│   │   ├── clear.py
│   │   ├── compact.py
│   │   ├── model.py
│   │   ├── cost.py
│   │   ├── memory.py
│   │   ├── tasks.py
│   │   ├── config.py
│   │   └── ...
│   │
│   ├── context/                   # 컨텍스트 관리
│   │   ├── __init__.py
│   │   ├── compact.py             # Auto/Reactive/Emergency 컴팩션
│   │   ├── token_counter.py       # 모델별 토큰 카운팅
│   │   └── system_prompt.py       # 시스템 프롬프트 조립
│   │
│   ├── session/                   # 세션 관리
│   │   ├── __init__.py
│   │   ├── manager.py             # 세션 생성/복원/목록
│   │   ├── storage.py             # SQLite 기반 세션 영속성
│   │   └── checkpoint.py          # LangGraph 체크포인터 래퍼
│   │
│   ├── config/                    # 설정
│   │   ├── __init__.py
│   │   ├── settings.py            # 설정 로더 (파일 + 환경변수 + CLI)
│   │   ├── schema.py              # 설정 스키마 (Pydantic)
│   │   └── env.py                 # 환경변수 관리
│   │
│   ├── ui/                        # TUI 레이어
│   │   ├── __init__.py
│   │   ├── app.py                 # Textual App 메인
│   │   ├── widgets/               # UI 위젯
│   │   │   ├── prompt_input.py    # 입력 프롬프트
│   │   │   ├── message_list.py    # 메시지 렌더링
│   │   │   ├── status_bar.py      # 상태 바 (비용, 모델)
│   │   │   ├── task_panel.py      # 서브에이전트/태스크 패널
│   │   │   └── spinner.py         # 로딩 스피너
│   │   └── theme.py               # 테마 설정
│   │
│   ├── telemetry/                 # 텔레메트리
│   │   ├── __init__.py
│   │   ├── tracer.py              # LangSmith 트레이싱 래퍼
│   │   └── stats.py               # 세션 통계 (비용, 토큰, 도구 호출)
│   │
│   └── utils/                     # 유틸리티
│       ├── __init__.py
│       ├── async_helpers.py       # 비동기 유틸리티
│       ├── retry.py               # 지수 백오프 재시도
│       ├── file_ops.py            # 파일 연산 유틸리티
│       ├── git.py                 # Git 연동
│       └── formatting.py          # 출력 포맷팅
│
├── skills/                        # 프로젝트 레벨 스킬
│   └── deep-interview/SKILL.md
│
├── tests/                         # 테스트
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
└── scripts/                       # 빌드/배포 스크립트
    ├── install.sh
    └── dev.sh
```

---

## 3. 핵심 모듈 상세 설계

### 3.1 AgentState (core/state.py)

LangGraph StateGraph의 상태 스키마. 모든 노드가 공유하는 중앙 상태.

```python
from typing import Annotated, Optional, Literal
from typing_extensions import TypedDict
from langgraph.graph import add_messages
import operator


class SubAgentInfo(TypedDict):
    agent_id: str
    agent_type: str
    status: str
    instruction: str
    result: Optional[str]


class LoopGuard(TypedDict):
    """Agentic Loop 방어 상태"""
    turn_count: int
    total_cost_usd: float
    consecutive_empty_turns: int
    last_tool_calls: list[str]  # 최근 도구 호출 (반복 감지용)
    stall_recovery_attempts: int


class AgentState(TypedDict):
    """메인 에이전트 상태 스키마"""
    # 메시지 이력 (add_messages reducer로 누적)
    messages: Annotated[list, add_messages]

    # 태스크 관리
    todos: list[dict]

    # 서브에이전트 추적
    active_subagents: Annotated[list[SubAgentInfo], operator.add]

    # 루프 방어
    loop_guard: LoopGuard

    # 컨텍스트 관리
    context_usage_ratio: float  # 0.0 ~ 1.0
    needs_compaction: bool

    # 세션 메타데이터
    session_id: str
    project_root: str
    cwd: str

    # 메모리 컨텍스트 (매 턴 주입)
    memory_context: Optional[str]
```

### 3.2 Core Graph (core/graph.py)

LangGraph StateGraph로 구현하는 에이전트의 핵심 실행 그래프.

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, RetryPolicy
from langgraph.prebuilt import ToolNode
from typing import Literal


def create_agent_graph(
    model,
    tools: list,
    checkpointer,
    store,
    config: dict
) -> StateGraph:
    """에이전트 실행 그래프 조립"""

    graph = StateGraph(AgentState)

    # ─── 노드 정의 ───
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("agent", agent_node, retry_policy=RetryPolicy(max_attempts=3))
    graph.add_node("tools", tool_execution_node)
    graph.add_node("postprocess", postprocess_node)
    graph.add_node("compact", compact_node)
    graph.add_node("stall_recovery", stall_recovery_node)

    # ─── 엣지 정의 ───
    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "agent")

    # agent 노드 → 조건부 라우팅
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        ["tools", "compact", "stall_recovery", END]
    )

    # tools → agent (루프백)
    graph.add_edge("tools", "postprocess")
    graph.add_edge("postprocess", "agent")

    # compact → agent (압축 후 재시도)
    graph.add_edge("compact", "agent")

    # stall_recovery → 조건부
    graph.add_conditional_edges(
        "stall_recovery",
        route_after_recovery,
        ["agent", END]
    )

    return graph.compile(
        checkpointer=checkpointer,
        store=store
    )


# ─── 라우팅 함수 ───

def route_after_agent(state: AgentState) -> Literal["tools", "compact", "stall_recovery", "__end__"]:
    """agent 노드 실행 후 다음 경로 결정"""
    last_message = state["messages"][-1]
    guard = state["loop_guard"]

    # 최대 턴 초과
    if guard["turn_count"] >= MAX_TURNS:
        return END

    # 비용 한도 초과
    if guard["total_cost_usd"] >= MAX_COST_USD:
        return END

    # 멈춤 감지
    if guard["consecutive_empty_turns"] >= 3:
        return "stall_recovery"

    # 컨텍스트 압축 필요
    if state["needs_compaction"]:
        return "compact"

    # 도구 호출 있음 → 도구 실행
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # end_turn → 종료
    return END
```

### 3.3 노드 구현 상세

```python
# ─── preprocess_node ───
async def preprocess_node(state: AgentState, config: RunnableConfig) -> dict:
    """매 턴 시작 시 전처리"""
    # 1. 관련 메모리 검색 및 주입
    memory_context = await retrieve_relevant_memories(
        state["messages"][-1].content,
        config
    )

    # 2. 컨텍스트 사용률 확인
    usage = calculate_context_usage(state["messages"], config)
    needs_compaction = usage > COMPACT_THRESHOLD

    # 3. 루프 가드 갱신
    guard = state["loop_guard"].copy()
    guard["turn_count"] += 1

    return {
        "memory_context": memory_context,
        "context_usage_ratio": usage,
        "needs_compaction": needs_compaction,
        "loop_guard": guard
    }


# ─── agent_node ───
async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    """LLM 호출 노드"""
    model = get_configured_model(config)

    # 시스템 프롬프트 조립 (AGENTS.md + 메모리 + 프로젝트 컨텍스트)
    system_prompt = assemble_system_prompt(
        agents_md=load_agents_md(state["project_root"]),
        memory_context=state.get("memory_context"),
        todos=state.get("todos", []),
        active_subagents=state.get("active_subagents", [])
    )

    # LLM 호출
    response = await model.ainvoke(
        [SystemMessage(content=system_prompt)] + state["messages"]
    )

    # 비용 추적
    guard = state["loop_guard"].copy()
    guard["total_cost_usd"] += calculate_cost(response)

    # 빈 턴 감지 (도구 호출 없이 text만 반환)
    if not response.tool_calls:
        guard["consecutive_empty_turns"] += 1
    else:
        guard["consecutive_empty_turns"] = 0
        guard["last_tool_calls"] = [tc["name"] for tc in response.tool_calls]

    return {
        "messages": [response],
        "loop_guard": guard
    }


# ─── tool_execution_node ───
async def tool_execution_node(state: AgentState, config: RunnableConfig) -> dict:
    """도구 실행 노드 — 동시성 파티셔닝 적용"""
    last_message = state["messages"][-1]
    tool_calls = last_message.tool_calls

    results = []

    # 도구를 안전/위험으로 분류하여 배치 실행
    batches = partition_tool_calls(tool_calls)

    for batch in batches:
        if batch.is_concurrent:
            # 안전한 도구: 병렬 실행
            batch_results = await asyncio.gather(
                *[execute_single_tool(tc, state, config) for tc in batch.calls],
                return_exceptions=True
            )
        else:
            # 위험한 도구: 순차 실행
            batch_results = []
            for tc in batch.calls:
                result = await execute_single_tool(tc, state, config)
                batch_results.append(result)

        results.extend(batch_results)

    # 결과를 ToolMessage로 변환
    tool_messages = [
        to_tool_message(tc, result)
        for tc, result in zip(tool_calls, results)
    ]

    return {"messages": tool_messages}


# ─── stall_recovery_node ───
async def stall_recovery_node(state: AgentState, config: RunnableConfig) -> dict:
    """LLM 멈춤 시 복구 노드"""
    guard = state["loop_guard"].copy()
    attempts = guard["stall_recovery_attempts"]

    if attempts == 0:
        # 1차: 넛지 메시지 삽입
        nudge = HumanMessage(content=(
            "[시스템] 이전 시도에서 진전이 없었습니다. "
            "다른 접근 방식을 시도하거나, 구체적인 도움이 필요하면 ask_user를 사용해주세요."
        ))
        guard["stall_recovery_attempts"] = 1
        guard["consecutive_empty_turns"] = 0
        return {"messages": [nudge], "loop_guard": guard}

    elif attempts == 1:
        # 2차: 모델 전환
        # (ConfigurableModelMiddleware가 폴백 모델로 전환)
        guard["stall_recovery_attempts"] = 2
        guard["consecutive_empty_turns"] = 0
        return {"loop_guard": guard}

    else:
        # 3차: 사용자에게 방향 질문 (interrupt)
        from langgraph.types import interrupt
        response = interrupt({
            "type": "stall_recovery",
            "message": "에이전트가 진전을 이루지 못하고 있습니다. 방향을 알려주시겠어요?",
            "context": summarize_recent_attempts(state)
        })
        guard["stall_recovery_attempts"] = 0
        guard["consecutive_empty_turns"] = 0
        return {
            "messages": [HumanMessage(content=response)],
            "loop_guard": guard
        }
```

### 3.4 그래프 시각화

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  preprocess  │  메모리 검색, 컨텍스트 체크
                  └──────┬───────┘
                         │
                         ▼
              ┌──────────────────────┐
         ┌───>│       agent          │  LLM 호출 (시스템 프롬프트 + 메시지)
         │    └──────────┬───────────┘
         │               │
         │               ▼
         │    ┌──────────────────────┐
         │    │   route_after_agent  │  조건부 라우팅
         │    └──┬────┬────┬────┬───┘
         │       │    │    │    │
         │       │    │    │    └──────────────── ▶ END (end_turn/한도 초과)
         │       │    │    │
         │       │    │    └─── ▶ stall_recovery ─┐
         │       │    │                            │
         │       │    └──────── ▶ compact ─────────┤
         │       │                                 │
         │       ▼                                 │
         │  ┌────────────┐                         │
         │  │   tools     │  도구 실행 (배치/병렬)  │
         │  └─────┬──────┘                         │
         │        │                                │
         │        ▼                                │
         │  ┌──────────────┐                       │
         │  │ postprocess  │  메모리 추출, 비용 갱신│
         │  └──────┬───────┘                       │
         │         │                               │
         └─────────┘◀──────────────────────────────┘
```

---

## 4. 서브에이전트 구현

### 4.1 SubAgentManager

```python
class SubAgentManager:
    """서브에이전트 생명주기 관리자"""

    def __init__(self, config: AgentConfig, store, checkpointer):
        self._active: dict[str, SubAgentState] = {}
        self._config = config
        self._store = store
        self._checkpointer = checkpointer
        self._semaphore = asyncio.Semaphore(config.max_concurrent_subagents)

    async def spawn(
        self,
        agent_type: str,
        instruction: str,
        model_override: Optional[str] = None,
        tools_override: Optional[list] = None,
        max_turns: int = 30,
        timeout: int = 300
    ) -> str:
        """서브에이전트 동적 생성"""
        agent_id = f"sa-{uuid4().hex[:8]}"

        async with self._semaphore:
            # 1. 서브에이전트 타입에 맞는 설정 로드
            type_config = SUBAGENT_TYPES[agent_type]
            tools = tools_override or type_config.default_tools
            model = model_override or type_config.default_model

            # 2. 격리된 StateGraph 생성
            subagent_graph = create_subagent_graph(
                model=create_model(model),
                tools=tools,
                max_turns=max_turns
            )

            # 3. 상태 등록
            self._active[agent_id] = SubAgentState(
                agent_id=agent_id,
                agent_type=agent_type,
                status="running",
                instruction=instruction,
                created_at=datetime.now()
            )

            # 4. 비동기 실행 (타임아웃 적용)
            try:
                result = await asyncio.wait_for(
                    subagent_graph.ainvoke(
                        {"messages": [HumanMessage(content=instruction)]},
                        config={"configurable": {"thread_id": agent_id}}
                    ),
                    timeout=timeout
                )
                self._active[agent_id]["status"] = "completed"
                self._active[agent_id]["result"] = extract_final_answer(result)
            except asyncio.TimeoutError:
                self._active[agent_id]["status"] = "timed_out"
                self._active[agent_id]["result"] = "작업이 시간 제한을 초과했습니다."
            except Exception as e:
                self._active[agent_id]["status"] = "failed"
                self._active[agent_id]["error"] = str(e)
            finally:
                self._active[agent_id]["completed_at"] = datetime.now()

        return agent_id

    async def abort(self, agent_id: str) -> None:
        """서브에이전트 강제 중단"""
        if agent_id in self._active:
            self._active[agent_id]["status"] = "aborted"

    def get_status(self, agent_id: str) -> Optional[SubAgentState]:
        return self._active.get(agent_id)

    def list_active(self) -> list[SubAgentState]:
        return [s for s in self._active.values() if s["status"] == "running"]

    def cleanup(self) -> None:
        """완료/실패된 서브에이전트 정리"""
        completed = [
            aid for aid, state in self._active.items()
            if state["status"] in ("completed", "failed", "aborted", "timed_out")
        ]
        for aid in completed:
            del self._active[aid]
```

### 4.2 task() 도구 구현

```python
from langchain.tools import tool

@tool
async def task(
    agent: str = "general",
    instruction: str = "",
    model: Optional[str] = None
) -> str:
    """서브에이전트에게 작업을 위임합니다.

    Args:
        agent: 서브에이전트 타입 (general, explorer, coder, researcher, reviewer, planner)
        instruction: 위임할 작업의 상세 설명. 충분히 구체적으로 작성해야 합니다.
        model: 선택적 모델 오버라이드 (예: haiku로 경량 작업)
    """
    manager = get_subagent_manager()  # 싱글톤
    agent_id = await manager.spawn(
        agent_type=agent,
        instruction=instruction,
        model_override=model
    )

    # 완료 대기 (spawn 내부에서 이미 대기)
    state = manager.get_status(agent_id)
    if state["status"] == "completed":
        return state["result"]
    else:
        return f"서브에이전트 실행 실패: {state.get('error', state['status'])}"
```

---

## 5. 메모리 시스템 구현

### 5.1 CompositeBackend 구성

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore  # 개발용
# from langgraph.store.postgres import PostgresStore  # 프로덕션

def create_memory_backend(config):
    """3-Tier 메모리 백엔드 구성"""

    store = InMemoryStore()  # 또는 PostgresStore(...)

    return CompositeBackend(
        # 기본: 세션 내 임시 파일 (Tier 1)
        default=StateBackend(config),
        routes={
            # /memories/ 경로: 장기 메모리 (Tier 3)
            "/memories/": StoreBackend(config),
            # /project/ 경로: 프로젝트 메모리 (Tier 3)
            "/project/": StoreBackend(config),
        }
    ), store
```

### 5.2 MemoryExtractor (Auto-Dream)

```python
class MemoryExtractor:
    """대화에서 자동으로 메모리를 추출하는 비동기 프로세서"""

    EXTRACTION_PROMPT = """
    다음 대화 구간을 분석하여 장기 메모리로 저장할 가치가 있는 정보를 추출하세요.

    추출 대상:
    1. user: 사용자의 역할, 전문성, 선호도
    2. feedback: 작업 방식에 대한 교정이나 확인
    3. domain: 도메인 지식 (비즈니스 로직, 용어, 규칙)
    4. project: 프로젝트 고유 컨텍스트 (아키텍처 결정, 컨벤션)

    추출하지 않을 것:
    - 코드 자체 (git/파일에서 확인 가능)
    - 일시적 작업 상태
    - 이미 메모리에 있는 중복 정보

    기존 메모리:
    {existing_memories}

    대화 구간:
    {conversation_segment}

    JSON 배열로 반환:
    [{"type": "...", "name": "...", "description": "...", "content": "...", "tags": [...]}]
    빈 배열 []도 유효합니다 (추출할 것이 없을 때).
    """

    def __init__(self, model, store: MemoryStore):
        self._model = model
        self._store = store
        self._last_extraction_token_count = 0
        self._last_extraction_tool_count = 0

    async def maybe_extract(self, messages: list, current_token_count: int, tool_count: int) -> None:
        """임계값 확인 후 비차단 추출"""
        token_delta = current_token_count - self._last_extraction_token_count
        tool_delta = tool_count - self._last_extraction_tool_count

        if token_delta < 3000 and tool_delta < 3:
            return  # 임계값 미달

        # 비차단 비동기 추출
        asyncio.create_task(self._extract(messages))
        self._last_extraction_token_count = current_token_count
        self._last_extraction_tool_count = tool_count

    async def _extract(self, messages: list) -> None:
        """실제 추출 로직"""
        existing = await self._store.list_all_summaries()
        recent_segment = messages[-20:]  # 최근 20개 메시지만

        response = await self._model.ainvoke([
            SystemMessage(content=self.EXTRACTION_PROMPT.format(
                existing_memories=existing,
                conversation_segment=format_messages(recent_segment)
            ))
        ])

        entries = parse_json_response(response.content)
        for entry in entries:
            # 중복 감지 (semantic similarity)
            existing_similar = await self._store.find_similar(entry["content"])
            if existing_similar:
                # 기존 메모리 갱신
                await self._store.update(existing_similar.id, entry)
            else:
                # 새 메모리 생성
                await self._store.create(entry)

        # 인덱스 갱신
        await self._store.rebuild_index()
```

### 5.3 MemoryRetriever

```python
class MemoryRetriever:
    """쿼리 시 관련 메모리를 검색하여 컨텍스트에 주입"""

    def __init__(self, store: MemoryStore):
        self._store = store

    async def retrieve(self, query: str, project_slug: Optional[str] = None) -> str:
        """관련 메모리를 검색하여 프롬프트용 문자열로 반환"""

        # 1. 항상 포함: user, feedback 메모리
        always_include = await self._store.get_by_types(["user", "feedback"])

        # 2. 프로젝트 메모리 (현재 프로젝트)
        project_memories = []
        if project_slug:
            project_memories = await self._store.get_by_namespace(
                ("memory", "project", project_slug)
            )

        # 3. 쿼리 관련 도메인 메모리 (keyword/semantic 검색)
        domain_memories = await self._store.search(
            query=query,
            types=["domain"],
            limit=5
        )

        # 4. 참조 메모리 (쿼리에 외부 시스템 언급 시)
        reference_memories = await self._store.search(
            query=query,
            types=["reference"],
            limit=3
        )

        # 포맷팅
        sections = []
        if always_include:
            sections.append("## 사용자 프로필 & 피드백\n" + format_memories(always_include))
        if project_memories:
            sections.append("## 프로젝트 컨텍스트\n" + format_memories(project_memories))
        if domain_memories:
            sections.append("## 관련 도메인 지식\n" + format_memories(domain_memories))
        if reference_memories:
            sections.append("## 참조 정보\n" + format_memories(reference_memories))

        return "\n\n".join(sections) if sections else ""
```

---

## 6. 미들웨어 스택

미들웨어는 에이전트 생성 시 LangGraph 그래프의 노드 전후에 로직을 삽입한다.

```python
def create_agent(config: AgentConfig):
    """미들웨어가 적용된 에이전트 생성"""

    # 기본 컴포넌트
    model = create_model(config.model)
    checkpointer = create_checkpointer(config)
    store = create_store(config)
    tools = assemble_tools(config)

    # 미들웨어 적용 순서 (중요!)
    # 1. 모델 미들웨어: 런타임 모델 전환
    model = ConfigurableModelMiddleware(model, config.fallback_model)

    # 2. 메모리 미들웨어: 자동 추출/주입
    memory_extractor = MemoryExtractor(model, MemoryStore(store))
    memory_retriever = MemoryRetriever(MemoryStore(store))

    # 3. 서브에이전트 매니저
    subagent_manager = SubAgentManager(config, store, checkpointer)

    # 4. 그래프 조립
    graph = create_agent_graph(
        model=model,
        tools=tools + [create_task_tool(subagent_manager)],
        checkpointer=checkpointer,
        store=store,
        config=config
    )

    return graph
```

### 미들웨어 실행 순서

```
Request (사용자 메시지)
    │
    ▼
[1] HookMiddleware.pre_session()
[2] PermissionMiddleware.check()
[3] MemoryRetriever.retrieve()  → 시스템 프롬프트에 메모리 주입
[4] ContextManager.check_usage()  → 컴팩션 필요 시 트리거
    │
    ▼
[Agent Node - LLM 호출]
    │
    ▼
[5] StallDetector.check()  → 멈춤 감지
[6] ToolExecutor.execute()  → 도구 실행 (권한 검사 포함)
    │
    ├── HookMiddleware.pre_tool_use()
    ├── PermissionMiddleware.check_tool()
    ├── [도구 실행]
    ├── HookMiddleware.post_tool_use()
    └── MemoryExtractor.maybe_extract()  → 비차단 메모리 추출
    │
    ▼
[Response 또는 다음 턴]
```

---

## 7. 도구 실행 파이프라인

### 7.1 동시성 파티셔닝 구현

```python
from dataclasses import dataclass

@dataclass
class ToolBatch:
    calls: list  # ToolCall 리스트
    is_concurrent: bool  # 병렬 실행 가능 여부

CONCURRENT_SAFE_TOOLS = frozenset({
    "read_file", "grep", "glob", "ls", "web_search", "fetch_url"
})

def partition_tool_calls(tool_calls: list) -> list[ToolBatch]:
    """도구 호출을 안전/위험 배치로 분할"""
    batches = []
    current_safe = []

    for tc in tool_calls:
        is_safe = tc["name"] in CONCURRENT_SAFE_TOOLS

        if is_safe:
            current_safe.append(tc)
        else:
            # 이전 안전 배치 플러시
            if current_safe:
                batches.append(ToolBatch(calls=current_safe, is_concurrent=True))
                current_safe = []
            # 위험 도구는 단독 배치
            batches.append(ToolBatch(calls=[tc], is_concurrent=False))

    # 남은 안전 배치 플러시
    if current_safe:
        batches.append(ToolBatch(calls=current_safe, is_concurrent=True))

    return batches
```

### 7.2 단일 도구 실행 흐름

```python
async def execute_single_tool(
    tool_call: dict,
    state: AgentState,
    config: RunnableConfig
) -> str:
    """단일 도구 실행 (훅 + 권한 + 타임아웃)"""

    tool_name = tool_call["name"]
    tool_input = tool_call["args"]

    # 1. Pre-hook
    hook_result = await run_hooks("pre_tool_use", tool_name, tool_input)
    if hook_result and not hook_result.get("allow", True):
        return f"훅에 의해 차단됨: {hook_result.get('message', '')}"

    # 2. 권한 확인
    permission = check_permission(tool_name, tool_input, config)
    if permission == "deny":
        return f"권한 거부: {tool_name}"
    elif permission == "ask":
        # interrupt로 사용자에게 묻기
        from langgraph.types import interrupt
        approval = interrupt({
            "type": "permission_request",
            "tool": tool_name,
            "input": tool_input
        })
        if not approval:
            return f"사용자가 {tool_name} 실행을 거부했습니다."

    # 3. 도구 실행 (타임아웃 적용)
    tool_impl = get_tool(tool_name)
    timeout = TOOL_TIMEOUTS.get(tool_name, 30)

    try:
        result = await asyncio.wait_for(
            tool_impl.ainvoke(tool_input),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        result = f"도구 실행 시간 초과 ({timeout}초)"
    except Exception as e:
        result = f"도구 실행 에러: {str(e)}"

    # 4. 대형 결과 처리
    if len(str(result)) > MAX_TOOL_RESULT_SIZE:
        result = truncate_and_persist(result, tool_name)

    # 5. Post-hook
    await run_hooks("post_tool_use", tool_name, tool_input, result)

    return result
```

---

## 8. 시스템 프롬프트 조립

```python
def assemble_system_prompt(
    agents_md: str,
    memory_context: Optional[str],
    todos: list[dict],
    active_subagents: list[SubAgentInfo],
    cwd: str,
    project_root: str
) -> str:
    """시스템 프롬프트를 동적으로 조립"""

    sections = []

    # 1. 기본 에이전트 행동 규칙 (AGENTS.md에서 핵심만 추출)
    sections.append(CORE_SYSTEM_PROMPT)

    # 2. 프로젝트 컨텍스트
    sections.append(f"""
# 환경
- 작업 디렉토리: {cwd}
- 프로젝트 루트: {project_root}
- 현재 날짜: {datetime.now().isoformat()}
""")

    # 3. 메모리 컨텍스트 (관련 장기 메모리)
    if memory_context:
        sections.append(f"""
# 메모리 (이전 세션에서 학습한 정보)
{memory_context}
""")

    # 4. 활성 태스크
    if todos:
        sections.append(format_todos(todos))

    # 5. 활성 서브에이전트
    if active_subagents:
        sections.append(format_active_subagents(active_subagents))

    # 6. AGENTS.md (프로젝트 규칙)
    if agents_md:
        sections.append(f"""
# 프로젝트 규칙 (AGENTS.md)
{agents_md[:8000]}  # 토큰 예산 내에서
""")

    return "\n\n".join(sections)
```

---

## 9. 의존성

```toml
[project]
name = "sds-ax"
requires-python = ">=3.11"

[project.dependencies]
# 핵심
langgraph = ">=0.4"
langchain = ">=0.3"
langchain-core = ">=0.3"
langchain-anthropic = ">=0.3"    # Claude 모델
langchain-openai = ">=0.3"       # OpenAI/OpenRouter 호환
deepagents = ">=0.1"             # DeepAgents 프레임워크

# 저장소
langgraph-checkpoint-sqlite = ">=2.0"  # 세션 체크포인트
# langgraph-checkpoint-postgres = ">=2.0"  # 프로덕션

# TUI
textual = ">=3.0"               # 터미널 UI

# 도구
tavily-python = ">=0.5"          # 웹 검색

# MCP
langchain-mcp-adapters = ">=0.1" # MCP 통합

# 유틸리티
pydantic = ">=2.0"
python-dotenv = ">=1.0"
httpx = ">=0.27"
rich = ">=13.0"                  # 터미널 출력 포맷팅

[project.scripts]
sds-ax = "sds_ax.cli:main"
```

---

## 10. 구현 로드맵

### Phase 1: 기초 골격 (MVP)
- [ ] 프로젝트 구조 생성 (pyproject.toml, 패키지 구조)
- [ ] AgentState 정의 (core/state.py)
- [ ] 기본 StateGraph 구성 (core/graph.py)
- [ ] LLM 프로바이더 초기화 (core/models.py — OpenRouter)
- [ ] 기본 Agentic Loop (agent → tools → agent 사이클)
- [ ] 내장 도구 4종 (read_file, write_file, edit_file, bash)
- [ ] CLI 진입점 (cli.py — 비대화형 모드 먼저)
- [ ] 기본 설정 로더 (config/)

### Phase 2: 루프 강화
- [ ] 도구 실행 파이프라인 (권한, 훅, 타임아웃)
- [ ] 동시성 파티셔닝 (안전/위험 배치)
- [ ] Stall Detector (멈춤 감지 + 복구)
- [ ] 모델 폴백 체인
- [ ] 컨텍스트 관리 (Auto-Compact)
- [ ] 나머지 내장 도구 (grep, glob, ls, web_search, fetch_url)
- [ ] 에러 복구 (재시도, Withhold & Recover)

### Phase 3: 메모리 시스템
- [ ] MemoryStore (LangGraph Store 래퍼)
- [ ] MemoryExtractor (Auto-Dream)
- [ ] MemoryRetriever (쿼리 시 관련 메모리 검색)
- [ ] MEMORY_INDEX.md 자동 관리
- [ ] CompositeBackend 라우팅

### Phase 4: 서브에이전트
- [ ] SubAgentManager (생명주기 관리)
- [ ] task() 도구 구현
- [ ] 내장 서브에이전트 타입 (explorer, coder, researcher, reviewer, planner)
- [ ] 서브에이전트 모니터링 (진행 상황 스트리밍)
- [ ] 동시 서브에이전트 제한 (세마포어)

### Phase 5: TUI & UX
- [ ] Textual App 메인 (ui/app.py)
- [ ] 메시지 렌더링, 스트리밍
- [ ] 입력 프롬프트 (슬래시 커맨드 지원)
- [ ] 서브에이전트/태스크 패널
- [ ] 상태 바 (비용, 모델, 세션)
- [ ] 슬래시 커맨드 구현

### Phase 6: 확장성
- [ ] 스킬 시스템 (발견/로드/실행)
- [ ] MCP 도구 통합
- [ ] 훅 시스템
- [ ] 세션 관리 (복원, 목록, 내보내기)
- [ ] LangSmith 트레이싱 통합
