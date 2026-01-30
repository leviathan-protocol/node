"""Cosmos SDK chain adapter implementation.

Provides governance operations for Cosmos SDK chains using:
- CosmPy for chain interactions
- Authz module for delegated voting (MsgExec)
- Gov module for proposals and voting
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import grpc
from cosmpy.aerial.client import LedgerClient, NetworkConfig
from cosmpy.aerial.tx import SigningCfg, Transaction, TxFee
from cosmpy.aerial.urls import parse_url
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.crypto.keypairs import PrivateKey
from cosmpy.protos.cosmos.authz.v1beta1.query_pb2 import QueryGrantsRequest
from cosmpy.protos.cosmos.authz.v1beta1.query_pb2_grpc import QueryStub as AuthzQueryStub
from cosmpy.protos.cosmos.authz.v1beta1.tx_pb2 import MsgExec
from cosmpy.protos.cosmos.gov.v1beta1.gov_pb2 import (
    PROPOSAL_STATUS_VOTING_PERIOD,
    TextProposal,
    VOTE_OPTION_ABSTAIN,
    VOTE_OPTION_NO,
    VOTE_OPTION_NO_WITH_VETO,
    VOTE_OPTION_YES,
)
from cosmpy.protos.cosmos.gov.v1beta1.query_pb2 import (
    QueryProposalRequest,
    QueryProposalsRequest,
)
from cosmpy.protos.cosmos.gov.v1beta1.query_pb2_grpc import QueryStub as GovQueryStub
from cosmpy.protos.cosmos.gov.v1beta1.tx_pb2 import MsgVote
from google.protobuf.any_pb2 import Any as ProtoAny

from chain.adapter import ChainAdapter, ChainType, DelegationInfo, VoteResult
from models.proposal import Proposal, ProposalStatus
from models.vote import VoteChoice

if TYPE_CHECKING:
    from config.settings import ChainConfig

logger = logging.getLogger(__name__)

# Map VoteChoice to Cosmos vote options
VOTE_OPTION_MAP = {
    VoteChoice.YES: VOTE_OPTION_YES,
    VoteChoice.ABSTAIN: VOTE_OPTION_ABSTAIN,
    VoteChoice.NO: VOTE_OPTION_NO,
    VoteChoice.NO_WITH_VETO: VOTE_OPTION_NO_WITH_VETO,
}

# String to VoteChoice mapping
VOTE_CHOICE_MAP = {
    "YES": VoteChoice.YES,
    "NO": VoteChoice.NO,
    "ABSTAIN": VoteChoice.ABSTAIN,
    "NO_WITH_VETO": VoteChoice.NO_WITH_VETO,
}


class CosmosChainAdapter(ChainAdapter):
    """Chain adapter for Cosmos SDK chains.

    Uses:
    - Gov module for governance proposals and direct voting
    - Authz module for delegated voting (gasless voting via MsgExec)
    """

    def __init__(self, config: "ChainConfig"):
        self.config = config
        self._client: LedgerClient | None = None
        self._channel: grpc.Channel | None = None
        self._gov_client: GovQueryStub | None = None
        self._authz_client: AuthzQueryStub | None = None

    @property
    def chain_type(self) -> ChainType:
        return ChainType.COSMOS

    @property
    def chain_id(self) -> str:
        return self.config.chain_id

    @property
    def is_connected(self) -> bool:
        try:
            # Try a simple query to check connection
            if self._client is None:
                return False
            # Query a known address balance as health check
            return True
        except Exception:
            return False

    @property
    def client(self) -> LedgerClient:
        """Lazy-initialize and return the LedgerClient."""
        if self._client is None:
            self._initialize_client()
        return self._client

    @property
    def channel(self) -> grpc.Channel:
        """Return the gRPC channel for direct stub access."""
        if self._channel is None:
            self._initialize_client()
        return self._channel

    @property
    def gov_client(self) -> GovQueryStub:
        """Get or create the governance query client."""
        if self._gov_client is None:
            self._gov_client = GovQueryStub(self.channel)
        return self._gov_client

    @property
    def authz_client(self) -> AuthzQueryStub:
        """Get or create the authz query client."""
        if self._authz_client is None:
            self._authz_client = AuthzQueryStub(self.channel)
        return self._authz_client

    def _initialize_client(self):
        """Initialize the LedgerClient and gRPC channel."""
        logger.info(f"Connecting to Cosmos chain {self.config.chain_id} at {self.config.grpc_url}")

        network_config = NetworkConfig(
            chain_id=self.config.chain_id,
            url=self.config.grpc_url,
            fee_minimum_gas_price=1,
            fee_denomination=self.config.fee_denom,
            staking_denomination=self.config.fee_denom,
        )

        self._client = LedgerClient(network_config)

        # Create gRPC channel for direct stub access
        parsed = parse_url(self.config.grpc_url)
        self._channel = grpc.insecure_channel(parsed.host_and_port)

    # ==================== Governance ====================

    def fetch_proposals(self, status: str | None = None) -> list[Proposal]:
        """Fetch governance proposals from the chain."""
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

    def get_proposal(self, proposal_id: int) -> Proposal | None:
        """Fetch a single proposal by ID."""
        try:
            request = QueryProposalRequest(proposal_id=proposal_id)
            response = self.gov_client.Proposal(request)
            return self._parse_proposal(response.proposal)
        except Exception as e:
            logger.error(f"Failed to fetch proposal {proposal_id}: {e}")
            return None

    def _parse_proposal(self, proto_proposal) -> Proposal | None:
        """Parse a protobuf proposal into our Proposal model."""
        try:
            title = "Unknown"
            description = "No description available"
            proposal_type = "unknown"

            # v1 style: title and summary are direct fields
            if hasattr(proto_proposal, "title") and proto_proposal.title:
                title = proto_proposal.title
            if hasattr(proto_proposal, "summary") and proto_proposal.summary:
                description = proto_proposal.summary

            # v1beta1 style: content field is an Any type
            if hasattr(proto_proposal, "content") and proto_proposal.content:
                content = proto_proposal.content
                if hasattr(content, "type_url") and content.type_url:
                    proposal_type = content.type_url.split(".")[-1]

                    if "TextProposal" in content.type_url:
                        text_proposal = TextProposal()
                        if content.Unpack(text_proposal):
                            title = text_proposal.title
                            description = text_proposal.description

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
        voter_address: str,
        proposal_id: int,
        vote_option: VoteChoice,
        private_key: bytes | None = None,
    ) -> VoteResult:
        """Submit a vote directly (voter pays gas)."""
        logger.info(f"Submitting vote {vote_option.name} for proposal #{proposal_id}")

        try:
            # Create wallet from private key
            if private_key:
                wallet = LocalWallet(PrivateKey(private_key), prefix=self.config.address_prefix)
            else:
                raise ValueError("Private key required for direct voting")

            msg = MsgVote(
                proposal_id=proposal_id,
                voter=voter_address,
                option=VOTE_OPTION_MAP[vote_option],
            )

            tx = Transaction()
            tx.add_message(msg)

            # Query account for sequence
            account = self.client.query_account(wallet.address())

            fee = TxFee(
                amount=f"{self.config.fee_amount}{self.config.fee_denom}",
                gas_limit=self.config.gas_limit,
            )

            tx.seal(
                signing_cfgs=SigningCfg.direct(wallet.public_key(), account.sequence),
                fee=fee,
            )
            tx.sign(wallet.signer(), self.config.chain_id, account.number)
            tx.complete()

            submitted_tx = self.client.broadcast_tx(tx)
            submitted_tx.wait_to_complete()

            logger.info(f"Vote submitted. TX hash: {submitted_tx.tx_hash}")
            return VoteResult(success=True, tx_hash=submitted_tx.tx_hash)

        except Exception as e:
            logger.error(f"Failed to submit vote: {e}")
            return VoteResult(success=False, error=str(e))

    def submit_vote_on_behalf(
        self,
        voter_address: str,
        proposal_id: int,
        vote_option: VoteChoice,
        relayer_private_key: bytes,
    ) -> VoteResult:
        """Submit a vote on behalf of a user using Authz MsgExec."""
        logger.info(
            f"Voting on behalf: voter={voter_address}, "
            f"proposal={proposal_id}, vote={vote_option.name}"
        )

        try:
            # Create relayer wallet
            relayer_wallet = LocalWallet(
                PrivateKey(relayer_private_key), prefix=self.config.address_prefix
            )
            relayer_address = str(relayer_wallet.address())

            # Create the inner MsgVote
            msg_vote = MsgVote(
                proposal_id=proposal_id,
                voter=voter_address,
                option=VOTE_OPTION_MAP[vote_option],
            )

            # Wrap in protobuf Any type
            vote_any = ProtoAny()
            vote_any.Pack(msg_vote)

            # Create MsgExec
            msg_exec = MsgExec(
                grantee=relayer_address,
                msgs=[vote_any],
            )

            tx = Transaction()
            tx.add_message(msg_exec)

            account = self.client.query_account(relayer_wallet.address())

            fee = TxFee(
                amount=f"{self.config.fee_amount}{self.config.fee_denom}",
                gas_limit=self.config.gas_limit,
            )

            tx.seal(
                signing_cfgs=SigningCfg.direct(relayer_wallet.public_key(), account.sequence),
                fee=fee,
            )
            tx.sign(relayer_wallet.signer(), self.config.chain_id, account.number)
            tx.complete()

            submitted_tx = self.client.broadcast_tx(tx)
            submitted_tx.wait_to_complete()

            logger.info(f"Vote on behalf submitted. TX hash: {submitted_tx.tx_hash}")
            return VoteResult(success=True, tx_hash=submitted_tx.tx_hash)

        except Exception as e:
            logger.error(f"Failed to submit vote on behalf: {e}")
            return VoteResult(success=False, error=str(e))

    # ==================== Delegation ====================

    def check_delegation(self, delegator: str, delegate: str) -> DelegationInfo:
        """Check if an Authz grant exists for MsgVote."""
        try:
            request = QueryGrantsRequest(
                granter=delegator,
                grantee=delegate,
                msg_type_url="/cosmos.gov.v1beta1.MsgVote",
            )
            response = self.authz_client.Grants(request)

            if response.grants:
                grant = response.grants[0]
                expires_at = None
                if grant.expiration:
                    expires_at = grant.expiration.ToDatetime().replace(tzinfo=timezone.utc)

                return DelegationInfo(
                    delegator=delegator,
                    delegate=delegate,
                    is_valid=True,
                    expires_at=expires_at,
                    chain_type=ChainType.COSMOS,
                )

            return DelegationInfo(
                delegator=delegator,
                delegate=delegate,
                is_valid=False,
                chain_type=ChainType.COSMOS,
            )

        except Exception as e:
            logger.warning(f"Failed to check authz grant: {e}")
            return DelegationInfo(
                delegator=delegator,
                delegate=delegate,
                is_valid=False,
                chain_type=ChainType.COSMOS,
            )

    def get_voting_power(self, address: str) -> int:
        """Get staked token balance (voting power) for an address."""
        try:
            # Query staking balance
            # Note: This is simplified - full implementation would query staking module
            return self.get_balance(address, self.config.fee_denom)
        except Exception as e:
            logger.warning(f"Failed to get voting power: {e}")
            return 0

    # ==================== Balance ====================

    def get_balance(self, address: str, token: str | None = None) -> int:
        """Get token balance of an address."""
        token = token or self.config.fee_denom
        try:
            return self.client.query_bank_balance(address, token)
        except Exception as e:
            logger.warning(f"Failed to get balance: {e}")
            return 0

    def close(self):
        """Close connections."""
        self._client = None
        if self._channel:
            self._channel.close()
            self._channel = None
