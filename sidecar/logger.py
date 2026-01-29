"""Decision audit logging for transparency and future Proof of Alignment.

Enhanced with shared law context including terms referenced, principles aligned,
and governance version tracking.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from config.fork import Fork, ForkPrinciple
from models.proposal import Proposal
from models.vote import VoteDecision

if TYPE_CHECKING:
    from data.loader import SharedLaw

logger = logging.getLogger(__name__)


def _match_principle(reasoning: str, principles: list[str | ForkPrinciple]) -> str | None:
    """Try to identify which principle triggered the decision.

    Simple keyword matching - could be enhanced with semantic similarity.
    """
    reasoning_lower = reasoning.lower()

    for principle in principles:
        # Extract statement text
        if isinstance(principle, str):
            statement = principle
        elif isinstance(principle, ForkPrinciple):
            statement = principle.statement
        else:
            continue

        # Check if any significant words from the principle appear in reasoning
        words = [w.lower() for w in statement.split() if len(w) > 4]
        matches = sum(1 for w in words if w in reasoning_lower)
        if matches >= 2 or (len(words) <= 2 and matches >= 1):
            return statement

    return None


def _find_aligned_principles(
    reasoning: str,
    fork: Fork,
    shared_law: "SharedLaw | None" = None,
) -> list[str]:
    """Find which principles (both locked and personal) were applied in the decision.

    Args:
        reasoning: The LLM's reasoning text.
        fork: The fork with personal principles.
        shared_law: Optional SharedLaw for locked principles.

    Returns:
        List of principle names/statements that appear to have been applied.
    """
    aligned = []
    reasoning_lower = reasoning.lower()

    # Check fork principles
    for p in fork.principles:
        statement = p if isinstance(p, str) else p.statement
        words = [w.lower() for w in statement.split() if len(w) > 4]
        matches = sum(1 for w in words if w in reasoning_lower)
        if matches >= 2:
            if isinstance(p, ForkPrinciple) and p.aligns_with:
                aligned.append(p.aligns_with)
            else:
                aligned.append(statement[:50])

    # Check locked principles if shared law available
    if shared_law:
        for name in shared_law.get_locked_principles():
            principle = shared_law.get_principle(name)
            if principle:
                words = [w.lower() for w in principle.statement.split() if len(w) > 4]
                matches = sum(1 for w in words if w in reasoning_lower)
                if matches >= 2:
                    aligned.append(name)

    return list(set(aligned))


def _extract_terms_referenced(
    reasoning: str,
    shared_law: "SharedLaw | None" = None,
) -> list[str]:
    """Extract @terms mentioned in the reasoning.

    Args:
        reasoning: The LLM's reasoning text.
        shared_law: Optional SharedLaw for term validation.

    Returns:
        List of term names found in the reasoning.
    """
    terms = []

    # Look for @term patterns
    import re
    pattern = r'@[a-z_]+'
    matches = re.findall(pattern, reasoning.lower())
    terms.extend(matches)

    # If shared law available, validate terms exist
    if shared_law:
        valid_terms = []
        for term in terms:
            if shared_law.term_exists(term):
                valid_terms.append(term)
        return list(set(valid_terms))

    return list(set(terms))


def log_decision(
    proposal: Proposal,
    decision: VoteDecision,
    fork: Fork,
    log_file: str | Path = "decisions.log",
    shared_law: "SharedLaw | None" = None,
    agent_name: str | None = None,
):
    """Log a voting decision for transparency and future Proof of Alignment.

    Creates a JSON-lines audit log with:
    - Timestamp
    - Proposal details
    - Fork context
    - Vote decision and reasoning
    - Pre-computed reasoning hash for chain submission
    - Enhanced fields when shared_law is provided:
      - Terms referenced
      - Principles aligned (both locked and personal)
      - Locked principle constraints
      - Governance version

    Args:
        proposal: The proposal that was voted on
        decision: The voting decision made
        fork: The fork (values) used for the decision
        log_file: Path to the decisions log file
        shared_law: Optional SharedLaw for enhanced logging
    """
    log_file = Path(log_file)

    # Pre-compute hash for future x/alignment submission
    reasoning_hash = hashlib.sha256(decision.reasoning.encode()).hexdigest()

    # Build base entry
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "proposal_id": proposal.id,
        "proposal_title": proposal.title,
        "proposal_type": proposal.proposal_type,
        "agent_name": agent_name,  # CLI --name for monitor matching
        "fork_name": fork.name,
        "fork_voting_style": fork.voting_style,
        "fork_inherits": fork.inherits,
        "principle_triggered": _match_principle(decision.reasoning, fork.principles),
        "vote": decision.choice.name,
        "confidence": decision.confidence,
        "llm_reasoning": decision.reasoning,
        "reasoning_hash": reasoning_hash,
    }

    # Add enhanced fields if shared law available
    if shared_law:
        entry["terms_referenced"] = fork.uses_terms
        entry["terms_in_reasoning"] = _extract_terms_referenced(
            decision.reasoning, shared_law
        )
        entry["principles_aligned"] = _find_aligned_principles(
            decision.reasoning, fork, shared_law
        )
        entry["locked_constraints"] = shared_law.get_locked_principles()
        entry["governance_version"] = shared_law.core_version
        entry["governance_instance"] = shared_law.instance_id

        # Include relevant thresholds for context
        entry["consensus_context"] = {
            "quorum": shared_law.quorum_percentage,
            "protection_ratchet": shared_law.protection_ratchet_multiplier,
        }

    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info(f"Logged decision for proposal #{proposal.id} to {log_file}")
    except IOError as e:
        logger.error(f"Failed to log decision: {e}")

    # Also log to standard logger for visibility
    logger.info(
        f"DECISION: Proposal #{proposal.id} ({proposal.title}) -> "
        f"{decision.choice.name} (confidence: {decision.confidence:.2f})"
    )

    # Log enhanced context if available
    if shared_law and entry.get("principles_aligned"):
        logger.debug(
            f"Applied principles: {entry['principles_aligned']}"
        )
    if shared_law and entry.get("terms_in_reasoning"):
        logger.debug(
            f"Terms referenced: {entry['terms_in_reasoning']}"
        )


def get_decision_summary(
    log_file: str | Path = "decisions.log",
    last_n: int = 10,
) -> list[dict]:
    """Read recent decisions from the log file.

    Args:
        log_file: Path to the decisions log file.
        last_n: Number of recent entries to return.

    Returns:
        List of decision entries (most recent first).
    """
    log_file = Path(log_file)
    if not log_file.exists():
        return []

    entries = []
    try:
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except IOError as e:
        logger.error(f"Failed to read decisions log: {e}")
        return []

    # Return last N entries, most recent first
    return list(reversed(entries[-last_n:]))
