"""Decision engine that combines Fork, Proposal, and LLM to produce VoteDecision."""

import json
import logging

from brain.llm import LLMWrapper
from brain.prompts import build_voting_prompt
from config.fork import Fork
from models.proposal import Proposal
from models.vote import VoteChoice, VoteDecision

logger = logging.getLogger(__name__)


class DecisionEngine:
    """Combines Fork principles with LLM to make voting decisions."""

    def __init__(self, llm: LLMWrapper, fork: Fork):
        self.llm = llm
        self.fork = fork

    def decide(self, proposal: Proposal) -> VoteDecision:
        """Generate a voting decision for a proposal.

        Args:
            proposal: The proposal to evaluate

        Returns:
            VoteDecision with choice, confidence, and reasoning
        """
        logger.info(f"Evaluating proposal #{proposal.id}: {proposal.title}")

        # Build the prompt
        messages = build_voting_prompt(proposal, self.fork)

        # Generate decision using constrained grammar
        raw_response = self.llm.generate_vote_decision(messages)
        logger.debug(f"LLM response: {raw_response}")

        # Parse the JSON response
        decision = self._parse_decision(raw_response)

        # Apply abstain threshold
        if decision.confidence < self.fork.abstain_threshold:
            logger.info(
                f"Confidence {decision.confidence:.2f} below threshold "
                f"{self.fork.abstain_threshold}, changing to ABSTAIN"
            )
            decision = VoteDecision(
                choice=VoteChoice.ABSTAIN,
                confidence=decision.confidence,
                reasoning=f"Confidence below threshold. Original reasoning: {decision.reasoning}",
            )

        logger.info(
            f"Decision for #{proposal.id}: {decision.choice.name} "
            f"(confidence: {decision.confidence:.2f})"
        )
        return decision

    def _parse_decision(self, raw_json: str) -> VoteDecision:
        """Parse LLM JSON output into VoteDecision.

        Args:
            raw_json: JSON string from LLM

        Returns:
            VoteDecision

        Raises:
            ValueError: If JSON is invalid or missing required fields
        """
        try:
            data = json.loads(raw_json)

            vote = VoteChoice.from_string(data["vote"])
            confidence = float(data["confidence"])
            reasoning = data["reasoning"]

            return VoteDecision(
                choice=vote,
                confidence=confidence,
                reasoning=reasoning,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Raw response: {raw_json}")
            # Return a safe default
            return VoteDecision(
                choice=VoteChoice.ABSTAIN,
                confidence=0.0,
                reasoning=f"Failed to parse LLM response: {e}",
            )
