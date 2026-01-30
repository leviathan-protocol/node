"""EVM chain adapter implementation for Avalanche C-Chain and other EVM networks.

Provides governance operations using:
- Web3.py for chain interactions (via EVMChainClient)
- OpenZeppelin Governor contracts for proposals and voting
- EIP-2771 meta-transactions for gasless voting via Forwarder contract

Supported networks:
- Avalanche C-Chain (Mainnet: 43114, Fuji Testnet: 43113)
- Any EVM-compatible chain with Governor contracts
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eth_utils import to_checksum_address

from chain.adapter import ChainAdapter, ChainType, DelegationInfo, VoteResult
from chain.evm_client import EVMChainClient
from chain.evm_meta_tx import (
    ForwardRequest,
    MetaTransactionRelayer,
    encode_cast_vote,
    encode_cast_vote_with_reasoning_hash,
    load_forwarder_abi,
    load_governor_abi,
)
from models.proposal import Proposal, ProposalStatus
from models.vote import VoteChoice

if TYPE_CHECKING:
    from config.settings import ChainConfig

logger = logging.getLogger(__name__)

# Vote option mapping for Governor contracts
# OpenZeppelin Governor uses: 0=Against, 1=For, 2=Abstain
GOVERNOR_VOTE_MAP = {
    VoteChoice.NO: 0,
    VoteChoice.YES: 1,
    VoteChoice.ABSTAIN: 2,
    VoteChoice.NO_WITH_VETO: 0,  # EVM doesn't have NO_WITH_VETO, map to NO
}

# Minimal ERC20Votes ABI for voting power and delegation queries
ERC20_VOTES_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "getVotes",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "delegates",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Minimal Governor ABI for state queries and events
GOVERNOR_ABI = [
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "state",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "proposalSnapshot",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "proposalDeadline",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "proposalId", "type": "uint256"},
            {"indexed": False, "name": "proposer", "type": "address"},
            {"indexed": False, "name": "targets", "type": "address[]"},
            {"indexed": False, "name": "values", "type": "uint256[]"},
            {"indexed": False, "name": "signatures", "type": "string[]"},
            {"indexed": False, "name": "calldatas", "type": "bytes[]"},
            {"indexed": False, "name": "voteStart", "type": "uint256"},
            {"indexed": False, "name": "voteEnd", "type": "uint256"},
            {"indexed": False, "name": "description", "type": "string"},
        ],
        "name": "ProposalCreated",
        "type": "event",
    },
]


class EVMChainAdapter(ChainAdapter):
    """Chain adapter for EVM chains (Avalanche, Ethereum, etc.).

    Uses:
    - EVMChainClient for low-level Web3 operations
    - OpenZeppelin Governor for governance proposals and voting
    - ERC20Votes for token delegation and voting power
    - EIP-2771 Forwarder for meta-transactions (gasless voting)

    Contract addresses must be configured:
    - governor_address: The Governor contract
    - token_address: The ERC20Votes token contract
    - forwarder_address: The EIP-2771 Forwarder contract (for gasless)
    """

    def __init__(self, config: "ChainConfig"):
        self.config = config
        self._client: EVMChainClient | None = None
        self._governor_contract: Any = None
        self._token_contract: Any = None
        self._forwarder_contract: Any = None
        self._meta_tx_relayer: MetaTransactionRelayer | None = None
        self._relayer_private_key: str | None = None

    @property
    def chain_type(self) -> ChainType:
        return ChainType.EVM

    @property
    def chain_id(self) -> str:
        return str(self.config.chain_id)

    @property
    def is_connected(self) -> bool:
        try:
            if self._client is None:
                return False
            return self._client.is_connected
        except Exception:
            return False

    @property
    def client(self) -> EVMChainClient:
        """Lazy-initialize EVMChainClient."""
        if self._client is None:
            self._initialize_client()
        return self._client

    @property
    def web3(self):
        """Return Web3 instance from client."""
        return self.client.web3

    def _initialize_client(self):
        """Initialize EVMChainClient with relayer private key."""
        logger.info(f"Connecting to EVM chain {self.config.chain_id} at {self.config.rpc_url}")

        # Get relayer private key from environment
        self._relayer_private_key = os.environ.get("RELAYER_PRIVATE_KEY")

        self._client = EVMChainClient(
            rpc_url=self.config.rpc_url,
            private_key=self._relayer_private_key,
        )

        if not self._client.is_connected:
            raise ConnectionError(f"Failed to connect to {self.config.rpc_url}")

        logger.info(f"Connected to EVM chain. Block: {self._client.block_number}")

        if self._relayer_private_key:
            logger.info(f"Relayer wallet: {self._client.account.address}")
        else:
            logger.warning("No RELAYER_PRIVATE_KEY set - gasless voting disabled")

    def _get_governor_contract(self):
        """Get or create Governor contract instance."""
        if self._governor_contract is None:
            if not self.config.governor_address:
                raise ValueError("Governor address not configured")

            # Try to load full ABI from artifacts, fall back to minimal ABI
            try:
                abi = load_governor_abi()
            except FileNotFoundError:
                logger.warning("Governor ABI not found in artifacts, using minimal ABI")
                abi = GOVERNOR_ABI

            self._governor_contract = self.web3.eth.contract(
                address=to_checksum_address(self.config.governor_address),
                abi=abi,
            )

        return self._governor_contract

    def _get_token_contract(self):
        """Get or create ERC20Votes token contract instance."""
        if self._token_contract is None:
            if not self.config.token_address:
                raise ValueError("Token address not configured")

            self._token_contract = self.web3.eth.contract(
                address=to_checksum_address(self.config.token_address),
                abi=ERC20_VOTES_ABI,
            )

        return self._token_contract

    def _get_meta_tx_relayer(self) -> MetaTransactionRelayer:
        """Get or create MetaTransactionRelayer."""
        if self._meta_tx_relayer is None:
            if not self.config.forwarder_address:
                raise ValueError("Forwarder address not configured for gasless voting")

            if not self._relayer_private_key:
                raise ValueError(
                    "RELAYER_PRIVATE_KEY not set. Required for gasless voting."
                )

            # Load forwarder ABI
            try:
                forwarder_abi = load_forwarder_abi()
            except FileNotFoundError:
                raise ValueError(
                    "Forwarder ABI not found. Run 'npx hardhat compile' in contracts/"
                )

            self._meta_tx_relayer = MetaTransactionRelayer(
                client=self.client,
                forwarder_address=self.config.forwarder_address,
                forwarder_abi=forwarder_abi,
            )

        return self._meta_tx_relayer

    # ==================== Governance ====================

    def fetch_proposals(self, status: str | None = None) -> list[Proposal]:
        """Fetch governance proposals from Governor contract events.

        Queries ProposalCreated events to build proposal list.
        Filters by current state if status is specified.

        Args:
            status: Optional filter (e.g., "VOTING_PERIOD", "PASSED")

        Returns:
            List of Proposal objects
        """
        try:
            governor = self._get_governor_contract()

            # Query ProposalCreated events from recent blocks
            # In production, you'd use a subgraph or indexed database
            current_block = self.client.block_number
            from_block = max(0, current_block - 100000)  # Last ~100k blocks

            logger.debug(f"Fetching ProposalCreated events from block {from_block}")

            # Get events
            event_filter = governor.events.ProposalCreated.create_filter(
                from_block=from_block,
                to_block="latest",
            )
            events = event_filter.get_all_entries()

            proposals = []
            for event in events:
                try:
                    proposal = self._parse_proposal_event(event, governor)
                    if proposal:
                        # Filter by status if specified
                        if status is None or proposal.status.name == status:
                            proposals.append(proposal)
                except Exception as e:
                    logger.warning(f"Failed to parse proposal event: {e}")
                    continue

            logger.info(f"Found {len(proposals)} proposals from events")
            return proposals

        except Exception as e:
            logger.warning(f"Failed to fetch proposals from events: {e}")
            logger.warning("Returning mock proposals")
            return self._get_mock_proposals()

    def _parse_proposal_event(self, event: Any, governor: Any) -> Proposal | None:
        """Parse a ProposalCreated event into a Proposal object."""
        args = event["args"]
        proposal_id = args["proposalId"]

        # Get current state
        state = governor.functions.state(proposal_id).call()
        status = self._map_governor_state(state)

        # Parse description - format is usually "# Title\n\nDescription"
        description = args.get("description", "")
        lines = description.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else f"Proposal #{proposal_id}"
        desc_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else description

        # Get timing from event
        vote_start = args.get("voteStart", 0)
        vote_end = args.get("voteEnd", 0)

        # Convert block numbers to approximate timestamps
        # Assuming ~2 second blocks for Avalanche
        block_time = self.web3.eth.get_block("latest")["timestamp"]
        current_block = self.client.block_number

        start_time = datetime.fromtimestamp(
            block_time - (current_block - vote_start) * 2, tz=timezone.utc
        ) if vote_start else datetime.now(timezone.utc)

        end_time = datetime.fromtimestamp(
            block_time + (vote_end - current_block) * 2, tz=timezone.utc
        ) if vote_end else datetime.now(timezone.utc)

        return Proposal(
            id=proposal_id,
            title=title,
            description=desc_body,
            status=status,
            submit_time=start_time,
            voting_start_time=start_time,
            voting_end_time=end_time,
            proposal_type="Governor",
            proposer=args.get("proposer", ""),
        )

    def _get_mock_proposals(self) -> list[Proposal]:
        """Return mock proposals for testing."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        return [
            Proposal(
                id=1,
                title="[EVM Mock] Increase Treasury Allocation",
                description="Proposal to increase community treasury from 5% to 10%",
                status=ProposalStatus.VOTING_PERIOD,
                submit_time=now,
                voting_start_time=now,
                voting_end_time=now + timedelta(days=7),
                proposal_type="Governor",
            ),
        ]

    def get_proposal(self, proposal_id: int) -> Proposal | None:
        """Fetch a single proposal by ID from Governor contract."""
        try:
            governor = self._get_governor_contract()

            # Get proposal state
            state = governor.functions.state(proposal_id).call()
            status = self._map_governor_state(state)

            # Get timing
            snapshot = governor.functions.proposalSnapshot(proposal_id).call()
            deadline = governor.functions.proposalDeadline(proposal_id).call()

            return Proposal(
                id=proposal_id,
                title=f"Proposal #{proposal_id}",
                description="Description from events (not stored on-chain)",
                status=status,
                proposal_type="Governor",
            )

        except ValueError as e:
            logger.warning(f"Configuration error: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch proposal {proposal_id}: {e}")
            return None

    def _map_governor_state(self, state: int) -> ProposalStatus:
        """Map OpenZeppelin Governor state to ProposalStatus."""
        # Governor states: Pending=0, Active=1, Canceled=2, Defeated=3,
        # Succeeded=4, Queued=5, Expired=6, Executed=7
        state_map = {
            0: ProposalStatus.DEPOSIT_PERIOD,  # Pending
            1: ProposalStatus.VOTING_PERIOD,  # Active
            2: ProposalStatus.REJECTED,  # Canceled
            3: ProposalStatus.REJECTED,  # Defeated
            4: ProposalStatus.PASSED,  # Succeeded
            5: ProposalStatus.PASSED,  # Queued
            6: ProposalStatus.REJECTED,  # Expired
            7: ProposalStatus.PASSED,  # Executed
        }
        return state_map.get(state, ProposalStatus.UNSPECIFIED)

    def submit_vote(
        self,
        voter_address: str,
        proposal_id: int,
        vote_option: VoteChoice,
        private_key: bytes | None = None,
    ) -> VoteResult:
        """Submit a vote directly (voter pays gas)."""
        logger.info(f"EVM vote: {vote_option.name} for proposal #{proposal_id}")

        try:
            if not private_key:
                raise ValueError("Private key required for direct voting")

            governor = self._get_governor_contract()
            support = GOVERNOR_VOTE_MAP[vote_option]

            # Create a temporary client with the voter's private key
            from eth_account import Account

            account = Account.from_key(private_key)

            # Build transaction
            tx = governor.functions.castVote(proposal_id, support).build_transaction(
                {
                    "from": account.address,
                    "nonce": self.client.get_nonce(account.address),
                    "gas": self.config.gas_limit,
                    "gasPrice": self.client.web3.eth.gas_price,
                    "chainId": self.client.chain_id,
                }
            )

            # Sign and send
            signed_tx = account.sign_transaction(tx)
            tx_hash = self.client.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            # Wait for receipt
            receipt = self.client.wait_for_receipt(tx_hash_hex)

            return VoteResult(
                success=receipt["status"] == 1,
                tx_hash=tx_hash_hex,
                block_number=receipt["blockNumber"],
                gas_used=receipt["gasUsed"],
            )

        except ValueError as e:
            return VoteResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Failed to submit EVM vote: {e}")
            return VoteResult(success=False, error=str(e))

    def submit_vote_on_behalf(
        self,
        voter_address: str,
        proposal_id: int,
        vote_option: VoteChoice,
        signature: bytes,
        reasoning_hash: bytes | None = None,
    ) -> VoteResult:
        """Submit a vote on behalf of a user using EIP-2771 meta-transaction.

        Flow:
        1. User signed a ForwardRequest (EIP-712) off-chain
        2. Build the ForwardRequest with encoded vote call
        3. Relayer calls Forwarder.execute() and pays gas
        4. Forwarder verifies signature and calls Governor
        5. Governor sees user as msg.sender (via ERC2771Context)

        Args:
            voter_address: User's address (signer of the ForwardRequest)
            proposal_id: ID of the proposal to vote on
            vote_option: Vote choice (YES, NO, ABSTAIN)
            signature: EIP-712 signature from user
            reasoning_hash: Optional IPFS hash of reasoning (bytes32)

        Returns:
            VoteResult with tx_hash if successful
        """
        logger.info(
            f"EVM vote on behalf: voter={voter_address[:10]}..., "
            f"proposal={proposal_id}, vote={vote_option.name}"
        )

        try:
            relayer = self._get_meta_tx_relayer()
            support = GOVERNOR_VOTE_MAP[vote_option]

            # Encode the vote call
            if reasoning_hash:
                call_data = encode_cast_vote_with_reasoning_hash(
                    proposal_id=proposal_id,
                    support=support,
                    reasoning_hash=reasoning_hash,
                )
            else:
                call_data = encode_cast_vote(
                    proposal_id=proposal_id,
                    support=support,
                )

            # Build ForwardRequest
            request = relayer.build_forward_request(
                from_addr=voter_address,
                to_addr=self.config.governor_address,
                data=call_data,
                gas=150_000,
            )

            # Verify signature matches the user
            is_valid, recovered = relayer.verify_signature(request, signature)
            if not is_valid:
                return VoteResult(
                    success=False,
                    error=f"Invalid signature: expected {voter_address}, recovered {recovered}",
                )

            # Execute meta-transaction (relayer pays gas)
            receipt = relayer.execute_and_wait(request, signature)

            success = receipt["status"] == 1
            tx_hash = receipt["transactionHash"].hex()

            if success:
                logger.info(f"Vote executed successfully: tx={tx_hash}")
            else:
                logger.error(f"Vote transaction failed: tx={tx_hash}")

            return VoteResult(
                success=success,
                tx_hash=tx_hash,
                block_number=receipt["blockNumber"],
                gas_used=receipt["gasUsed"],
            )

        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            return VoteResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Failed to submit EVM vote on behalf: {e}")
            return VoteResult(success=False, error=str(e))

    def build_forward_request(
        self,
        voter_address: str,
        proposal_id: int,
        vote_option: VoteChoice,
        reasoning_hash: bytes | None = None,
    ) -> tuple[ForwardRequest, dict]:
        """Build a ForwardRequest for the user to sign.

        Called when preparing the vote intent for user signing.

        Args:
            voter_address: User's address
            proposal_id: ID of the proposal
            vote_option: Vote choice
            reasoning_hash: Optional reasoning IPFS hash

        Returns:
            Tuple of (ForwardRequest, EIP712TypedData for signing)
        """
        relayer = self._get_meta_tx_relayer()
        support = GOVERNOR_VOTE_MAP[vote_option]

        # Encode vote call
        if reasoning_hash:
            call_data = encode_cast_vote_with_reasoning_hash(
                proposal_id=proposal_id,
                support=support,
                reasoning_hash=reasoning_hash,
            )
        else:
            call_data = encode_cast_vote(
                proposal_id=proposal_id,
                support=support,
            )

        # Build request
        request = relayer.build_forward_request(
            from_addr=voter_address,
            to_addr=self.config.governor_address,
            data=call_data,
            gas=150_000,
        )

        # Get EIP-712 typed data for signing
        typed_data = relayer.get_eip712_typed_data(request)

        return request, typed_data

    # ==================== Delegation ====================

    def check_delegation(self, delegator: str, delegate: str) -> DelegationInfo:
        """Check token delegation for ERC20Votes.

        In ERC20Votes, users delegate their voting power to an address.
        The delegate can vote with the combined power of all delegators.

        Args:
            delegator: Address that delegated
            delegate: Address that received delegation

        Returns:
            DelegationInfo with validity and voting power
        """
        try:
            token = self._get_token_contract()

            # Get current delegate
            current_delegate = token.functions.delegates(
                to_checksum_address(delegator)
            ).call()
            is_delegated = current_delegate.lower() == delegate.lower()

            # Get voting power of the delegate
            voting_power = 0
            if is_delegated:
                voting_power = token.functions.getVotes(
                    to_checksum_address(delegate)
                ).call()

            return DelegationInfo(
                delegator=delegator,
                delegate=delegate,
                is_valid=is_delegated,
                voting_power=voting_power,
                chain_type=ChainType.EVM,
            )

        except ValueError as e:
            logger.warning(f"Configuration error: {e}")
            return DelegationInfo(
                delegator=delegator,
                delegate=delegate,
                is_valid=False,
                chain_type=ChainType.EVM,
            )
        except Exception as e:
            logger.warning(f"Failed to check EVM delegation: {e}")
            return DelegationInfo(
                delegator=delegator,
                delegate=delegate,
                is_valid=False,
                chain_type=ChainType.EVM,
            )

    def get_voting_power(self, address: str) -> int:
        """Get voting power from ERC20Votes token.

        Args:
            address: Address to check

        Returns:
            Voting power (in token wei)
        """
        try:
            token = self._get_token_contract()
            return token.functions.getVotes(to_checksum_address(address)).call()
        except ValueError:
            return 0
        except Exception as e:
            logger.warning(f"Failed to get EVM voting power: {e}")
            return 0

    # ==================== Balance ====================

    def get_balance(self, address: str, token: str | None = None) -> int:
        """Get token balance of an address.

        Args:
            address: Address to check
            token: Optional ERC20 token address. None for native token.

        Returns:
            Balance in wei
        """
        try:
            if token is None:
                # Native token (AVAX, ETH)
                return self.client.get_balance(address)
            else:
                # ERC20 token
                erc20_abi = [
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function",
                    }
                ]
                contract = self.web3.eth.contract(
                    address=to_checksum_address(token),
                    abi=erc20_abi,
                )
                return contract.functions.balanceOf(
                    to_checksum_address(address)
                ).call()

        except Exception as e:
            logger.warning(f"Failed to get EVM balance: {e}")
            return 0

    def close(self):
        """Close Web3 connection."""
        self._client = None
        self._governor_contract = None
        self._token_contract = None
        self._forwarder_contract = None
        self._meta_tx_relayer = None
