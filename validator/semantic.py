"""Semantic validation of vote reasoning.

Uses LLM to verify that a user's voting reasoning is consistent with:
1. Their stated vote choice (no contradictions)
2. The actual proposal content (no hallucinations)
3. SharedLaw locked principles (no constitutional violations)

This acts as a "semantic firewall" in Observer Mode, catching
malformed or suspicious voting intents before they're broadcast.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from brain.prompts import (
    SEMANTIC_VALIDATION_SCHEMA,
    build_semantic_validation_prompt,
)

if TYPE_CHECKING:
    from brain.llm import LLMWrapper
    from data.loader import SharedLaw

logger = logging.getLogger(__name__)


class ValidationIssueType(Enum):
    """Types of issues that can be detected in reasoning."""

    CONTRADICTION = "contradiction"
    HALLUCINATION = "hallucination"
    CONSTITUTIONAL_VIOLATION = "constitutional_violation"
    PARSING_ERROR = "parsing_error"
    LLM_ERROR = "llm_error"


@dataclass
class ValidationResult:
    """Result of semantic validation."""

    consistent: bool
    issues: list[str] = field(default_factory=list)
    recommendation: str = "accept"  # "accept" or "reject"
    raw_response: dict | None = None
    error_message: str | None = None

    @property
    def should_accept(self) -> bool:
        """Whether the vote should be accepted."""
        return self.recommendation == "accept"

    @property
    def should_reject(self) -> bool:
        """Whether the vote should be rejected."""
        return self.recommendation == "reject"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "consistent": self.consistent,
            "issues": self.issues,
            "recommendation": self.recommendation,
            "error_message": self.error_message,
        }


def validate_reasoning(
    llm: "LLMWrapper",
    proposal_title: str,
    proposal_description: str,
    vote_option: str,
    public_reasoning: str,
    confidence_score: float | None = None,
    shared_law: "SharedLaw | None" = None,
) -> ValidationResult:
    """Validate that vote reasoning is consistent with the vote choice.

    Uses LLM to perform semantic analysis and detect:
    - Contradictions (vote says NO but reasoning supports YES)
    - Hallucinations (reasoning mentions things not in proposal)
    - Constitutional violations (reasoning violates locked principles)

    Args:
        llm: LLMWrapper instance for LLM calls.
        proposal_title: Title of the proposal being voted on.
        proposal_description: Full description of the proposal.
        vote_option: User's vote choice (YES/NO/ABSTAIN/NO_WITH_VETO).
        public_reasoning: User's explanation for their vote.
        confidence_score: Optional confidence score (0.0-1.0).
        shared_law: Optional SharedLaw for constitutional context.

    Returns:
        ValidationResult with consistency check and any detected issues.
    """
    logger.info(f"Validating reasoning for vote: {vote_option}")

    # Build prompt
    messages = build_semantic_validation_prompt(
        proposal_title=proposal_title,
        proposal_description=proposal_description,
        vote_option=vote_option,
        public_reasoning=public_reasoning,
        confidence_score=confidence_score,
        shared_law=shared_law,
    )

    try:
        # Call LLM with structured output
        response = llm.client.chat(
            model=llm.model,
            messages=messages,
            format=SEMANTIC_VALIDATION_SCHEMA,
            options={
                "temperature": 0.3,  # Low temperature for consistent analysis
                "num_ctx": llm.config.n_ctx,
            },
        )

        # Parse response
        result_text = response.message.content
        logger.debug(f"LLM response: {result_text}")

        try:
            result_data = json.loads(result_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return ValidationResult(
                consistent=False,
                issues=["Failed to parse validation response"],
                recommendation="reject",
                error_message=f"JSON parse error: {e}",
            )

        # Extract fields with defaults
        consistent = result_data.get("consistent", False)
        issues = result_data.get("issues", [])
        recommendation = result_data.get("recommendation", "reject")

        # Validate recommendation value
        if recommendation not in ("accept", "reject"):
            recommendation = "reject" if issues else "accept"

        logger.info(
            f"Semantic validation: consistent={consistent}, "
            f"issues={len(issues)}, recommendation={recommendation}"
        )

        return ValidationResult(
            consistent=consistent,
            issues=issues,
            recommendation=recommendation,
            raw_response=result_data,
        )

    except Exception as e:
        logger.error(f"Semantic validation failed: {e}")
        return ValidationResult(
            consistent=False,
            issues=["Validation service error"],
            recommendation="reject",
            error_message=str(e),
        )


def validate_reasoning_quick(
    proposal_title: str,
    proposal_description: str,
    vote_option: str,
    public_reasoning: str,
) -> ValidationResult:
    """Quick heuristic validation without LLM (for testing/fallback).

    Performs basic checks:
    - Reasoning is not empty
    - Reasoning is not too short
    - Basic sentiment alignment (very rough)

    Args:
        proposal_title: Title of the proposal.
        proposal_description: Description of the proposal.
        vote_option: User's vote choice.
        public_reasoning: User's explanation.

    Returns:
        ValidationResult with basic consistency check.
    """
    issues = []

    # Check reasoning exists and has minimum length
    if not public_reasoning or len(public_reasoning.strip()) < 10:
        issues.append("Reasoning is too short or empty")
        return ValidationResult(
            consistent=False,
            issues=issues,
            recommendation="reject",
        )

    # Basic keyword heuristics (very rough)
    reasoning_lower = public_reasoning.lower()

    positive_words = ["support", "agree", "good", "beneficial", "approve", "favor"]
    negative_words = ["oppose", "disagree", "bad", "harmful", "reject", "against"]

    positive_count = sum(1 for w in positive_words if w in reasoning_lower)
    negative_count = sum(1 for w in negative_words if w in reasoning_lower)

    # Check for obvious contradictions
    if vote_option in ("YES",) and negative_count > positive_count + 2:
        issues.append("Reasoning appears negative but vote is YES")

    if vote_option in ("NO", "NO_WITH_VETO") and positive_count > negative_count + 2:
        issues.append("Reasoning appears positive but vote is NO")

    # If issues found, recommend rejection
    if issues:
        return ValidationResult(
            consistent=False,
            issues=issues,
            recommendation="reject",
        )

    return ValidationResult(
        consistent=True,
        issues=[],
        recommendation="accept",
    )


# Mock validation for testing without LLM
def validate_reasoning_mock(
    proposal_title: str,
    proposal_description: str,
    vote_option: str,
    public_reasoning: str,
    should_pass: bool = True,
) -> ValidationResult:
    """Mock validation for testing without LLM.

    Args:
        proposal_title: Title of the proposal.
        proposal_description: Description of the proposal.
        vote_option: User's vote choice.
        public_reasoning: User's explanation.
        should_pass: Whether validation should pass (for testing).

    Returns:
        ValidationResult based on should_pass flag.
    """
    if should_pass:
        return ValidationResult(
            consistent=True,
            issues=[],
            recommendation="accept",
        )
    else:
        return ValidationResult(
            consistent=False,
            issues=["Mock validation failure"],
            recommendation="reject",
        )


if __name__ == "__main__":
    # Quick test with heuristic validation
    import sys

    logging.basicConfig(level=logging.DEBUG)

    print("=== Testing quick heuristic validation ===")

    # Test consistent YES vote
    result = validate_reasoning_quick(
        proposal_title="Increase Block Size",
        proposal_description="Proposal to increase block size to 2MB",
        vote_option="YES",
        public_reasoning="I support this proposal because larger blocks will improve throughput.",
    )
    print(f"Consistent YES: {result.consistent}, recommend={result.recommendation}")

    # Test consistent NO vote
    result = validate_reasoning_quick(
        proposal_title="Increase Block Size",
        proposal_description="Proposal to increase block size to 2MB",
        vote_option="NO",
        public_reasoning="I oppose this proposal because it harms decentralization.",
    )
    print(f"Consistent NO: {result.consistent}, recommend={result.recommendation}")

    # Test contradictory vote
    result = validate_reasoning_quick(
        proposal_title="Increase Block Size",
        proposal_description="Proposal to increase block size to 2MB",
        vote_option="YES",
        public_reasoning="I strongly oppose and reject this harmful proposal.",
    )
    print(f"Contradictory: {result.consistent}, issues={result.issues}")

    # Test empty reasoning
    result = validate_reasoning_quick(
        proposal_title="Test",
        proposal_description="Test",
        vote_option="YES",
        public_reasoning="",
    )
    print(f"Empty reasoning: {result.consistent}, issues={result.issues}")

    print("\n=== Testing mock validation ===")
    result = validate_reasoning_mock("T", "D", "YES", "R", should_pass=True)
    print(f"Mock pass: {result.should_accept}")

    result = validate_reasoning_mock("T", "D", "YES", "R", should_pass=False)
    print(f"Mock fail: {result.should_reject}")

    sys.exit(0)
