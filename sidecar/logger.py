"""Decision audit logging for transparency and future Proof of Alignment."""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from config.fork import Fork
from models.proposal import Proposal
from models.vote import VoteDecision

logger = logging.getLogger(__name__)


def _match_principle(reasoning: str, principles: list[str]) -> str | None:
    """Try to identify which principle triggered the decision.

    Simple keyword matching - could be enhanced with semantic similarity.
    """
    reasoning_lower = reasoning.lower()
    for principle in principles:
        # Check if any significant words from the principle appear in reasoning
        words = [w.lower() for w in principle.split() if len(w) > 4]
        matches = sum(1 for w in words if w in reasoning_lower)
        if matches >= 2 or (len(words) <= 2 and matches >= 1):
            return principle
    return None


def log_decision(
    proposal: Proposal,
    decision: VoteDecision,
    fork: Fork,
    log_file: str | Path = "decisions.log",
):
    """Log a voting decision for transparency and future Proof of Alignment.

    Creates a JSON-lines audit log with:
    - Timestamp
    - Proposal details
    - Fork context
    - Vote decision and reasoning
    - Pre-computed reasoning hash for chain submission

    Args:
        proposal: The proposal that was voted on
        decision: The voting decision made
        fork: The fork (values) used for the decision
        log_file: Path to the decisions log file
    """
    log_file = Path(log_file)

    # Pre-compute hash for future x/alignment submission
    reasoning_hash = hashlib.sha256(decision.reasoning.encode()).hexdigest()

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "proposal_id": proposal.id,
        "proposal_title": proposal.title,
        "proposal_type": proposal.proposal_type,
        "fork_name": fork.name,
        "fork_voting_style": fork.voting_style,
        "principle_triggered": _match_principle(decision.reasoning, fork.principles),
        "vote": decision.choice.name,
        "confidence": decision.confidence,
        "llm_reasoning": decision.reasoning,
        "reasoning_hash": reasoning_hash,
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
