# SDS-AX: Advanced CLI Agent

> **프로젝트**: SDS-AX (SDS Agent eXtended)  
> **스택**: Python 3.11+ / LangGraph / LangChain / DeepAgents CLI  
> **목표**: Claude Code, Codex 수준의 고도화된 CLI 전용 자율 에이전트

---

## 1. 에이전트 정체성

SDS-AX는 터미널에서 동작하는 **자율 소프트웨어 엔지니어 에이전트**다.
사용자의 자연어 지시를 받아 코드를 읽고, 수정하고, 실행하며, 필요 시 서브에이전트를 동적으로 생성하여 복잡한 작업을 병렬 처리한다.

### 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **안전성 우선** | 파괴적 작업은 반드시 사용자 승인 후 실행 |
| **루프 불멸** | Agentic Loop이 어떤 상황에서도 깨지지 않는 방어적 설계 |
| **점진적 개인화** | 사용할수록 사용자와 프로젝트에 맞춤화되는 장기 메모리 |
| **동적 위임** | 서브에이전트를 필요 시 생성하고, 작업 후 소멸시키는 동적 오케스트레이션 |
| **투명성** | 에이전트의 판단 근거, 비용, 진행 상황을 항상 사용자에게 노출 |

---

## 2. 실행 모드

```
sds-ax
  │
  ├── 대화형 모드 (기본)
  │   └── Textual TUI → 스트리밍 응답, 도구 실행, 서브에이전트 모니터링
  │
  ├── 비대화형 모드 (-n "task")
  │   └── 단일 작업 실행 → 결과 출력 → 종료
  │
  ├── 서버 모드 (--serve)
  │   └── LangGraph API 서버 → 프로그래밍 방식 접근
  │
  └── 코디네이터 모드 (--coordinator)
      └── 리더 에이전트가 워커 서브에이전트를 오케스트레이션
```

---

## 3. 도구(Tool) 시스템

### 3.1 내장 도구

| 도구 | 타입 | 설명 | 병렬 안전 |
|------|------|------|-----------|
| **read_file** | 읽기 전용 | 파일 읽기 (이미지/PDF 포함) | O |
| **write_file** | 파괴적 | 새 파일 작성 | X |
| **edit_file** | 파괴적 | 파일 인라인 편집 (문자열 치환) | X |
| **bash** | 파괴적 | 셸 명령 실행, 샌드박스 지원 | X |
| **grep** | 읽기 전용 | ripgrep 기반 패턴 검색 | O |
| **glob** | 읽기 전용 | 파일 패턴 매칭 | O |
| **ls** | 읽기 전용 | 디렉토리 목록 | O |
| **web_search** | 읽기 전용 | Tavily 웹 검색 | O |
| **fetch_url** | 읽기 전용 | URL 콘텐츠 가져오기 | O |
| **ask_user** | UI | 사용자에게 질문 (interrupt) | X |
| **write_todos** | 상태 변경 | 태스크 계획 관리 | X |
| **task** | 오케스트레이션 | 서브에이전트 생성/위임 | X |

### 3.2 도구 실행 파이프라인

```
LLM이 tool_use 반환
    │
    ▼
[1] 도구 조회 (이름 → 구현체 매핑)
[2] 입력 검증 (Pydantic/Zod 스키마)
[3] PreToolUse 훅 실행 (차단/수정 가능)
[4] 권한 확인
    ├── allow_list 규칙 매칭 → 허용
    ├── deny_list 규칙 매칭 → 거부
    ├── auto_approve=True → 허용
    └── 기본값 → 사용자에게 승인 요청 (interrupt)
[5] 도구 실행 (타임아웃 적용)
[6] 결과 매핑 (ToolMessage 형식)
[7] 대형 결과 처리 (임계값 초과 시 파일로 영속화)
[8] PostToolUse 훅 실행
[9] 텔레메트리 기록
```

### 3.3 동시성 파티셔닝 (Claude Code 패턴 차용)

