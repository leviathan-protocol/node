"""Governance module for fetching proposals and submitting votes."""

import logging

from cosmpy.aerial.client import LedgerClient
from cosmpy.aerial.tx import SigningCfg, Transaction
from cosmpy.aerial.tx_helpers import SubmittedTx
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.protos.cosmos.gov.v1beta1.gov_pb2 import (
    PROPOSAL_STATUS_VOTING_PERIOD,
    TextProposal,
    VOTE_OPTION_ABSTAIN,
    VOTE_OPTION_NO,
    VOTE_OPTION_NO_WITH_VETO,
    VOTE_OPTION_YES,
)
from cosmpy.protos.cosmos.gov.v1beta1.query_pb2 import QueryProposalsRequest
from cosmpy.protos.cosmos.gov.v1beta1.query_pb2_grpc import QueryStub as GovQueryStub
from cosmpy.protos.cosmos.gov.v1beta1.tx_pb2 import MsgVote

from chain.client import ChainClient
from config.settings import ChainConfig
from models.proposal import Proposal, ProposalStatus
from models.vote import VoteChoice

logger = logging.getLogger(__name__)

# Map VoteChoice to Cosmos vote options
VOTE_OPTION_MAP = {
    VoteChoice.YES: VOTE_OPTION_YES,
    VoteChoice.ABSTAIN: VOTE_OPTION_ABSTAIN,
    VoteChoice.NO: VOTE_OPTION_NO,
    VoteChoice.NO_WITH_VETO: VOTE_OPTION_NO_WITH_VETO,
}


class GovernanceClient:
    """Client for governance operations: fetching proposals and voting."""

    def __init__(self, chain_client: ChainClient, config: ChainConfig):
        self.chain_client = chain_client
        self.config = config
        self._gov_client: GovQueryStub | None = None

    @property
    def ledger(self) -> LedgerClient:
        return self.chain_client.client

    @property
    def gov_client(self) -> GovQueryStub:
        """Get or create the governance query client."""
        if self._gov_client is None:
            self._gov_client = GovQueryStub(self.chain_client.channel)
        return self._gov_client

    def fetch_voting_proposals(self) -> list[Proposal]:
        """Fetch all proposals currently in voting period."""
        logger.debug("Fetching proposals in voting period")

        try:
            request = QueryProposalsRequest(
                proposal_status=PROPOSAL_STATUS_VOTING_PERIOD,
            )
            response = self.gov_client.Proposals(request)

            proposals = []
            for p in response.proposals:
                proposal = self._parse_proposal(p)
                if proposal:
                    proposals.append(proposal)

            logger.info(f"Found {len(proposals)} proposals in voting period")
            return proposals

        except Exception as e:
            logger.error(f"Failed to fetch proposals: {e}")
            return []

    def _parse_proposal(self, proto_proposal) -> Proposal | None:
        """Parse a protobuf proposal into our Proposal model."""
        try:
            # Extract content - handle both v1 and v1beta1 proposal types
            title = "Unknown"
            description = "No description available"
            proposal_type = "unknown"

            # v1 style: title and summary are direct fields on proposal
            if hasattr(proto_proposal, "title") and proto_proposal.title:
                title = proto_proposal.title
            if hasattr(proto_proposal, "summary") and proto_proposal.summary:
                description = proto_proposal.summary

            # v1beta1 style: content field is an Any type containing TextProposal
            if hasattr(proto_proposal, "content") and proto_proposal.content:
                content = proto_proposal.content
                # Get type from type_url
                if hasattr(content, "type_url") and content.type_url:
                    proposal_type = content.type_url.split(".")[-1]

                    # Unpack the Any type to get actual content
                    if "TextProposal" in content.type_url:
                        text_proposal = TextProposal()
                        if content.Unpack(text_proposal):
                            title = text_proposal.title
                            description = text_proposal.description
                            logger.debug(f"Unpacked TextProposal: {title}")
                        else:
                            logger.warning(f"Failed to unpack TextProposal for proposal {proto_proposal.proposal_id}")

            # v1 style: check messages for legacy content
            if title == "Unknown" and hasattr(proto_proposal, "messages") and proto_proposal.messages:
                for msg in proto_proposal.messages:
                    # Try to unpack the message content
                    if hasattr(msg, "type_url") and "TextProposal" in msg.type_url:
                        proposal_type = "TextProposal"
                        text_proposal = TextProposal()
                        if msg.Unpack(text_proposal):
                            title = text_proposal.title
                            description = text_proposal.description
                            logger.debug(f"Unpacked TextProposal from message: {title}")
                            break
                    if hasattr(msg, "content"):
                        title = getattr(msg.content, "title", title)
                        description = getattr(msg.content, "description", description)
                        break

            # Parse timestamps
            submit_time = None
            voting_start = None
            voting_end = None

            if hasattr(proto_proposal, "submit_time"):
                submit_time = proto_proposal.submit_time.ToDatetime()
            if hasattr(proto_proposal, "voting_start_time"):
                voting_start = proto_proposal.voting_start_time.ToDatetime()
            if hasattr(proto_proposal, "voting_end_time"):
                voting_end = proto_proposal.voting_end_time.ToDatetime()

            return Proposal(
                id=proto_proposal.proposal_id,
                title=title,
                description=description,
                status=ProposalStatus(proto_proposal.status),
                submit_time=submit_time,
                voting_start_time=voting_start,
                voting_end_time=voting_end,
                proposal_type=proposal_type,
            )
        except Exception as e:
            logger.warning(f"Failed to parse proposal: {e}")
            return None

    def submit_vote(
        self,
        proposal_id: int,
        vote: VoteChoice,
        wallet: LocalWallet,
    ) -> SubmittedTx:
        """Submit a vote transaction for a proposal.

        Args:
            proposal_id: The proposal ID to vote on
            vote: The vote choice
            wallet: The wallet to sign with

        Returns:
            The submitted transaction
        """
        logger.info(f"Submitting vote {vote.name} for proposal #{proposal_id}")

        msg = MsgVote(
            proposal_id=proposal_id,
            voter=str(wallet.address()),
            option=VOTE_OPTION_MAP[vote],
        )

        tx = Transaction()
        tx.add_message(msg)

        # Query account for sequence and account number
        account = self.ledger.query_account(wallet.address())

        # Use fixed gas limit and fee (vote transactions are simple)
        from cosmpy.aerial.tx import TxFee
        gas_limit = self.config.gas_limit
        fee = TxFee(
            amount=f"{self.config.fee_amount}{self.config.fee_denom}",
            gas_limit=gas_limit,
        )

        # Transaction lifecycle: Draft → seal() → sign() → complete() → broadcast
        tx.seal(
            signing_cfgs=SigningCfg.direct(wallet.public_key(), account.sequence),
            fee=fee,
        )
        tx.sign(wallet.signer(), self.config.chain_id, account.number)
        tx.complete()

        # Broadcast and wait for inclusion
        submitted_tx = self.ledger.broadcast_tx(tx)
        submitted_tx.wait_to_complete()

        logger.info(f"Vote submitted successfully. TX hash: {submitted_tx.tx_hash}")
        return submitted_tx
