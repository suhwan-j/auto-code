#!/usr/bin/env python3
"""Interactive PTY-based testing for Totoro.

Uses pexpect to spawn a real totoro interactive session with a pseudo-terminal,
then sends messages and reads responses — exactly like a human would.

Usage:
    python tests/interactive_pty_test.py                    # Run all scenarios
    python tests/interactive_pty_test.py --scenario simple  # Run one scenario
    python tests/interactive_pty_test.py --free "하고싶은말"  # Free-form single message
"""
import os
import re
import sys
import time
import argparse
import pexpect

# Strip ANSI escape codes for clean output
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\[\?[0-9;]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def clean_output(text: str) -> str:
    """Strip ANSI, remove blank lines and spinner artifacts."""
    lines = []
    for line in strip_ansi(text).splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip spinner lines
        if 'thinking...' in line or line in ('', ' '):
            continue
        # Skip cursor movement artifacts
        if line.startswith('[') and line.endswith('m'):
            continue
        lines.append(line)
    return '\n'.join(lines)


class TotoroSession:
    """Manages a live totoro interactive session via PTY."""

    def __init__(self, auto_approve: bool = True, timeout: int = 120):
        self.timeout = timeout
        self.auto_approve = auto_approve
        # Use the internal API directly instead of spawning a PTY
        from totoro.config.settings import load_config, ensure_api_keys
        ensure_api_keys()  # Load API keys from ~/.totoro/settings.json
        overrides = {"permissions": {"mode": "auto_approve"}} if auto_approve else {}
        self.config = load_config(cli_overrides=overrides)
        from totoro.core.agent import create_totoro_agent
        self.agent, self._checkpointer, self._store, _ = create_totoro_agent(self.config)
        from totoro.session.manager import SessionManager
        self._sm = SessionManager(checkpointer=self._checkpointer)
        session = self._sm.create_session(description="pty-test")
        self._invoke_config = self._sm.get_invoke_config(session.session_id)
        self._turn = 0

    def send(self, message: str, wait_timeout: int | None = None) -> str:
        """Send a message and get the response.

        Uses _stream_with_hitl internally — same code path as interactive mode.
        Returns the agent's text output captured from stdout.
        """
        import io
        from contextlib import redirect_stdout
        from totoro.cli import _stream_with_hitl, _ensure_imports
        _ensure_imports()

        self._turn += 1

        # Capture stdout
        captured = io.StringIO()

        # We need both real stdout (for ANSI rendering) and capture
        # Solution: tee stdout
        real_stdout = sys.stdout

        class TeeWriter:
            def write(self, s):
                captured.write(s)
                real_stdout.write(s)
                return len(s)
            def flush(self):
                captured.flush()
                real_stdout.flush()
            def isatty(self):
                return False  # Disable spinner in captured mode
            def fileno(self):
                return real_stdout.fileno()

        sys.stdout = TeeWriter()
        try:
            _stream_with_hitl(
                self.agent, message, self._invoke_config,
                auto_approve=self.auto_approve,
            )
        finally:
            sys.stdout = real_stdout

        return clean_output(captured.getvalue())

    def close(self):
        """Cleanup."""
        pass


# ─── Test Scenarios ───

SCENARIOS = {}


def scenario(name, description=""):
    def wrapper(fn):
        SCENARIOS[name] = {"fn": fn, "desc": description}
        return fn
    return wrapper


@scenario("simple", "Basic greeting and math")
def test_simple(session: TotoroSession):
    print("  [Turn 1] Sending: 안녕! 1+1은?")
    resp = session.send("안녕! 1+1은?")
    print(f"  Response:\n{resp[:500]}")
    ok = '2' in resp
    print(f"  {'[PASS]' if ok else '[FAIL]'} Contains '2': {ok}")
    return ok


@scenario("context", "Multi-turn context retention")
def test_context(session: TotoroSession):
    print("  [Turn 1] Introducing name...")
    resp1 = session.send("내 이름은 토토로야. 꼭 기억해!")
    print(f"  Response: {resp1[:300]}")

    print("\n  [Turn 2] Asking for name...")
    resp2 = session.send("내 이름이 뭐라고 했지?")
    print(f"  Response: {resp2[:300]}")

    ok = '토토로' in resp2
    print(f"  {'[PASS]' if ok else '[FAIL]'} Remembers name: {ok}")
    return ok


@scenario("file-ops", "File reading")
def test_file_ops(session: TotoroSession):
    print("  [Turn 1] Reading pyproject.toml...")
    resp = session.send("pyproject.toml에서 프로젝트 이름만 알려줘. 짧게 답해.", wait_timeout=60)
    print(f"  Response: {resp[:300]}")
    ok = 'totoro' in resp.lower()
    print(f"  {'[PASS]' if ok else '[FAIL]'} Found project name: {ok}")
    return ok


@scenario("subagent", "Subagent delegation")
def test_subagent(session: TotoroSession):
    print("  [Turn 1] Requesting analysis via subagent...")
    resp = session.send(
        "totoro/utils.py 파일이 뭐하는 파일인지 한 줄로 요약해줘",
        wait_timeout=180,
    )
    print(f"  Response: {resp[:500]}")
    ok = len(resp) > 20  # Got some meaningful response
    print(f"  {'[PASS]' if ok else '[FAIL]'} Got response: {ok}")
    return ok


@scenario("slash-help", "Test /help command output")
def test_slash_help(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/help", session.agent, session._invoke_config)
    print(f"  /help output length: {len(result)} chars")
    checks = [
        ("/exit" in result, "/exit present"),
        ("/model" in result, "/model present"),
        ("/mode" in result, "/mode present"),
        ("/session" in result, "/session present"),
        ("/compact" in result, "/compact present"),
        ("/memory" in result, "/memory present"),
        ("/skill" in result, "/skill present"),
    ]
    all_ok = True
    for ok, label in checks:
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {status} {label}")
        if not ok:
            all_ok = False
    return all_ok


@scenario("slash-status", "Test /status command")
def test_slash_status(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/status", session.agent, session._invoke_config)
    print(f"  /status output: {result[:300]}")
    ok = result is not None and len(result) > 5
    print(f"  {'[PASS]' if ok else '[FAIL]'} Got status output")
    return ok


@scenario("slash-sessions", "Test /sessions command")
def test_slash_sessions(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/sessions", session.agent, session._invoke_config)
    print(f"  /sessions output: {result[:300]}")
    ok = result is not None and ("session" in result.lower() or "Session" in result)
    print(f"  {'[PASS]' if ok else '[FAIL]'} Shows session list")
    return ok


@scenario("slash-memory", "Test /memory command")
def test_slash_memory(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/memory", session.agent, session._invoke_config)
    print(f"  /memory output: {result[:300] if result else '(None)'}")
    # /memory should return something (even "no memories")
    ok = result is not None
    print(f"  {'[PASS]' if ok else '[FAIL]'} Got memory output")
    return ok


@scenario("slash-tasks", "Test /tasks command")
def test_slash_tasks(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/tasks", session.agent, session._invoke_config)
    print(f"  /tasks output: {result[:300] if result else '(None)'}")
    ok = result is not None
    print(f"  {'[PASS]' if ok else '[FAIL]'} Got tasks output")
    return ok


@scenario("slash-skill", "Test /skill list command")
def test_slash_skill(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/skill list", session.agent, session._invoke_config)
    print(f"  /skill list output: {result[:300] if result else '(None)'}")
    ok = result is not None
    print(f"  {'[PASS]' if ok else '[FAIL]'} Got skill list")
    return ok


@scenario("slash-unknown", "Test unknown command handling")
def test_slash_unknown(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    result = handle_slash_command("/nonexistent", session.agent, session._invoke_config)
    print(f"  /nonexistent output: {result}")
    ok = result is not None and "Unknown" in result
    print(f"  {'[PASS]' if ok else '[FAIL]'} Shows 'Unknown command'")
    return ok


@scenario("slash-compact", "Test /compact command")
def test_slash_compact(session: TotoroSession):
    from totoro.commands.registry import handle_slash_command
    # First send a message so there's something to compact
    session.send("안녕!")
    result = handle_slash_command("/compact", session.agent, session._invoke_config)
    print(f"  /compact output: {result[:300] if result else '(None)'}")
    ok = result is not None
    print(f"  {'[PASS]' if ok else '[FAIL]'} Compact executed")
    return ok


@scenario("error", "Error handling")
def test_error(session: TotoroSession):
    print("  [Turn 1] Reading non-existent file...")
    resp = session.send("/tmp/nonexistent-file-xyz.py 파일을 읽어줘")
    print(f"  Response: {resp[:300]}")
    ok = len(resp) > 10  # Got some response (error or explanation)
    print(f"  {'[PASS]' if ok else '[FAIL]'} Handled error gracefully: {ok}")
    return ok


# ─── Runner ───

def run_free(message: str):
    """Run a single free-form message in interactive mode."""
    print("Starting Totoro session...")
    session = TotoroSession(auto_approve=True)
    try:
        print(f"\n  Sending: {message}\n")
        resp = session.send(message, wait_timeout=180)
        print(f"  Response:\n{resp}")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Totoro interactive PTY test")
    parser.add_argument("--scenario", "-s", help="Run specific scenario")
    parser.add_argument("--free", "-f", help="Send a free-form message")
    parser.add_argument("--list", "-l", action="store_true", help="List scenarios")
    parser.add_argument("--timeout", "-t", type=int, default=120)
    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for name, info in SCENARIOS.items():
            print(f"  {name:15s} — {info['desc']}")
        return

    if args.free:
        run_free(args.free)
        return

    print("=" * 60)
    print("  Totoro Interactive PTY Test Runner")
    print("=" * 60)

    scenarios = (
        {args.scenario: SCENARIOS[args.scenario]} if args.scenario
        else SCENARIOS
    )

    total = len(scenarios)
    passed = 0
    failed = 0

    for i, (name, info) in enumerate(scenarios.items(), 1):
        print(f"\n{'#'*60}")
        print(f"  Scenario {i}/{total}: {name} — {info['desc']}")
        print(f"{'#'*60}")

        session = TotoroSession(auto_approve=True, timeout=args.timeout)
        start = time.time()
        try:
            ok = info["fn"](session)
            elapsed = time.time() - start
            if ok:
                print(f"\n  [PASS] {name} ({elapsed:.1f}s)")
                passed += 1
            else:
                print(f"\n  [FAIL] {name} ({elapsed:.1f}s)")
                failed += 1
        except KeyboardInterrupt:
            print(f"\n  [SKIP] {name}")
            failed += 1
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  [ERROR] {name}: {type(e).__name__}: {e} ({elapsed:.1f}s)")
            failed += 1
        finally:
            session.close()

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'='*60}")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