```python
# 안전한 도구: 병렬 실행
CONCURRENT_SAFE = {"read_file", "grep", "glob", "ls", "web_search", "fetch_url"}

# 위험한 도구: 순차 실행
SEQUENTIAL_ONLY = {"write_file", "edit_file", "bash", "task"}

# 실행 예시:
# [read_file, grep, glob]  → Batch 1: 병렬
# [edit_file]               → Batch 2: 순차
# [read_file, read_file]    → Batch 3: 병렬
# [bash]                    → Batch 4: 순차
```

### 3.4 MCP 도구 확장

```
도구 발견 순서:
[1] 내장 도구 (항상 우선)
[2] ~/.deepagents/.mcp.json (사용자 전역)
[3] .deepagents/.mcp.json (프로젝트)
[4] .mcp.json (프로젝트 루트)

이름 충돌 시 내장 도구가 우선한다.
```

---

## 4. 동적 서브에이전트 시스템

### 4.1 설계 철학

서브에이전트는 **매번 동적으로** 생성되고, 작업 완료 후 소멸한다.
Claude Code의 AgentTool + TaskSystem 패턴과 DeepAgents의 SubAgentMiddleware를 결합한다.

### 4.2 생명주기

```
┌─────────────────────────────────────────────────────────┐
│                서브에이전트 생명주기                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [생성] task(agent="researcher", instruction="...")      │
│    │                                                    │
│    ├── 새 StateGraph 인스턴스 생성                       │
│    ├── 격리된 메시지 컨텍스트                             │
│    ├── 전용 도구 세트 할당                                │
│    ├── 모델 오버라이드 가능 (경량 작업 → haiku)           │
│    └── AbortController 연결                              │
│    │                                                    │
│  [작업] 자율 실행                                        │
│    │                                                    │
│    ├── 독립된 Agentic Loop 내에서 도구 호출               │
│    ├── 메인 에이전트 컨텍스트와 격리                      │
│    ├── 진행 상황은 메인에 스트리밍                        │
│    └── 타임아웃/최대 턴 제한 적용                         │
│    │                                                    │
│  [보고] 결과 반환                                        │
│    │                                                    │
│    ├── 최종 결과를 메인 에이전트에 반환                    │
│    └── 컨텍스트 정리 (메모리 해제)                        │
│    │                                                    │
│  [소멸] 리소스 정리                                      │
│    │                                                    │
│    ├── AbortController 정리                               │
│    └── 상태 → 'completed' 또는 'failed'                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.3 상태 관리

```python
class SubAgentState:
    agent_id: str           # 고유 ID (예: "sa-abc123")
    agent_type: str         # "general" | "researcher" | "coder" | custom
    status: Literal[
        "spawning",         # 생성 중
        "running",          # 실행 중
        "waiting_approval", # HITL 대기
        "completed",        # 정상 완료
        "failed",           # 실패
        "aborted",          # 사용자/시스템에 의해 중단
        "timed_out"         # 타임아웃
    ]
    instruction: str        # 위임된 작업 설명
    created_at: datetime
    completed_at: Optional[datetime]
    result: Optional[str]   # 최종 결과
    error: Optional[str]    # 에러 정보
    turn_count: int         # 실행된 턴 수
    max_turns: int          # 최대 턴 제한 (기본 30)
    timeout_seconds: int    # 타임아웃 (기본 300초)
```

### 4.4 내장 서브에이전트 타입

| 타입 | 용도 | 기본 모델 | 전용 도구 |
|------|------|-----------|-----------|
| **general** | 범용 (메인과 동일 도구) | 메인과 동일 | 전체 |
| **explorer** | 코드베이스 탐색 | haiku | read_file, grep, glob, ls |
| **coder** | 코드 작성/수정 | sonnet | read_file, write_file, edit_file, bash |
| **researcher** | 웹 조사 | sonnet | web_search, fetch_url, read_file |
| **reviewer** | 코드 리뷰 | opus | read_file, grep, glob |
| **planner** | 계획 수립 | opus | read_file, grep, glob, write_todos |

### 4.5 동적 생성 예시

```python
# 메인 에이전트가 LLM 판단으로 서브에이전트 호출
# tool_call: task(agent="explorer", instruction="src/ 디렉토리에서 인증 관련 코드 찾기")

