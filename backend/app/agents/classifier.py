"""AI-vs-human PR classifier using heuristics and LLM.

Fast path uses text-pattern heuristics to short-circuit trivial and
high-risk cases. Ambiguous PRs go through the LLM for a full verdict.
"""

import json
import re
from typing import Optional

import structlog
from litellm import acompletion

from app.agents.prompts import CLASSIFIER_SYSTEM_PROMPT
from app.config import settings

logger = structlog.get_logger()

# Heuristic markers of AI-generated code
AI_MARKERS = [
    r"Here.?s (what|the|a|an|how|why)",
    r"I hope this (helps|finds you well)",
    r"Certainly!",
    r"Let me (explain|walk you through|break this down)",
    r"As an AI",
    r"I.ve (created|generated|implemented|added)",
    r"This (PR|pull request) (implements|adds|fixes|introduces)",
    r"I (apologize|apologise) for",
    r"It looks like",
    r"(In|Based on) (this|the) (context|codebase|analysis)",
    r"Here is the implementation",
]


def heuristic_score(title: str, body: str) -> float:
    """Compute a heuristic score for AI-authorship based on text patterns."""
    text = f"{title}\n{body or ''}".lower()
    matches = 0
    for pattern in AI_MARKERS:
        if re.search(pattern, text, re.IGNORECASE):
            matches += 1
    return min(matches / len(AI_MARKERS), 1.0)


def compute_diff_complexity(diff_text: str) -> float:
    """Estimate diff complexity based on size and churn."""
    lines = diff_text.split("\n")
    additions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    total = additions + deletions
    return min(total / 500.0, 1.0)  # 500+ lines = max complexity


async def classify_pr(
    title: str,
    body: str,
    diff_text: str,
    files_changed: list[str],
    high_risk_patterns: Optional[list[str]] = None,
) -> dict:
    """Classify a PR using heuristics + LLM.

    Returns: {classification, confidence, rationale}
    """
    heuristic = heuristic_score(title, body)
    complexity = compute_diff_complexity(diff_text)

    # Fast path: trivial PRs
    if len(files_changed) <= 1 and complexity < 0.05:
        return {
            "classification": "trivial",
            "confidence": 0.95,
            "rationale": "Single file change with minimal diff — likely a typo fix or small docs update.",
        }

    # Fast path: high-risk files
    if high_risk_patterns:
        risk_files = [
            f for f in files_changed if any(p in f.lower() for p in high_risk_patterns)
        ]
        if risk_files:
            return {
                "classification": "high_risk",
                "confidence": 0.90,
                "rationale": f"Changes touch high-risk files: {', '.join(risk_files[:3])}.",
            }

    # LLM classification for ambiguous cases
    try:
        diff_sample = diff_text[:8000] if len(diff_text) > 8000 else diff_text

        prompt = f"""PR Title: {title}
PR Body: {(body or '')[:2000] if body else 'None'}
Files changed: {', '.join(files_changed[:20])}
Heuristic AI score: {heuristic:.2f}
Diff complexity: {complexity:.2f}

Diff sample:
{diff_sample}
"""

        response = await acompletion(
            model=f"{settings.llm_provider}/{settings.llm_model}",
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        logger.error("LLM classification failed, falling back to heuristics", error=str(e))
        if heuristic > 0.6:
            return {
                "classification": "ai_slop" if heuristic > 0.8 else "ai_assisted",
                "confidence": heuristic,
                "rationale": "Fallback classification based on heuristic AI-markers.",
            }
        return {
            "classification": "human_first",
            "confidence": 0.5,
            "rationale": "Fallback classification — unable to reach LLM. Review manually.",
        }
