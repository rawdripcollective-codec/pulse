"""PR Triage Agent — LangGraph state machine for automated PR triage.

Pipeline:
  [Classify] → [Blast Radius] → [Generate Report] → [Wait Human] → [Post to GitHub]

The graph pauses after `generate_report` via `interrupt_before=["action"]`
so that no comment is posted to GitHub without an explicit human approval.
"""

import json
import time
from typing import Optional, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from litellm import acompletion

from app.agents.classifier import classify_pr
from app.agents.prompts import BLAST_RADIUS_PROMPT, REPORT_GENERATION_PROMPT
from app.config import settings
from app.engine.queries import get_blast_radius, get_callers
from app.github.client import GitHubClient

logger = structlog.get_logger()


# ─── State ────────────────────────────────────────────────────

class TriageState(TypedDict):
    # Input
    repo_full_name: str
    pr_number: int
    pr_title: str
    pr_body: str
    pr_author: str
    diff_text: str
    files_changed: list[str]

    # Classification
    classification: str
    classification_confidence: float
    classification_rationale: str

    # Blast radius
    blast_radius_score: float
    affected_modules: list[dict]
    affected_callers: list[str]

    # Report
    report_summary: str
    suggested_action: str
    suggested_reviewer: str
    suggested_labels: list[str]
    findings: list[dict]

    # Human approval
    needs_human: bool
    approved: bool
    moderation_notes: str

    # Output
    error: Optional[str]


# ─── Constants ────────────────────────────────────────────────

HIGH_RISK_PATTERNS = [
    "auth", "authenticate", "authorization", "login", "session", "token",
    "crypto", "encrypt", "decrypt", "hash", "password", "secret",
    "payment", "billing", "invoice", "charge", "refund",
    "sql", "query", "database", "migration",
    "permission", "acl", "rbac", "role",
]


# ─── Nodes ────────────────────────────────────────────────────

async def classification_node(state: TriageState) -> TriageState:
    """Classify the PR as human_first, ai_assisted, ai_slop, trivial, or high_risk."""
    logger.info("Classifying PR", repo=state["repo_full_name"], pr=state["pr_number"])

    result = await classify_pr(
        title=state["pr_title"],
        body=state["pr_body"],
        diff_text=state["diff_text"],
        files_changed=state["files_changed"],
        high_risk_patterns=HIGH_RISK_PATTERNS,
    )

    state["classification"] = result["classification"]
    state["classification_confidence"] = result["confidence"]
    state["classification_rationale"] = result["rationale"]

    # Determine if human review is mandatory
    state["needs_human"] = result["classification"] in ("high_risk", "ai_slop")
    return state


async def blast_radius_node(state: TriageState) -> TriageState:
    """Compute blast radius for each changed file."""
    logger.info("Computing blast radius", repo=state["repo_full_name"], pr=state["pr_number"])

    all_affected: list[dict] = []
    all_callers: set[str] = set()

    for file_path in state["files_changed"]:
        affected = get_blast_radius(state["repo_full_name"], file_path)
        all_affected.extend(affected)
        for entry in affected:
            all_callers.add(entry.get("caller", ""))

    # Score: how many external files are affected
    unique_affected_files = len(set(a.get("caller_file", "") for a in all_affected))
    total_files_in_repo = max(len(state["files_changed"]), 1)
    state["blast_radius_score"] = min(
        unique_affected_files / max(total_files_in_repo * 5, 1), 1.0
    )
    state["affected_modules"] = all_affected[:50]  # cap at 50
    state["affected_callers"] = list(all_callers)[:50]

    # If blast radius is significant, require human review
    if state["blast_radius_score"] > 0.3:
        state["needs_human"] = True

    return state