# 런타임에 동적 생성:
subagent = create_subagent(
    agent_type="explorer",
    instruction="src/ 디렉토리에서 인증 관련 코드를 찾아 구조를 정리해줘",
    model_override="haiku",  # 경량 모델로 비용 최적화
    tools=EXPLORER_TOOLS,
    max_turns=10,
    timeout=120
)
result = await subagent.ainvoke(...)
# 결과 반환 후 subagent는 GC에 의해 소멸
```

---

## 5. 장기 메모리 / 지식 저장 체계

### 5.1 메모리 아키텍처 (3-Tier)

```
┌─────────────────────────────────────────────────────────┐
│                    메모리 아키텍처                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Tier 1: 세션 메모리 (Ephemeral)                        │
│  ├── StateBackend (LangGraph state)                     │
│  ├── 현재 대화 컨텍스트                                  │
│  ├── 활성 서브에이전트 상태                               │
│  └── 세션 종료 시 소멸                                   │
│                                                         │
│  Tier 2: 스레드 메모리 (Persistent per thread)           │
│  ├── Checkpointer (SQLite/PostgreSQL)                   │
│  ├── 대화 이력 및 체크포인트                              │
│  ├── 세션 간 대화 복원 가능                              │
│  └── thread_id 기반 접근                                 │
│                                                         │
│  Tier 3: 장기 메모리 (Cross-session)                    │
│  ├── StoreBackend (LangGraph Store)                     │
│  ├── 개발자 개인화 메모리                                │
│  ├── 도메인 지식 저장소                                  │
│  ├── 프로젝트 맞춤 메모리                                │
│  └── 모든 세션에서 접근 가능                             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 5.2 장기 메모리 스키마 (Tier 3)

Claude Code의 Auto-Dream 패턴을 차용하여, 사용자가 입력하는 도메인 지식을 자동으로 추출하고 체계적으로 저장한다.

#### 메모리 타입

| 타입 | namespace | 설명 | 자동 추출 |
|------|-----------|------|-----------|
| **user** | `("memory", "user")` | 개발자 역할, 선호, 전문성 | O |
| **feedback** | `("memory", "feedback")` | 작업 방식 교정/확인 | O |
| **domain** | `("memory", "domain")` | 도메인 지식 (비즈니스 로직, 용어) | O |
| **project** | `("memory", "project", "{project_slug}")` | 프로젝트별 맞춤 지식 | O |
| **reference** | `("memory", "reference")` | 외부 시스템 참조 | 수동 |

#### 메모리 파일 구조

```
~/.deepagents/memory/
├── MEMORY_INDEX.md          # 메모리 인덱스 (항상 시스템 프롬프트에 포함)
├── user/
│   ├── role.json            # 사용자 역할/전문성
│   └── preferences.json     # 작업 선호도
├── feedback/
│   ├── coding_style.json    # 코딩 스타일 피드백
│   └── workflow.json        # 워크플로 피드백
├── domain/
│   ├── {topic_slug}.json    # 도메인 지식 엔트리
│   └── ...
├── project/
│   ├── {project_slug}/
│   │   ├── context.json     # 프로젝트 컨텍스트
│   │   ├── architecture.json # 아키텍처 결정
│   │   └── conventions.json  # 코딩 컨벤션
│   └── ...
└── reference/
    └── external.json        # 외부 시스템 참조
```

#### 메모리 엔트리 형식

