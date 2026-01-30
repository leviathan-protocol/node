"""
EVM Meta-Transaction Relayer for DAHAO Gasless Voting.

Implements EIP-712 typed data signing for ERC2771 ForwardRequests,
allowing users to sign voting intents off-chain while the node
pays gas fees to execute the transaction.

Flow:
1. User signs ForwardRequest (EIP-712 typed data)
2. Node receives signature + request
3. Node calls forwarder.execute(request, signature) and pays gas
4. Forwarder verifies signature, forwards call to Governor
5. Governor sees user as msg.sender (via ERC2771Context)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_typing import ChecksumAddress
from eth_utils import keccak, to_checksum_address
from web3 import Web3

if TYPE_CHECKING:
    from chain.evm_client import EVMChainClient

logger = logging.getLogger(__name__)

# Default path to compiled forwarder ABI
DEFAULT_FORWARDER_ABI_PATH = Path(__file__).parent.parent / "contracts" / "artifacts" / "src" / "DAHAOForwarder.sol" / "DAHAOForwarder.json"


@dataclass
class ForwardRequest:
    """ERC2771 ForwardRequest structure."""
    from_addr: str  # User's address
    to: str  # Target contract (DAHAOGovernor)
    value: int  # ETH value (usually 0 for voting)
    gas: int  # Gas limit for the forwarded call
    nonce: int  # User's nonce in forwarder
    deadline: int  # Request expiration (uint48 timestamp)
    data: bytes  # Encoded function call

    def to_dict(self) -> dict:
        """Convert to dictionary for ABI encoding."""
        return {
            "from": to_checksum_address(self.from_addr),
            "to": to_checksum_address(self.to),
            "value": self.value,
            "gas": self.gas,
            "nonce": self.nonce,
            "deadline": self.deadline,
            "data": self.data,
        }

    def to_tuple(self) -> tuple:
        """Convert to tuple for contract call."""
        return (
            to_checksum_address(self.from_addr),
            to_checksum_address(self.to),
            self.value,
            self.gas,
            self.nonce,
            self.deadline,
            self.data,
        )


def load_forwarder_abi(abi_path: Path | None = None) -> list:
    """Load DAHAOForwarder ABI from compiled artifacts.

    Args:
        abi_path: Path to ABI JSON file. Uses default if not provided.

    Returns:
        ABI as a list of function/event definitions.

    Raises:
        FileNotFoundError: If ABI file doesn't exist.
    """
    path = abi_path or DEFAULT_FORWARDER_ABI_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Forwarder ABI not found at {path}. "
            "Run 'npx hardhat compile' in contracts/ directory first."
        )

    with open(path) as f:
        artifact = json.load(f)

    return artifact["abi"]


def load_governor_abi(abi_path: Path | None = None) -> list:
    """Load DAHAOGovernor ABI from compiled artifacts."""
    default_path = Path(__file__).parent.parent / "contracts" / "artifacts" / "src" / "DAHAOGovernor.sol" / "DAHAOGovernor.json"
    path = abi_path or default_path

    if not path.exists():
        raise FileNotFoundError(f"Governor ABI not found at {path}")

    with open(path) as f:
        artifact = json.load(f)

    return artifact["abi"]


class MetaTransactionRelayer:
    """
    Relayer for ERC2771 meta-transactions.

    Builds ForwardRequests, generates EIP-712 typed data for signing,
    and submits signed requests to the forwarder contract.

    Example:
        ```python
        from chain.evm_client import EVMChainClient
        from chain.evm_meta_tx import MetaTransactionRelayer, load_forwarder_abi

        client = EVMChainClient(rpc_url, private_key)
        relayer = MetaTransactionRelayer(
            client=client,
            forwarder_address="0x...",
            forwarder_abi=load_forwarder_abi(),
        )

        # Build request for user
        request = relayer.build_forward_request(
            from_addr=user_address,
            to_addr=governor_address,
            data=encoded_vote_call,
        )

        # User signs the request (off-chain)
        typed_data = relayer.get_eip712_typed_data(request)
        signature = user_wallet.sign_typed_data(typed_data)

        # Relayer executes (pays gas)
        tx_hash = relayer.execute(request, signature)
        ```
    """

    # EIP-712 type definitions for ForwardRequest
    EIP712_TYPES = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "ForwardRequest": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "gas", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint48"},
            {"name": "data", "type": "bytes"},
        ],
    }

    def __init__(
        self,
        client: "EVMChainClient",
        forwarder_address: str,
        forwarder_abi: list,
        name: str = "DAHAOForwarder",
        version: str = "1",
    ):
        """
        Initialize the meta-transaction relayer.

        Args:
            client: EVMChainClient instance for chain interactions
            forwarder_address: Address of deployed DAHAOForwarder contract
            forwarder_abi: ABI of the forwarder contract
            name: EIP-712 domain name (must match contract)
            version: EIP-712 domain version (must match contract)
        """
        self.client = client
        self.forwarder_address = to_checksum_address(forwarder_address)
        self.name = name
        self.version = version

        # Create contract instance
        self.forwarder = client.w3.eth.contract(
            address=self.forwarder_address,
            abi=forwarder_abi,
        )

        # Cache domain separator
        self._domain: dict | None = None

    @property
    def domain(self) -> dict:
        """Get EIP-712 domain for signing."""
        if self._domain is None:
            self._domain = {
                "name": self.name,
                "version": self.version,
                "chainId": self.client.chain_id,
                "verifyingContract": self.forwarder_address,
            }
        return self._domain

    def get_nonce(self, address: str) -> int:
        """Get user's current nonce from forwarder contract.

        Args:
            address: User's address

        Returns:
            Current nonce (next valid nonce for ForwardRequest)
        """
        return self.forwarder.functions.nonces(
            to_checksum_address(address)
        ).call()

    def build_forward_request(
        self,
        from_addr: str,
        to_addr: str,
        data: bytes,
        value: int = 0,
        gas: int = 200_000,
        deadline: int | None = None,
        nonce: int | None = None,
    ) -> ForwardRequest:
        """
        Build a ForwardRequest for meta-transaction.

        Args:
            from_addr: User's address (will be msg.sender in target)
            to_addr: Target contract address (DAHAOGovernor)
            data: Encoded function call data
            value: ETH value to send (usually 0 for voting)
            gas: Gas limit for the forwarded call
            deadline: Request expiration timestamp (default: 1 hour from now)
            nonce: User's nonce (default: fetch from contract)

        Returns:
            ForwardRequest ready for signing
        """
        if nonce is None:
            nonce = self.get_nonce(from_addr)

        if deadline is None:
            # Default: 1 hour from now
            deadline = int(time.time()) + 3600

        return ForwardRequest(
            from_addr=from_addr,
            to=to_addr,
            value=value,
            gas=gas,
            nonce=nonce,
            deadline=deadline,
            data=data,
        )

    def get_eip712_typed_data(self, request: ForwardRequest) -> dict:
        """
        Get EIP-712 typed data structure for signing.

        This is what the user signs off-chain.

        Args:
            request: ForwardRequest to sign

        Returns:
            EIP-712 typed data dict (domain, types, primaryType, message)
        """
        return {
            "types": self.EIP712_TYPES,
            "primaryType": "ForwardRequest",
            "domain": self.domain,
            "message": {
                "from": to_checksum_address(request.from_addr),
                "to": to_checksum_address(request.to),
                "value": request.value,
                "gas": request.gas,
                "nonce": request.nonce,
                "deadline": request.deadline,
                "data": request.data,
            },
        }

    def sign_request(self, request: ForwardRequest, private_key: str | bytes) -> bytes:
        """
        Sign a ForwardRequest with a private key.

        Utility method for testing. In production, users sign on their devices.

        Args:
            request: ForwardRequest to sign
            private_key: Private key to sign with

        Returns:
            Signature bytes (65 bytes: r + s + v)
        """
        typed_data = self.get_eip712_typed_data(request)

        # eth_account expects specific format
        signable = encode_typed_data(full_message=typed_data)
        signed = Account.sign_message(signable, private_key)

        return signed.signature

    def verify_signature(
        self,
        request: ForwardRequest,
        signature: bytes,
        expected_signer: str | None = None,
    ) -> tuple[bool, str]:
        """
        Verify a signature matches the expected signer.

        Args:
            request: The signed ForwardRequest
            signature: The signature to verify
            expected_signer: Expected signer address (defaults to request.from_addr)

        Returns:
            Tuple of (is_valid, recovered_address)
        """
        typed_data = self.get_eip712_typed_data(request)
        signable = encode_typed_data(full_message=typed_data)

        recovered = Account.recover_message(signable, signature=signature)
        recovered = to_checksum_address(recovered)

        expected = to_checksum_address(expected_signer or request.from_addr)
        is_valid = recovered == expected

        return is_valid, recovered

    def execute(
        self,
        request: ForwardRequest,
        signature: bytes,
        gas_limit: int | None = None,
    ) -> str:
        """
        Execute a signed ForwardRequest via the forwarder contract.

        The relayer (node) pays gas for this transaction.

        Args:
            request: The ForwardRequest
            signature: User's EIP-712 signature
            gas_limit: Gas limit for the execute tx (default: request.gas + 50k overhead)

        Returns:
            Transaction hash

        Raises:
            Exception: If transaction fails
        """
        # Verify signature before submitting
        is_valid, recovered = self.verify_signature(request, signature)
        if not is_valid:
            raise ValueError(
                f"Invalid signature: expected {request.from_addr}, "
                f"recovered {recovered}"
            )

        logger.info(
            f"Executing meta-tx: from={request.from_addr[:10]}..., "
            f"to={request.to[:10]}..., nonce={request.nonce}"
        )

        # Build the execute transaction
        # ForwardRequest struct + signature
        execute_gas = gas_limit or (request.gas + 50_000)  # Add overhead for forwarder

        tx = self.forwarder.functions.execute(
            request.to_tuple(),
            signature,
        ).build_transaction({
            "from": self.client.account.address,
            "gas": execute_gas,
            "nonce": self.client.get_nonce(),
            "maxFeePerGas": self.client.w3.eth.gas_price * 2,
            "maxPriorityFeePerGas": self.client.w3.eth.max_priority_fee,
        })

        # Sign and send
        tx_hash = self.client.send_transaction(tx)
        logger.info(f"Meta-tx submitted: {tx_hash}")

        return tx_hash

    def execute_and_wait(
        self,
        request: ForwardRequest,
        signature: bytes,
        gas_limit: int | None = None,
        timeout: int = 120,
    ) -> dict:
        """
        Execute a ForwardRequest and wait for receipt.

        Args:
            request: The ForwardRequest
            signature: User's EIP-712 signature
            gas_limit: Gas limit for the execute tx
            timeout: Max seconds to wait for receipt

        Returns:
            Transaction receipt dict
        """
        tx_hash = self.execute(request, signature, gas_limit)
        return self.client.wait_for_receipt(tx_hash, timeout)


def encode_cast_vote_with_reasoning_hash(
    proposal_id: int,
    support: int,
    reasoning_hash: bytes,
) -> bytes:
    """
    Encode a castVoteWithReasoningHash call for the Governor.

    Args:
        proposal_id: The proposal ID to vote on
        support: Vote type (0=Against, 1=For, 2=Abstain)
        reasoning_hash: IPFS hash of reasoning document (bytes32)

    Returns:
        Encoded function call data
    """
    # Function selector: keccak256("castVoteWithReasoningHash(uint256,uint8,bytes32)")[:4]
    selector = keccak(text="castVoteWithReasoningHash(uint256,uint8,bytes32)")[:4]

    # Encode parameters
    params = encode(
        ["uint256", "uint8", "bytes32"],
        [proposal_id, support, reasoning_hash],
    )

    return selector + params


def encode_cast_vote(proposal_id: int, support: int) -> bytes:
    """
    Encode a standard castVote call for the Governor.

    Args:
        proposal_id: The proposal ID to vote on
        support: Vote type (0=Against, 1=For, 2=Abstain)

    Returns:
        Encoded function call data
    """
    selector = keccak(text="castVote(uint256,uint8)")[:4]
    params = encode(["uint256", "uint8"], [proposal_id, support])
    return selector + params


# Convenience function for creating relayer from config
def create_meta_tx_relayer(
    client: "EVMChainClient",
    forwarder_address: str,
    abi_path: Path | None = None,
) -> MetaTransactionRelayer:
    """
    Create a MetaTransactionRelayer with loaded ABI.

    Args:
        client: EVMChainClient instance
        forwarder_address: Deployed forwarder contract address
        abi_path: Optional custom path to ABI file

    Returns:
        Configured MetaTransactionRelayer
    """
    abi = load_forwarder_abi(abi_path)
    return MetaTransactionRelayer(
        client=client,
        forwarder_address=forwarder_address,
        forwarder_abi=abi,
    )
