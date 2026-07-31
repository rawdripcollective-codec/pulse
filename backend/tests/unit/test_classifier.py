"""Unit tests for the AI-vs-human PR classifier heuristics.

These tests cover the deterministic heuristic scoring and the fast-path
classifications (trivial / high_risk). The LLM-fallback path is tested
in the integration suite (test_triage_graph.py) with a stub `acompletion`.
"""

from unittest.mock import MagicMock

import pytest

from app.agents.classifier import (
    compute_diff_complexity,
    heuristic_score,
)


class TestHeuristicScore:
    """The AI-marker heuristic should score high on clear AI text, low on human text."""

    def test_clean_human_title_scores_zero(self):
        title = "Fix NPE in user serializer when email is missing"
        body = (
            "Repro: create a user without email, call /api/users/{id}, get NPE. "
            "Root cause: serializer assumes email is always set. "
            "Fix: handle the None case explicitly. Tests added."
        )
        assert heuristic_score(title, body) == 0.0

    def test_typical_ai_title_scores_high(self):
        title = "Here's an implementation of OAuth2 PKCE flow"
        body = (
            "Certainly! I've created a comprehensive implementation. "
            "Let me walk you through the changes. "
            "As an AI, I considered the standard best practices. "
            "I hope this helps!"
        )
        score = heuristic_score(title, body)
        assert score > 0.5, f"Expected score > 0.5 for typical AI text, got {score}"

    def test_partial_ai_signals_score_moderately(self):
        title = "Refactor auth module"
        body = "Here is the implementation with proper test coverage."
        score = heuristic_score(title, body)
        # "Here is the implementation" is a single marker
        assert 0.0 < score < 0.5

    def test_empty_body_uses_only_title(self):
        # Should not crash; should score based on title alone
        score = heuristic_score("As an AI language model", "")
        assert score > 0

    def test_case_insensitive_matching(self):
        title = "CERTAINLY!"
        score = heuristic_score(title, "")
        assert score > 0

    def test_score_capped_at_one(self):
        title = " ".join(["Here's the implementation"] * 20)
        score = heuristic_score(title, "")
        assert score <= 1.0


class TestDiffComplexity:
    """Diff complexity should normalize to [0, 1] and reflect churn."""

    def test_empty_diff_is_zero(self):
        assert compute_diff_complexity("") == 0.0

    def test_small_diff_is_low_complexity(self):
        diff = "\n".join([f"+line {i}" for i in range(5)])
        assert 0 < compute_diff_complexity(diff) < 0.1

    def test_large_diff_is_high_complexity(self):
        diff = "\n".join([f"+line {i}" for i in range(600)])
        assert compute_diff_complexity(diff) == 1.0  # capped

    def test_exactly_threshold_is_full(self):
        # 500 lines = complexity 1.0
        diff = "\n".join([f"+line {i}" for i in range(500)])
        assert compute_diff_complexity(diff) == 1.0

    def test_counts_both_additions_and_deletions(self):
        # 250 + and 250 - = 500 lines = 1.0
        diff = "\n".join([f"+line {i}" for i in range(250)] + [f"-line {i}" for i in range(250)])
        assert compute_diff_complexity(diff) == 1.0

    def test_ignores_diff_metadata(self):
        # "+++ a/file" and "--- a/file" are diff metadata, not changes
        diff = "+++ a/file.py\n--- a/file.py\n" + "\n".join(f"+x" for _ in range(10))
        # 10 real changes, not 12
        assert compute_diff_complexity(diff) < 0.05


@pytest.mark.asyncio
class TestClassifyPrFastPaths:
    """The fast-path classifications should fire BEFORE the LLM is called."""

    async def test_single_small_file_is_trivial(self):
        from app.agents.classifier import classify_pr

        result = await classify_pr(
            title="fix typo in README",
            body="",
            diff_text="+s",
            files_changed=["README.md"],
        )
        assert result["classification"] == "trivial"
        assert result["confidence"] >= 0.9

    async def test_auth_file_is_high_risk(self):
        from app.agents.classifier import classify_pr

        result = await classify_pr(
            title="Add password hashing",
            body="",
            diff_text="+import bcrypt\n+bcrypt.hash(password)\n" * 10,
            files_changed=["app/auth/passwords.py"],
            high_risk_patterns=["auth", "password", "crypto"],
        )
        assert result["classification"] == "high_risk"
        assert "passwords.py" in result["rationale"]

    async def test_payment_file_is_high_risk(self):
        from app.agents.classifier import classify_pr

        result = await classify_pr(
            title="Refactor billing",
            body="",
            diff_text="+x" * 200,
            files_changed=["app/payment/stripe.py"],
            high_risk_patterns=["payment", "billing", "charge"],
        )
        assert result["classification"] == "high_risk"

    async def test_falls_through_to_llm_for_ambiguous(self, monkeypatch):
        """For ambiguous PRs, the LLM should be called. We monkey-patch
        `acompletion` to verify the call and return a canned verdict.
        """
        from app.agents import classifier
        from app.agents.classifier import classify_pr

        async def fake_acompletion(*args, **kwargs):
            return _make_llm_response(
                '{"classification": "ai_assisted", "confidence": 0.7, '
                '"rationale": "Has AI markers"}'
            )

        monkeypatch.setattr(classifier, "acompletion", fake_acompletion)

        result = await classify_pr(
            title="Refactor module",
            body="",
            diff_text="+" * 100,
            files_changed=["app/whatever.py", "tests/test_whatever.py"],
        )
        assert result["classification"] == "ai_assisted"
        assert result["confidence"] == 0.7


def _make_llm_response(content: str):
    """Build a fake litellm acompletion response with the given content."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response