```json
{
  "id": "mem-uuid",
  "type": "domain",
  "name": "결제 시스템 도메인 모델",
  "description": "PG사 연동 결제 플로우의 핵심 엔티티와 상태 전이",
  "content": "...",
  "created_at": "2026-04-06T10:00:00Z",
  "updated_at": "2026-04-06T10:00:00Z",
  "source": "auto_extracted | user_explicit",
  "confidence": 0.85,
  "access_count": 12,
  "last_accessed": "2026-04-06T10:00:00Z",
  "tags": ["payment", "domain-model"],
  "project": "my-payment-service"
}
```

### 5.3 자동 메모리 추출 (Auto-Dream)

```
세션 진행 중
    │
    ▼
[임계값 확인]
├── 최소 메시지 토큰: 5,000
├── 최소 도구 호출 간격: 3회
└── 최소 토큰 간격: 3,000
    │
    ▼ (임계값 초과 시)
[포크된 서브에이전트에서 추출] (비차단)
    │
    ├── 사용자 선호/피드백 감지
    │   "이렇게 하지 마" → feedback 메모리 저장
    │   "나는 시니어 개발자야" → user 메모리 저장
    │
    ├── 도메인 지식 감지
    │   "우리 시스템에서 주문은 3단계를 거쳐..." → domain 메모리 저장
    │   "이 API는 반드시 idempotent해야 해" → domain 메모리 저장
    │
    ├── 프로젝트 컨텍스트 감지
    │   "이 프로젝트는 MSA로 되어있고..." → project 메모리 저장
    │   "배포 파이프라인이 freeze됐어" → project 메모리 저장
    │
    └── 기존 메모리와 병합/갱신
        ├── 중복 감지 (semantic similarity)
        ├── 충돌 시 최신 정보 우선
        └── MEMORY_INDEX.md 갱신
```

### 5.4 메모리 활용 시점

```
매 쿼리 시작 시
    │
    ▼
[1] MEMORY_INDEX.md 로드 (시스템 프롬프트에 포함)
[2] 현재 쿼리와 관련된 메모리 검색 (semantic search)
[3] 관련 메모리를 컨텍스트에 주입
[4] 프로젝트 메모리는 현재 cwd 기준으로 자동 필터
    │
    ▼
쿼리 처리 시
    │
    ├── feedback 메모리 → 응답 스타일/접근 방식 조정
    ├── user 메모리 → 설명 수준/복잡도 맞춤
    ├── domain 메모리 → 도메인 용어/규칙 적용
    ├── project 메모리 → 프로젝트 컨벤션 준수
    └── reference 메모리 → 외부 시스템 참조 시 활용
```

---

## 6. Agentic Loop 방어 설계

### 6.1 핵심 루프 구조

```
사용자 입력
    │
    ▼
┌────────────────────────────────────────────┐
│  AGENTIC LOOP (AsyncGenerator 패턴)        │
│                                            │
│  while not terminal:                       │
│    ├── [전처리] 메시지 정규화, 컨텍스트 압축 │
│    ├── [API 호출] LLM 스트리밍              │
│    ├── [에러 복구] 재시도/폴백              │
│    ├── [도구 실행] 도구 파이프라인          │
│    ├── [후처리] 메모리 갱신, 비용 추적      │
│    └── [판단] end_turn → 종료 / tool_use → 계속│
│                                            │
│  return Terminal                           │
└────────────────────────────────────────────┘
```

