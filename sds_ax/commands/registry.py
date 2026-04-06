"""Slash command registry and handler."""
import time


def handle_slash_command(user_input: str, agent, invoke_config: dict) -> str | None:
    """Parse and execute a slash command. Returns output string, '__exit__', or None."""
    parts = user_input.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handlers = {
        "/help": _cmd_help,
        "/exit": _cmd_exit,
        "/quit": _cmd_exit,
        "/clear": _cmd_clear,
        "/model": _cmd_model,
        "/session": _cmd_session,
    }

    handler = handlers.get(cmd)
    if handler is None:
        return f"Unknown command: {cmd}. Type /help for available commands."

    return handler(args, agent, invoke_config)


def _cmd_help(args, agent, config) -> str:
    return """Available commands:
  /help     - Show this help message
  /exit     - Exit the CLI
  /clear    - Clear conversation (start new session)
  /model    - Show current model
  /session  - Show current session ID"""


def _cmd_exit(args, agent, config) -> str:
    return "__exit__"


def _cmd_clear(args, agent, config) -> str:
    new_session = f"session-{int(time.time())}"
    config["configurable"]["thread_id"] = new_session
    return f"Conversation cleared. New session: {new_session}"


def _cmd_model(args, agent, config) -> str:
    return f"Current model: (configured in agent)"


def _cmd_session(args, agent, config) -> str:
    return f"Session ID: {config['configurable']['thread_id']}"
