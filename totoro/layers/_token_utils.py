"""Token estimation utilities shared across layers.

Provides a weighted estimator that accounts for CJK characters
(Korean, Japanese, Chinese) which typically consume 2-3 tokens per character,
unlike Latin text which averages ~4 characters per token.
"""
import re

# CJK Unified Ideographs + Hangul Syllables + Katakana/Hiragana ranges
_CJK_RE = re.compile(
    r"[\u3000-\u303f"   # CJK punctuation
    r"\u3040-\u309f"    # Hiragana
    r"\u30a0-\u30ff"    # Katakana
    r"\u4e00-\u9fff"    # CJK Unified Ideographs
    r"\uac00-\ud7af"    # Hangul Syllables
    r"\uf900-\ufaff"    # CJK Compatibility Ideographs
    r"]"
)


def estimate_tokens(messages: list) -> int:
    """Estimate token count from messages with CJK-aware weighting.

    - Latin/ASCII text: ~4 chars per token (standard heuristic)
    - CJK characters (Korean, Japanese, Chinese): ~1.5 chars per token
      (each character typically becomes 2-3 BPE tokens)

    This avoids under-counting for CJK-heavy conversations, which would
    cause context compaction to trigger too late.
    """
    total = 0
    for m in messages:
        content = getattr(m, "content", None)
        if content is None:
            continue
        if isinstance(content, list):
            # Multi-block content (tool_use, text blocks, etc.)
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            text = " ".join(text_parts)
        else:
            text = str(content)
        total += _estimate_text_tokens(text)
    return total


def _estimate_text_tokens(text: str) -> int:
    """Estimate tokens for a single text string."""
    if not text:
        return 0
    cjk_chars = len(_CJK_RE.findall(text))
    non_cjk_chars = len(text) - cjk_chars
    # CJK: ~2 tokens per char, Latin: ~0.25 tokens per char
    return int(cjk_chars * 2 + non_cjk_chars / 4)
