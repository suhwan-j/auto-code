"""SDS-AX CLI entry point."""
import sys
import time
import json
import argparse

from langgraph.types import Command


def main():
    parser = argparse.ArgumentParser(description="SDS-AX: CLI Coding Agent")
    parser.add_argument("-n", "--non-interactive", type=str, metavar="TASK", help="Run single task non-interactively")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve all tool executions (no HITL)")
    parser.add_argument("--model", type=str, help="Override model name")
    parser.add_argument("--resume", type=str, metavar="SESSION_ID", help="Resume a previous session")
    args = parser.parse_args()

    from sds_ax.config.settings import load_config, ensure_api_keys
    ensure_api_keys()

    cli_overrides = {}
    if args.auto_approve:
        cli_overrides["permissions"] = {"mode": "auto_approve"}
    if args.model:
        cli_overrides["model"] = args.model

    config = load_config(cli_overrides=cli_overrides)

    from sds_ax.core.agent import create_sds_ax_agent
    agent, checkpointer, store = create_sds_ax_agent(config)

    if args.non_interactive:
        session_id = f"task-{int(time.time())}"
        invoke_config = {"configurable": {"thread_id": session_id}}
        _stream_with_hitl(agent, args.non_interactive, invoke_config, auto_approve=args.auto_approve)
    elif args.resume:
        session_id = args.resume
        invoke_config = {"configurable": {"thread_id": session_id}}
        print(f"Resuming session: {session_id}")
        _run_interactive(agent, invoke_config, auto_approve=args.auto_approve)
    else:
        session_id = f"session-{int(time.time())}"
        invoke_config = {"configurable": {"thread_id": session_id}}
        _run_interactive(agent, invoke_config, auto_approve=args.auto_approve)


def _run_interactive(agent, invoke_config: dict, auto_approve: bool = False):
    """Interactive mode main loop."""
    from sds_ax.commands.registry import handle_slash_command

    print("SDS-AX ready. Type /help for commands, /exit to quit.")
    print(f"Session: {invoke_config['configurable']['thread_id']}")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            result = handle_slash_command(user_input, agent, invoke_config)
            if result == "__exit__":
                break
            if result:
                print(result)
            continue

        _stream_with_hitl(agent, user_input, invoke_config, auto_approve=auto_approve)
        print()  # blank line after response


def _stream_with_hitl(agent, user_input: str, config: dict, auto_approve: bool = False):
    """Stream agent response with HITL interrupt handling."""
    input_payload = {"messages": [{"role": "user", "content": user_input}]}

    while True:
        # Stream tokens
        interrupt_info = _do_stream(agent, input_payload, config)

        if interrupt_info is None:
            # No interrupt, done
            break

        # Handle interrupt
        if auto_approve:
            decisions = [{"type": "approve"} for _ in interrupt_info]
        else:
            decisions = _collect_hitl_decisions(interrupt_info)

        # Resume with decisions
        input_payload = Command(resume={"decisions": decisions})


def _do_stream(agent, input_payload, config: dict) -> list | None:
    """Stream tokens to stdout. Returns interrupt info if interrupted, None otherwise."""
    interrupt_info = None

    try:
        for chunk in agent.stream(input_payload, config=config, stream_mode="messages"):
            # stream_mode="messages" yields (message_chunk, metadata) tuples
            if isinstance(chunk, tuple) and len(chunk) == 2:
                token, metadata = chunk
                if hasattr(token, "content") and token.content:
                    print(token.content, end="", flush=True)
            # Some implementations yield dicts
            elif isinstance(chunk, dict):
                if "__interrupt__" in chunk:
                    interrupt_info = chunk["__interrupt__"]
    except Exception as e:
        # Fallback: try invoke if streaming doesn't work
        try:
            result = agent.invoke(input_payload, config=config)
            if "__interrupt__" in result:
                interrupt_info = result["__interrupt__"]
            else:
                messages = result.get("messages", [])
                if messages:
                    last = messages[-1]
                    content = getattr(last, "content", str(last))
                    if content:
                        print(content, flush=True)
        except Exception as e2:
            print(f"\nError: {e2}", file=sys.stderr)

    # Check for interrupt via get_state as fallback
    if interrupt_info is None:
        try:
            state = agent.get_state(config)
            if state and state.next:
                # There's a pending interrupt
                if hasattr(state, 'tasks') and state.tasks:
                    interrupt_info = state.tasks
        except Exception:
            pass

    print()  # newline after streaming
    return interrupt_info


def _collect_hitl_decisions(interrupts) -> list[dict]:
    """Prompt user for HITL decisions."""
    decisions = []
    for intr in interrupts:
        value = intr.value if hasattr(intr, 'value') else intr
        tool_name = value.get("tool", "unknown") if isinstance(value, dict) else str(value)
        tool_input = value.get("input", "") if isinstance(value, dict) else ""
        message = value.get("message", "") if isinstance(value, dict) else ""

        print(f"\n[HITL] {tool_name}")
        if tool_input:
            print(f"  Input: {tool_input}")
        if message:
            print(f"  {message}")
        print("  (a)pprove / (r)eject / (e)dit ?")

        choice = input("  > ").strip().lower()

        if choice in ("a", "approve", "y", "yes", ""):
            decisions.append({"type": "approve"})
        elif choice in ("e", "edit"):
            edited = input("  Enter edited args (JSON): ").strip()
            try:
                edited_args = json.loads(edited)
                decisions.append({
                    "type": "edit",
                    "edited_action": {"name": tool_name, "args": edited_args},
                })
            except json.JSONDecodeError:
                print("  Invalid JSON, rejecting.")
                decisions.append({"type": "reject"})
        else:
            decisions.append({"type": "reject"})

    return decisions
