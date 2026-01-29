"""Main polling loop for the sidecar."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

from brain.decision import DecisionEngine
from chain.governance import GovernanceClient
from chain.wallet import WalletManager
from config.fork import Fork
from config.settings import SidecarConfig
from models.proposal import Proposal
from models.vote import VoteDecision
from sidecar.logger import log_decision
from sidecar.state import SidecarState

if TYPE_CHECKING:
    from data.loader import SharedLaw

logger = logging.getLogger(__name__)


class SidecarLoop:
    """Main polling loop that fetches proposals, makes decisions, and votes."""

    def __init__(
        self,
        governance: GovernanceClient,
        wallet: WalletManager,
        decision_engine: DecisionEngine,
        fork: Fork,
        config: SidecarConfig,
        state: SidecarState | None = None,
        shared_law: "SharedLaw | None" = None,
    ):
        self.governance = governance
        self.wallet = wallet
        self.decision_engine = decision_engine
        self.fork = fork
        self.config = config
        self.state = state or SidecarState.load(config.state_file)
        self.shared_law = shared_law

        self._running = False
        self._retry_counts: dict[int, int] = {}

    async def run(self):
        """Run the main polling loop."""
        self._running = True
        logger.info(f"Starting sidecar loop (poll interval: {self.config.poll_interval_seconds}s)")

        # Log shared law context if available
        if self.shared_law:
            summary = self.shared_law.summary()
            logger.info(
                f"Shared law loaded: {summary['instance_id']} v{summary['core_version']} "
                f"({summary['terms_count']} terms, {summary['locked_principles_count']} locked principles)"
            )

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop)

        while self._running:
            try:
                await self._poll_cycle()
            except Exception as e:
                logger.error(f"Error in poll cycle: {e}", exc_info=True)

            if self._running:
                await asyncio.sleep(self.config.poll_interval_seconds)

        logger.info("Sidecar loop stopped")

    def stop(self):
        """Signal the loop to stop."""
        logger.info("Shutdown requested")
        self._running = False

    async def _poll_cycle(self):
        """Execute one polling cycle: fetch proposals, decide, vote."""
        logger.debug("Starting poll cycle")

        # Fetch proposals in voting period
        proposals = self.governance.fetch_voting_proposals()

        if not proposals:
            logger.debug("No proposals in voting period")
            return

        # Process each unprocessed proposal
        for proposal in proposals:
            if self.state.is_processed(proposal.id):
                logger.debug(f"Skipping already processed proposal #{proposal.id}")
                continue

            await self._process_proposal(proposal)

    async def _process_proposal(self, proposal: Proposal):
        """Process a single proposal: decide and vote."""
        logger.info(f"Processing proposal #{proposal.id}: {proposal.title}")

        try:
            # Get decision from LLM
            decision = self.decision_engine.decide(proposal)

            # Log the decision for transparency (with shared law context if available)
            log_decision(
                proposal,
                decision,
                self.fork,
                self.config.decisions_log,
                self.shared_law,
            )

            # Submit vote to chain
            await self._submit_vote(proposal, decision)

            # Mark as processed
            self.state.mark_processed(proposal.id)
            self._retry_counts.pop(proposal.id, None)

        except Exception as e:
            logger.error(f"Failed to process proposal #{proposal.id}: {e}")
            self._handle_retry(proposal.id)

    async def _submit_vote(self, proposal: Proposal, decision: VoteDecision):
        """Submit vote transaction with retry logic."""
        logger.info(
            f"Submitting vote {decision.choice.name} for proposal #{proposal.id}"
        )

        # Run synchronous chain call in executor to not block
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.governance.submit_vote,
            proposal.id,
            decision.choice,
            self.wallet.wallet,
        )

        logger.info(f"Vote submitted for proposal #{proposal.id}")

    def _handle_retry(self, proposal_id: int):
        """Handle retry logic for failed proposals."""
        count = self._retry_counts.get(proposal_id, 0) + 1
        self._retry_counts[proposal_id] = count

        if count >= self.config.max_retries:
            logger.warning(
                f"Proposal #{proposal_id} exceeded max retries ({self.config.max_retries}), "
                "marking as processed to avoid infinite loop"
            )
            self.state.mark_processed(proposal_id)
            self._retry_counts.pop(proposal_id, None)
        else:
            logger.info(f"Will retry proposal #{proposal_id} (attempt {count}/{self.config.max_retries})")
