"""T-031: Memory → Instructions builder.

Converts user memory preferences into NotebookLM audio generation instructions.
"""

from typing import Any


_BASE_INSTRUCTIONS = [
    "한국어로 진행해주세요.",
    "10분 분량으로 만들어주세요.",
]


def build_instructions(memory: dict[str, Any] | None) -> str:
    """Build NotebookLM audio generation instructions from user memory.

    Args:
        memory: User memory dict from Firestore (may be None or empty).

    Returns:
        Formatted instruction string for NotebookLM audio generation.
    """
    parts: list[str] = list(_BASE_INSTRUCTIONS)

    if not memory:
        return "\n".join(parts)

    interests = memory.get("interests", "")
    if interests:
        parts.append(f"관심 분야: {interests}")

    tone = memory.get("preferredTone", "")
    if tone:
        parts.append(f"톤: {tone}")

    depth = memory.get("preferredDepth", "")
    if depth:
        parts.append(f"깊이: {depth}")

    custom = memory.get("customInstructions", "")
    if custom:
        parts.append(custom)

    # Feedback signal: if 3+ "bad" ratings in last 10, add encouragement
    feedback_history = memory.get("feedbackHistory", [])
    recent = feedback_history[-10:] if feedback_history else []
    bad_count = sum(1 for f in recent if f.get("rating") == "bad")
    if bad_count >= 3:
        parts.append("더 흥미롭게 만들어주세요.")

    return "\n".join(parts)