async def report_generation_node(state: TriageState) -> TriageState:
    """Generate the triage report using LLM."""
    logger.info("Generating triage report", repo=state["repo_full_name"], pr=state["pr_number"])

    context = f"""## PR #{state['pr_number']}: {state['pr_title']}

**Author:** {state['pr_author']}
**Classification:** {state['classification']} (confidence: {state['classification_confidence']:.0%})
**Rationale:** {state['classification_rationale']}

**Files changed ({len(state['files_changed'])}):**
{chr(10).join(f'- {f}' for f in state['files_changed'][:15])}

**Blast radius score:** {state['blast_radius_score']:.0%}
**Affected callers:** {', '.join(state['affected_callers'][:10]) if state['affected_callers'] else 'None detected'}

**Diff summary (first 3000 chars):**
{state['diff_text'][:3000]}
"""

    try:
        response = await acompletion(
            model=f"{settings.llm_provider}/{settings.llm_model}",
            messages=[
                {"role": "system", "content": REPORT_GENERATION_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.2,
            max_tokens=1000,
        )

        report_text = response.choices[0].message.content

        state["report_summary"] = report_text
        state["suggested_action"] = _extract_section(report_text, "suggested action", "comment")
        state["suggested_reviewer"] = _extract_section(report_text, "recommended reviewer", "")
        state["suggested_labels"] = _extract_labels(report_text)

    except Exception as e:
        logger.error("Report generation failed", error=str(e))
        state["report_summary"] = (
            f"## Triage Report for PR #{state['pr_number']}\n\n"
            f"**Classification:** {state['classification']}\n"
            f"**Error:** Report generation failed. Please review manually."
        )
        state["suggested_action"] = "comment"
        state["error"] = str(e)

    return state


def action_node(state: TriageState) -> TriageState:
    """Execute the final action: post the report to GitHub (after human approval)."""
    if not state.get("approved"):
        logger.info("Report not approved, skipping GitHub post")
        return state

    logger.info("Posting triage report to GitHub", repo=state["repo_full_name"], pr=state["pr_number"])

    try:
        client = GitHubClient()
        comment_body = _format_github_comment(state)
        client.post_pr_comment(state["repo_full_name"], state["pr_number"], comment_body)

        if state.get("suggested_labels"):
            client.add_labels(
                state["repo_full_name"],
                state["pr_number"],
                state["suggested_labels"],
            )

        logger.info("Triage report posted successfully")

    except Exception as e:
        logger.error("Failed to post report to GitHub", error=str(e))
        state["error"] = str(e)

    return state


# ─── Helpers ──────────────────────────────────────────────────

def _extract_section(text: str, section_name: str, default: str) -> str:
    """Extract a section value from structured report text.

    Handles markdown bold markers: `**Suggested action:** approve` -> `approve`.
    """
    import re

    for line in text.split("\n"):
        if section_name.lower() not in line.lower() or ":" not in line:
            continue
        value = line.split(":", 1)[1].strip()
        # Strip surrounding ** (markdown bold) and backticks
        value = re.sub(r"^[\*\s`]+|[\*\s`]+$", "", value)
        return value
    return default


def _extract_labels(text: str) -> list[str]:
    """Extract suggested labels from report text (backtick-wrapped or comma-separated)."""
    import re

    labels: list[str] = []
    for line in text.split("\n"):
        if "label" in line.lower() and ":" in line:
            label_text = line.split(":", 1)[1].strip()
            found = re.findall(r"`([^`]+)`", label_text)
            labels.extend(found)
    return labels[:3]


def _format_github_comment(state: TriageState) -> str:
    """Format the triage report as a GitHub comment."""
    labels_md = " ".join(f"`{l}`" for l in state.get("suggested_labels", []))

    return f"""{state['report_summary']}

---
<details>
<summary>🤖 Pulse Triage Metadata</summary>

- **Classification:** `{state['classification']}` (confidence: {state.get('classification_confidence', 0):.0%})
- **Blast Radius Score:** {state.get('blast_radius_score', 0):.0%}
- **Suggested Action:** `{state.get('suggested_action', 'comment')}`
- **Suggested Labels:** {labels_md or 'None'}
- **Suggested Reviewer:** {state.get('suggested_reviewer', 'Not specified')}

> This report was generated by [Pulse](https://github.com/rawdripcollective-codec/pulse), an agentic PR triage tool. A human maintainer approved this post.
</details>
"""


# ─── Graph construction ───────────────────────────────────────

def build_triage_graph() -> StateGraph:
    """Build the LangGraph state machine for PR triage."""
    builder = StateGraph(TriageState)

    builder.add_node("classify", classification_node)
    builder.add_node("blast_radius", blast_radius_node)
    builder.add_node("generate_report", report_generation_node)
    builder.add_node("action", action_node)

    builder.set_entry_point("classify")
    builder.add_edge("classify", "blast_radius")
    builder.add_edge("blast_radius", "generate_report")
    # After report generation, the graph pauses for human approval.
    # The action_node only runs after approval is granted via the API.
    builder.add_edge("generate_report", "action")
    builder.add_edge("action", END)

    return builder


# Singleton graph instance
_triage_graph = None


def get_triage_graph():
    """Get the compiled (and interrupt-paused) triage graph singleton."""
    global _triage_graph
    if _triage_graph is None:
        _triage_graph = build_triage_graph().compile(
            checkpointer=MemorySaver(),
            interrupt_before=["action"],  # Pause before posting to GitHub
        )
    return _triage_graph
