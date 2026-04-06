"""LLM provider initialization."""


def create_lightweight_model(model_name: str = "claude-haiku-4-5-20251001"):
    """Create a lightweight LLM for Auto-Dream memory extraction.

    Uses ChatAnthropic for Anthropic models.
    """
    try:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name, max_tokens=1024)
    except Exception:
        return None