### 6.2 방어 계층

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: API 호출 방어                               │
│ ├── 지수 백오프 재시도 (최대 3회)                     │
│ ├── 타임아웃 (단일 호출 60초, 전체 턴 300초)         │
│ ├── Rate Limit → 대기 후 재시도                      │
│ ├── prompt_too_long → 리액티브 컴팩션                │
│ ├── max_output_tokens → 자동 continuation            │
│ └── 연결 실패 → 폴백 모델 전환                       │
├─────────────────────────────────────────────────────┤
│ Layer 2: 도구 실행 방어                               │
│ ├── 도구별 타임아웃 (bash: 120초, 기타: 30초)        │
│ ├── 실패 시 에러를 ToolMessage로 반환 (LLM이 복구)   │
│ ├── 무한 반복 감지 (동일 도구+입력 3회 → 중단 경고)  │
│ └── 대형 결과 자동 트렁케이션                        │
├─────────────────────────────────────────────────────┤
│ Layer 3: 루프 수준 방어                               │
│ ├── 최대 턴 제한 (기본 50턴)                         │
│ ├── 최대 비용 제한 (세션당 $5 기본)                   │
│ ├── 무한 루프 감지 (진전 없는 5턴 연속 → 경고)       │
│ ├── 컨텍스트 윈도우 소진 → 자동 컴팩션               │
│ └── 세션 상태 매 턴 영속화 (중단 복원 가능)          │
├─────────────────────────────────────────────────────┤
│ Layer 4: 모델 폴백 체인                               │
│ ├── Primary: 설정된 주 모델                          │
│ ├── Secondary: 폴백 모델 (비용 또는 안정성 우선)     │
│ └── Emergency: 최소 모델 (연결 유지 목적)            │
├─────────────────────────────────────────────────────┤
│ Layer 5: 프로세스 수준 방어                           │
│ ├── SIGINT (Ctrl+C) → 현재 턴 중단, 상태 보존       │
│ ├── SIGTERM → Graceful Shutdown (체크포인트 저장)     │
│ ├── 예상치 못한 예외 → 로깅 + 세션 복원 포인트 제공   │
│ └── OOM → 컨텍스트 비상 압축 후 속행                  │
└─────────────────────────────────────────────────────┘
```

### 6.3 LLM 멈춤 대응 전략

```python
class StallDetector:
    """LLM이 멈추거나 비생산적 루프에 빠졌을 때 감지하고 복구"""

    # 전략 1: 타임아웃 기반 감지
    api_call_timeout: int = 60          # 단일 API 호출
    streaming_stall_timeout: int = 30    # 스트리밍 중 청크 간 간격

    # 전략 2: 진전 감지
    max_consecutive_empty_turns: int = 3  # 도구 호출 없는 연속 턴
    max_identical_tool_calls: int = 3     # 동일 도구+입력 반복

    # 전략 3: 복구 액션
    recovery_actions = [
        "retry_with_nudge",      # "이전 시도가 실패했습니다. 다른 접근을 시도해주세요."
        "switch_model",          # 폴백 모델로 전환
        "compact_and_retry",     # 컨텍스트 압축 후 재시도
        "ask_user_for_guidance", # 사용자에게 방향 질문
        "graceful_stop"          # 안전하게 멈추고 진행 상황 보고
    ]
```

### 6.4 멀티 모델 환경 고려사항

```
모델 전환 시 주의사항:
├── 시스템 프롬프트 호환성 확인
│   └── 모델별 프롬프트 변형 매핑 (예: tool_use 포맷 차이)
├── 도구 스키마 호환성
│   └── 모델별 지원 도구 필터링
├── 컨텍스트 윈도우 차이
│   └── 폴백 모델의 윈도우가 작으면 사전 컴팩션
└── 토큰 카운팅 차이
    └── 모델별 토크나이저 사용
```

---

## 7. 권한(Permission) 시스템

### 7.1 권한 모드

| 모드 | 동작 | 사용 사례 |
|------|------|----------|
| **default** | 파괴적 도구 사용 시 사용자에게 묻기 | 일반 사용 |
| **auto_approve** | 모든 도구 자동 허용 | 신뢰 환경, CI/CD |
| **read_only** | 읽기 도구만 허용, 나머지 거부 | 탐색/리뷰 전용 |
| **plan_only** | 읽기 + 계획 도구만 허용 | 계획 수립 단계 |
| **shell_confirm** | 셸만 확인, 나머지 자동 | 파일 편집은 신뢰 |

### 7.2 권한 규칙 설정

```json
// .deepagents/settings.json
{
  "permissions": {
    "mode": "default",
    "allow": [
      "bash(npm install *)",
      "bash(npm run *)",
      "bash(git status)",
      "bash(git diff *)",
      "edit_file(src/**/*.py)",
      "write_file(tests/**/*.py)"
    ],
    "deny": [
      "bash(rm -rf *)",
      "bash(git push --force *)",
      "write_file(.env*)",
      "edit_file(*.lock)"
    ]
  }
}
```

### 7.3 권한 판정 파이프라인

```
도구 호출 요청
    │
    ▼
