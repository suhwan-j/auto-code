#!/usr/bin/env python3
"""Automated interactive testing for Totoro.

Simulates multi-turn conversations using the same code path as
interactive mode (_stream_with_hitl), without needing prompt_toolkit.

Usage:
    python tests/interactive_test.py                    # Run all scenarios
    python tests/interactive_test.py --scenario simple  # Run specific scenario
"""
import os
import sys
import time
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_agent():
    """Create Totoro agent (same as CLI startup)."""
    from totoro.config.settings import load_config, ensure_api_keys
    config = load_config(cli_overrides={"permissions": {"mode": "auto_approve"}})
    from totoro.core.agent import create_totoro_agent
    agent, checkpointer, store, _ = create_totoro_agent(config)
    return agent, checkpointer, config


def run_turn(agent, message: str, invoke_config: dict, verbose: bool = False) -> bool:
    """Run a single conversation turn. Returns True if agent responded."""
    from totoro.cli import _stream_with_hitl
    print(f"\n{'='*60}")
    print(f"  USER: {message}")
    print(f"{'='*60}\n")
    success = _stream_with_hitl(
        agent, message, invoke_config,
        auto_approve=True, verbose=verbose,
    )
    print()
    return success


# ─── Test Scenarios ───

SCENARIOS = {}


def scenario(name, description=""):
    """Decorator to register a test scenario."""
    def wrapper(fn):
        SCENARIOS[name] = {"fn": fn, "desc": description}
        return fn
    return wrapper


@scenario("simple", "Basic single-turn Q&A")
def test_simple(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-simple")
    invoke_config = sm.get_invoke_config(session.session_id)

    results = []
    results.append(run_turn(agent, "안녕! 1+1은 뭐야?", invoke_config))
    return results


@scenario("multi-turn", "Multi-turn conversation with context")
def test_multi_turn(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-multi-turn")
    invoke_config = sm.get_invoke_config(session.session_id)

    results = []
    results.append(run_turn(agent, "내 이름은 토토로야. 기억해.", invoke_config))
    results.append(run_turn(agent, "내 이름이 뭐라고 했지?", invoke_config))
    return results


@scenario("file-read", "Read and analyze a file")
def test_file_read(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-file-read")
    invoke_config = sm.get_invoke_config(session.session_id)

    results = []
    results.append(run_turn(
        agent,
        "pyproject.toml 파일을 읽고 이 프로젝트 이름과 버전을 알려줘",
        invoke_config,
    ))
    return results


@scenario("subagent", "Task requiring subagent delegation")
def test_subagent(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-subagent")
    invoke_config = sm.get_invoke_config(session.session_id)

    results = []
    results.append(run_turn(
        agent,
        "totoro/utils.py 파일의 코드를 분석해서 개선점을 알려줘. orchestrate_tool로 mei에게 맡겨.",
        invoke_config,
    ))
    return results


@scenario("create-file", "Create a small file")
def test_create_file(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-create-file")
    invoke_config = sm.get_invoke_config(session.session_id)

    test_dir = "/tmp/totoro-test"
    os.makedirs(test_dir, exist_ok=True)

    results = []
    results.append(run_turn(
        agent,
        f"{test_dir}/hello.py 경로에 'Hello World'를 출력하는 Python 스크립트를 만들어줘",
        invoke_config,
    ))

    # Verify
    hello_path = os.path.join(test_dir, "hello.py")
    if os.path.exists(hello_path):
        print(f"  [PASS] File created: {hello_path}")
        with open(hello_path) as f:
            print(f"  Content: {f.read()[:200]}")
    else:
        print(f"  [FAIL] File not created: {hello_path}")

    return results


@scenario("complex-app", "Complex multi-file application")
def test_complex_app(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-complex-app")
    invoke_config = sm.get_invoke_config(session.session_id)

    test_dir = "/tmp/totoro-test-app"
    os.makedirs(test_dir, exist_ok=True)

    results = []
    results.append(run_turn(
        agent,
        f"{test_dir} 경로에 간단한 Python Flask TODO API를 만들어줘. "
        f"app.py (라우트), models.py (데이터 모델), requirements.txt 3개 파일로.",
        invoke_config,
    ))

    # Verify files
    for fname in ["app.py", "models.py", "requirements.txt"]:
        fpath = os.path.join(test_dir, fname)
        if os.path.exists(fpath):
            print(f"  [PASS] {fname} created")
        else:
            print(f"  [FAIL] {fname} missing")

    return results


@scenario("error-recovery", "Test error handling and recovery")
def test_error_recovery(agent, config):
    from totoro.session.manager import SessionManager
    sm = SessionManager()
    session = sm.create_session(description="test-error-recovery")
    invoke_config = sm.get_invoke_config(session.session_id)

    results = []
    # Ask to read non-existent file
    results.append(run_turn(
        agent,
        "/tmp/this-file-does-not-exist-xyz123.py 파일을 읽어줘",
        invoke_config,
    ))
    return results


# ─── Runner ───

def main():
    parser = argparse.ArgumentParser(description="Totoro interactive test runner")
    parser.add_argument("--scenario", "-s", help="Run specific scenario")
    parser.add_argument("--list", "-l", action="store_true", help="List scenarios")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--timeout", type=int, default=300, help="Per-scenario timeout (seconds)")
    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for name, info in SCENARIOS.items():
            print(f"  {name:20s} — {info['desc']}")
        return

    print("=" * 60)
    print("  Totoro Interactive Test Runner")
    print("=" * 60)

    agent, checkpointer, config = create_agent()

    scenarios = (
        {args.scenario: SCENARIOS[args.scenario]} if args.scenario
        else SCENARIOS
    )

    total = len(scenarios)
    passed = 0
    failed = 0

    for i, (name, info) in enumerate(scenarios.items(), 1):
        print(f"\n{'#'*60}")
        print(f"  Scenario {i}/{total}: {name}")
        print(f"  {info['desc']}")
        print(f"{'#'*60}")

        start = time.time()
        try:
            results = info["fn"](agent, config)
            elapsed = time.time() - start

            if all(results):
                print(f"\n  [PASS] {name} ({elapsed:.1f}s)")
                passed += 1
            else:
                print(f"\n  [FAIL] {name} — agent did not respond ({elapsed:.1f}s)")
                failed += 1
        except KeyboardInterrupt:
            print(f"\n  [SKIP] {name} — interrupted")
            failed += 1
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  [ERROR] {name} — {type(e).__name__}: {e} ({elapsed:.1f}s)")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'='*60}")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
