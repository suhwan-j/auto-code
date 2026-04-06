"""Stall detection — detect when agent is stuck in empty turns."""
from langgraph.types import interrupt
from langchain_core.messages import HumanMessage


class StallDetector:
    """Detect agent stalls and escalate recovery."""

    def __init__(self, max_empty_turns: int = 3):
        self._max_empty_turns = max_empty_turns
        self._consecutive_empty = 0
        self._recovery_stage = 0

    def check(self, last_message) -> dict | None:
        """Check if agent is stalled. Returns recovery action or None."""
        has_tool_calls = hasattr(last_message, "tool_calls") and last_message.tool_calls

        if has_tool_calls:
            self._consecutive_empty = 0
            self._recovery_stage = 0
            return None

        self._consecutive_empty += 1

        if self._consecutive_empty < self._max_empty_turns:
            return None

        self._recovery_stage += 1

        if self._recovery_stage == 1:
            self._consecutive_empty = 0
            return {
                "action": "inject_message",
                "message": HumanMessage(content=(
                    "[System] No progress detected. "
                    "Try a different approach, or use ask_user if you need guidance."
                )),
            }
        elif self._recovery_stage == 2:
            self._consecutive_empty = 0
            return {"action": "switch_model"}
        elif self._recovery_stage == 3:
            self._consecutive_empty = 0
            return {"action": "ask_user"}
        else:
            return {"action": "stop", "message": "Agent stopped after multiple stall recovery attempts."}

    def reset(self):
        self._consecutive_empty = 0
        self._recovery_stage = 0