[1] deny 규칙 매칭 → 즉시 거부
[2] allow 규칙 매칭 → 즉시 허용
[3] 도구의 is_read_only → True면 허용
[4] 모드별 판정
    ├── auto_approve → 허용
    ├── read_only → 거부
    └── default → interrupt(사용자에게 묻기)
```

---

## 8. 훅(Hook) 시스템

```json
// ~/.deepagents/hooks.json
{
  "pre_tool_use": [
    {
      "if": "bash(git push *)",
      "command": ["echo", "{\"allow\": false, \"message\": \"Push는 수동으로 해주세요\"}"]
    }
  ],
  "post_tool_use": [
    {
      "command": ["notify-send", "SDS-AX", "도구 실행 완료"]
    }
  ],
  "session_start": [
    {
      "command": ["bash", "-c", "echo 'Session started' >> ~/.deepagents/audit.log"]
    }
  ]
}
```

### 훅 이벤트

| 이벤트 | 시점 | 차단 가능 |
|--------|------|-----------|
| session_start | 세션 시작 | X |
| session_end | 세션 종료 | X |
| pre_tool_use | 도구 실행 전 | O (allow/deny 반환) |
| post_tool_use | 도구 실행 후 | X |
| pre_compact | 컨텍스트 압축 전 | X |
| memory_update | 메모리 갱신 시 | O (거부 가능) |

---

## 9. 스킬(Skill) 시스템

### 9.1 스킬 발견 순서

```
[1] 내장 스킬    → deepagents_cli/built_in_skills/
[2] 사용자 스킬  → ~/.deepagents/skills/
[3] 프로젝트 스킬 → .deepagents/skills/ 또는 .agents/skills/
```

### 9.2 SKILL.md 형식

```markdown
---
name: my-skill
description: "스킬의 구체적인 설명 (에이전트가 언제 사용할지 판단하는 기준)"
---

# 스킬 이름

## 개요
스킬의 목적과 사용 시점.

## 지시사항
에이전트가 따라야 할 단계별 가이드.

## 예시
좋은/나쁜 사용 예시.
```

### 9.3 스킬 호출 흐름

```
사용자: "/my-skill arg1 arg2" 또는 LLM이 자동 판단
    │
    ▼
스킬 발견 → SKILL.md 로드
    │
    ▼
포크된 서브에이전트 컨텍스트에서 실행
    ├── 격리된 메시지 이력
    ├── SKILL.md 내용이 시스템 프롬프트에 주입
    └── 결과를 메인 에이전트에 반환
```

---

## 10. 컨텍스트 관리

### 10.1 컨텍스트 윈도우 전략

```
컨텍스트 사용량 모니터링
    │
    ├── < 50% : 정상 운영
    ├── 50-70% : Auto-Compact 준비
    ├── 70-85% : Auto-Compact 실행 (이전 대화 요약)
    ├── 85-95% : Reactive Compact (공격적 압축)
    └── > 95% : Emergency Compact (최소 컨텍스트만 유지)
