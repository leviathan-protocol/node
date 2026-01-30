"""Abstract Chain Adapter for multi-chain support.

The ChainAdapter provides a unified interface for interacting with different
blockchain networks (Cosmos, EVM, etc.) for governance operations.

Supported chains:
- Cosmos SDK chains (via CosmPy) - Uses Authz for delegation
- EVM chains (via Web3.py) - Uses EIP-2771 meta-transactions for gasless voting
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from models.proposal import Proposal
    from models.vote import VoteChoice

logger = logging.getLogger(__name__)


class ChainType(str, Enum):
    """Supported blockchain types."""

    COSMOS = "cosmos"
    EVM = "evm"


@dataclass
class DelegationInfo:
    """Information about a voting delegation/authorization.

    For Cosmos: Represents an Authz grant (MsgVote authorization)
    For EVM: Represents a token delegation (ERC20Votes.delegate())
    """

    delegator: str  # User who delegated
    delegate: str  # Node/relayer who can vote on behalf
    is_valid: bool
    expires_at: datetime | None = None
    voting_power: int = 0  # Token balance/voting weight
    chain_type: ChainType = ChainType.COSMOS


@dataclass
class VoteResult:
    """Result of a vote submission."""

    success: bool
    tx_hash: str | None = None
    error: str | None = None
    block_number: int | None = None
    gas_used: int | None = None


class ChainAdapter(ABC):
    """Abstract base class for blockchain adapters.

    Implementations must provide methods for:
    - Fetching governance proposals
    - Submitting votes (direct or on behalf of users)
    - Checking delegation/authorization status
    - Querying balances and voting power
    """

    @property
    @abstractmethod
    def chain_type(self) -> ChainType:
        """Return the chain type this adapter handles."""
        pass

    @property
    @abstractmethod
    def chain_id(self) -> str:
        """Return the chain ID."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the adapter is connected to the chain."""
        pass

    # ==================== Governance ====================

    @abstractmethod
    def fetch_proposals(self, status: str | None = None) -> list["Proposal"]:
        """Fetch governance proposals from the chain.

        Args:
            status: Optional filter for proposal status (e.g., "voting", "passed").
                   If None, returns proposals in voting period.

        Returns:
            List of Proposal objects.
        """
        pass

    @abstractmethod
    def get_proposal(self, proposal_id: int) -> "Proposal | None":
        """Fetch a single proposal by ID.

        Args:
            proposal_id: The proposal identifier.

        Returns:
            Proposal object or None if not found.
        """
        pass

    @abstractmethod
    def submit_vote(
        self,
        voter_address: str,
        proposal_id: int,
        vote_option: "VoteChoice",
        private_key: bytes | None = None,
    ) -> VoteResult:
        """Submit a vote directly (voter pays gas).

        Args:
            voter_address: Address of the voter.
            proposal_id: ID of the proposal to vote on.
            vote_option: The vote choice (YES/NO/ABSTAIN/NO_WITH_VETO).
            private_key: Private key for signing (optional, uses configured wallet if None).

        Returns:
            VoteResult with transaction hash or error.
        """
        pass

    @abstractmethod
    def submit_vote_on_behalf(
        self,
        voter_address: str,
        proposal_id: int,
        vote_option: "VoteChoice",
        relayer_private_key: bytes,
    ) -> VoteResult:
        """Submit a vote on behalf of a user (relayer/node pays gas).

        For Cosmos: Uses MsgExec with Authz
        For EVM: Uses EIP-2771 meta-transaction via Forwarder contract

        Args:
            voter_address: Address of the actual voter (who delegated).
            proposal_id: ID of the proposal to vote on.
            vote_option: The vote choice.
            relayer_private_key: Private key of the relayer who pays gas.

        Returns:
            VoteResult with transaction hash or error.
        """
        pass

    # ==================== Delegation ====================

    @abstractmethod
    def check_delegation(self, delegator: str, delegate: str) -> DelegationInfo:
        """Check if a delegation/authorization exists.

        For Cosmos: Checks for MsgVote Authz grant
        For EVM: Checks token delegation and voting power

        Args:
            delegator: Address of the user who delegates.
            delegate: Address of the node/relayer.

        Returns:
            DelegationInfo with validity and metadata.
        """
        pass

    @abstractmethod
    def get_voting_power(self, address: str) -> int:
        """Get the voting power of an address.

        For Cosmos: Returns staked tokens
        For EVM: Returns delegated ERC20Votes balance

        Args:
            address: Address to check.

        Returns:
            Voting power as integer (in smallest denomination).
        """
        pass

    # ==================== Balance ====================

    @abstractmethod
    def get_balance(self, address: str, token: str | None = None) -> int:
        """Get token balance of an address.

        Args:
            address: Address to check.
            token: Token identifier (denom for Cosmos, address for ERC20).
                  If None, returns native token balance.

        Returns:
            Balance in smallest denomination.
        """
        pass

    # ==================== Utilities ====================

    def close(self):
        """Close any open connections. Override if needed."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def create_chain_adapter(config: Any) -> ChainAdapter:
    """Factory function to create the appropriate chain adapter.

    Args:
        config: Chain configuration with 'type' field.

    Returns:
        ChainAdapter implementation for the specified chain type.

    Raises:
        ValueError: If chain type is not supported.
    """
    chain_type = getattr(config, "type", "cosmos")

    if chain_type == "cosmos" or chain_type == ChainType.COSMOS:
        from chain.cosmos_adapter import CosmosChainAdapter

        return CosmosChainAdapter(config)

    elif chain_type == "evm" or chain_type == ChainType.EVM:
        from chain.evm_adapter import EVMChainAdapter

        return EVMChainAdapter(config)

    else:
        raise ValueError(f"Unsupported chain type: {chain_type}")
