"""Chain interaction modules for Cosmos and EVM blockchains."""

from chain.adapter import ChainAdapter, ChainType, DelegationInfo, VoteResult, create_chain_adapter
from chain.client import ChainClient
from chain.cosmos_adapter import CosmosChainAdapter
from chain.evm_adapter import EVMChainAdapter
from chain.evm_client import EVMChainClient
from chain.evm_meta_tx import (
    ForwardRequest,
    MetaTransactionRelayer,
    create_meta_tx_relayer,
    encode_cast_vote,
    encode_cast_vote_with_reasoning_hash,
    load_forwarder_abi,
    load_governor_abi,
)
from chain.governance import GovernanceClient
from chain.wallet import InsufficientFundsError, WalletManager

__all__ = [
    # Adapters
    "ChainAdapter",
    "ChainType",
    "DelegationInfo",
    "VoteResult",
    "create_chain_adapter",
    "CosmosChainAdapter",
    "EVMChainAdapter",
    # EVM Client
    "EVMChainClient",
    # Meta-Transactions
    "ForwardRequest",
    "MetaTransactionRelayer",
    "create_meta_tx_relayer",
    "encode_cast_vote",
    "encode_cast_vote_with_reasoning_hash",
    "load_forwarder_abi",
    "load_governor_abi",
    # Legacy (Cosmos-specific)
    "ChainClient",
    "GovernanceClient",
    "WalletManager",
    "InsufficientFundsError",
]