```

### 10.2 Auto-Compact 동작

```
[1] 오래된 도구 실행 결과를 요약으로 교체
[2] 반복적인 대화를 핵심만 추출
[3] 메모리에 이미 저장된 정보는 참조로 대체
[4] 시스템 프롬프트와 최근 N턴은 보존
```

---

## 11. 슬래시 커맨드

| 커맨드 | 설명 |
|--------|------|
| `/help` | 도움말 표시 |
| `/clear` | 대화 이력 초기화 |
| `/compact` | 수동 컨텍스트 압축 |
| `/model` | 모델 변경 |
| `/cost` | 현재 세션 비용 표시 |
| `/memory` | 메모리 조회/관리 |
| `/tasks` | 활성 서브에이전트/태스크 목록 |
| `/resume` | 이전 세션 복원 |
| `/config` | 설정 변경 |
| `/skills` | 사용 가능한 스킬 목록 |
| `/plan` | 계획 모드 진입 (읽기 전용) |
| `/diff` | 현재 세션의 변경 사항 표시 |
| `/export` | 대화 내보내기 |

---

## 12. 설정 체계

### 12.1 설정 우선순위

```
[1] CLI 인수              (최우선)
[2] 환경 변수
[3] .deepagents/settings.json  (프로젝트)
[4] ~/.deepagents/settings.json  (사용자)
[5] 기본값                (최하위)
```

### 12.2 주요 설정

```json
{
  "model": "anthropic/claude-sonnet-4-5-20250929",
  "fallback_model": "anthropic/claude-haiku-4-5-20251001",
  "api_base": "https://openrouter.ai/api/v1",

  "permissions": {
    "mode": "default",
    "allow": [],
    "deny": []
  },

  "memory": {
    "auto_extract": true,
    "extraction_threshold_tokens": 5000,
    "max_memory_entries": 500
  },

  "loop": {
    "max_turns": 50,
    "max_cost_usd": 5.0,
    "tool_timeout_seconds": 120,
    "api_timeout_seconds": 60,
    "stall_detection": true
  },

  "subagents": {
    "max_concurrent": 5,
    "default_max_turns": 30,
    "default_timeout_seconds": 300
  },

  "context": {
    "auto_compact_threshold": 0.7,
    "reactive_compact_threshold": 0.85,
    "emergency_compact_threshold": 0.95
  }
}
```

---

## 13. 텔레메트리 및 관측성

```
LangSmith 트레이싱
    ├── 매 API 호출 추적 (모델, 토큰, 지연시간)
    ├── 도구 실행 추적 (이름, 입력, 출력, 소요시간)
    ├── 서브에이전트 추적 (생성, 실행, 결과)
    ├── 메모리 연산 추적 (읽기, 쓰기, 검색)
    └── 에러/복구 이벤트 추적

세션 통계
    ├── 총 API 비용
    ├── 모델별 토큰 사용량
    ├── 도구 호출 횟수/성공률
    ├── 서브에이전트 생성/완료 횟수
    └── 세션 소요 시간
```

---

## 14. 핵심 설계 패턴 (구현 시 준수)

### 패턴 1: AsyncGenerator Streaming
모든 쿼리 루프는 AsyncGenerator로 구현하여 메모리 효율적 스트리밍을 보장한다.

### 패턴 2: Withhold & Recover
복구 가능한 에러는 사용자에게 즉시 노출하지 않고 자동 복구를 시도한다.

### 패턴 3: Immutable State
LangGraph State는 reducer를 통해서만 갱신하며, 직접 변이를 금지한다.

### 패턴 4: Lazy Import
순환 의존을 런타임 지연 로딩으로 해결한다.

### 패턴 5: Interruption Resilience
매 턴 시작 전 체크포인트를 저장하여 중단 시에도 상태를 복원할 수 있다.

### 패턴 6: Concurrent Partitioning
안전한 도구는 병렬로, 위험한 도구는 순차로 실행하여 처리량과 안전성을 동시에 확보한다.

### 패턴 7: CompositeBackend Routing
파일 경로 기반으로 ephemeral/persistent 스토리지를 자동 라우팅한다.

---

## 부록: 참고 아키텍처

- **Claude Code**: 쿼리 루프, 도구 실행 파이프라인, 권한 시스템, 동시성 파티셔닝, Auto-Dream 메모리
- **Codex**: 동적 서브에이전트 생성/소멸, 멀티 모델 전략
- **DeepAgents CLI**: LangGraph 기반 에이전트 하네스, 미들웨어 스택, CompositeBackend, 스킬 시스템
