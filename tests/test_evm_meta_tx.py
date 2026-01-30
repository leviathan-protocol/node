"""
Tests for EVM Meta-Transaction Relayer.

Tests EIP-712 typed data signing, signature verification,
and ForwardRequest building without requiring a live chain.
"""

import pytest
from eth_account import Account
from eth_utils import to_checksum_address
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from chain.evm_meta_tx import (
    ForwardRequest,
    MetaTransactionRelayer,
    encode_cast_vote_with_reasoning_hash,
    encode_cast_vote,
    load_forwarder_abi,
)


# Test constants
TEST_CHAIN_ID = 43113  # Fuji testnet
TEST_FORWARDER_ADDRESS = "0x1234567890123456789012345678901234567890"
TEST_GOVERNOR_ADDRESS = "0xabcdef0123456789abcdef0123456789abcdef01"

# Generate a test wallet
TEST_PRIVATE_KEY = "0x" + "1" * 64  # Deterministic test key
TEST_ACCOUNT = Account.from_key(TEST_PRIVATE_KEY)
TEST_USER_ADDRESS = TEST_ACCOUNT.address


@pytest.fixture
def mock_forwarder_abi():
    """Minimal ABI for testing."""
    return [
        {
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "nonces",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {
                    "components": [
                        {"name": "from", "type": "address"},
                        {"name": "to", "type": "address"},
                        {"name": "value", "type": "uint256"},
                        {"name": "gas", "type": "uint256"},
                        {"name": "nonce", "type": "uint256"},
                        {"name": "deadline", "type": "uint48"},
                        {"name": "data", "type": "bytes"},
                    ],
                    "name": "request",
                    "type": "tuple",
                },
                {"name": "signature", "type": "bytes"},
            ],
            "name": "execute",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]


@pytest.fixture
def mock_client():
    """Mock EVMChainClient."""
    client = Mock()
    client.chain_id = TEST_CHAIN_ID
    client.w3 = MagicMock()
    client.w3.eth.gas_price = 25_000_000_000  # 25 gwei
    client.w3.eth.max_priority_fee = 1_000_000_000  # 1 gwei
    client.account = Mock()
    client.account.address = "0x9999999999999999999999999999999999999999"
    client.get_nonce.return_value = 0
    client.send_transaction.return_value = "0x" + "a" * 64
    return client


@pytest.fixture
def relayer(mock_client, mock_forwarder_abi):
    """Create a relayer with mocked dependencies."""
    # Mock the contract
    mock_contract = MagicMock()
    mock_contract.functions.nonces.return_value.call.return_value = 0

    with patch.object(mock_client.w3.eth, 'contract', return_value=mock_contract):
        rel = MetaTransactionRelayer(
            client=mock_client,
            forwarder_address=TEST_FORWARDER_ADDRESS,
            forwarder_abi=mock_forwarder_abi,
        )
        rel.forwarder = mock_contract
        return rel


class TestForwardRequest:
    """Tests for ForwardRequest dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        request = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=5,
            deadline=1700000000,
            data=b"\x12\x34",
        )

        result = request.to_dict()

        assert result["from"] == to_checksum_address(TEST_USER_ADDRESS)
        assert result["to"] == to_checksum_address(TEST_GOVERNOR_ADDRESS)
        assert result["value"] == 0
        assert result["gas"] == 200_000
        assert result["nonce"] == 5
        assert result["deadline"] == 1700000000
        assert result["data"] == b"\x12\x34"

    def test_to_tuple(self):
        """Test conversion to tuple for contract call."""
        request = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=5,
            deadline=1700000000,
            data=b"\x12\x34",
        )

        result = request.to_tuple()

        assert len(result) == 7
        assert result[0] == to_checksum_address(TEST_USER_ADDRESS)
        assert result[4] == 5  # nonce


class TestMetaTransactionRelayer:
    """Tests for MetaTransactionRelayer."""

    def test_domain(self, relayer):
        """Test EIP-712 domain construction."""
        domain = relayer.domain

        assert domain["name"] == "DAHAOForwarder"
        assert domain["version"] == "1"
        assert domain["chainId"] == TEST_CHAIN_ID
        assert domain["verifyingContract"] == to_checksum_address(TEST_FORWARDER_ADDRESS)

    def test_build_forward_request(self, relayer):
        """Test building a ForwardRequest."""
        data = b"\xde\xad\xbe\xef"

        request = relayer.build_forward_request(
            from_addr=TEST_USER_ADDRESS,
            to_addr=TEST_GOVERNOR_ADDRESS,
            data=data,
            value=0,
            gas=150_000,
            nonce=3,
            deadline=1700000000,
        )

        assert request.from_addr == TEST_USER_ADDRESS
        assert request.to == TEST_GOVERNOR_ADDRESS
        assert request.data == data
        assert request.nonce == 3
        assert request.gas == 150_000

    def test_build_forward_request_defaults(self, relayer):
        """Test ForwardRequest with default values."""
        request = relayer.build_forward_request(
            from_addr=TEST_USER_ADDRESS,
            to_addr=TEST_GOVERNOR_ADDRESS,
            data=b"\x00",
        )

        assert request.value == 0
        assert request.gas == 200_000
        assert request.nonce == 0  # From mocked contract
        assert request.deadline > 0

    def test_get_eip712_typed_data(self, relayer):
        """Test EIP-712 typed data generation."""
        request = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=0,
            deadline=1700000000,
            data=b"\x12\x34",
        )

        typed_data = relayer.get_eip712_typed_data(request)

        assert "types" in typed_data
        assert "domain" in typed_data
        assert "message" in typed_data
        assert typed_data["primaryType"] == "ForwardRequest"
        assert "ForwardRequest" in typed_data["types"]
        assert "EIP712Domain" in typed_data["types"]

    def test_sign_and_verify_request(self, relayer):
        """Test signing and verifying a ForwardRequest."""
        request = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=0,
            deadline=1700000000,
            data=b"\x12\x34",
        )

        # Sign the request
        signature = relayer.sign_request(request, TEST_PRIVATE_KEY)

        # Verify the signature
        is_valid, recovered = relayer.verify_signature(request, signature)

        assert is_valid is True
        assert recovered == to_checksum_address(TEST_USER_ADDRESS)

    def test_verify_signature_wrong_signer(self, relayer):
        """Test that wrong signer is detected."""
        wrong_key = "0x" + "2" * 64
        wrong_account = Account.from_key(wrong_key)

        request = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,  # Expect this signer
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=0,
            deadline=1700000000,
            data=b"\x12\x34",
        )

        # Sign with wrong key
        signature = relayer.sign_request(request, wrong_key)

        # Verify should fail
        is_valid, recovered = relayer.verify_signature(request, signature)

        assert is_valid is False
        assert recovered == to_checksum_address(wrong_account.address)
        assert recovered != to_checksum_address(TEST_USER_ADDRESS)

    def test_different_nonces_different_signatures(self, relayer):
        """Test that different nonces produce different signatures."""
        request1 = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=0,
            deadline=1700000000,
            data=b"\x12\x34",
        )

        request2 = ForwardRequest(
            from_addr=TEST_USER_ADDRESS,
            to=TEST_GOVERNOR_ADDRESS,
            value=0,
            gas=200_000,
            nonce=1,  # Different nonce
            deadline=1700000000,
            data=b"\x12\x34",
        )

        sig1 = relayer.sign_request(request1, TEST_PRIVATE_KEY)
        sig2 = relayer.sign_request(request2, TEST_PRIVATE_KEY)

        assert sig1 != sig2


class TestEncodeFunctions:
    """Tests for vote encoding functions."""

    def test_encode_cast_vote(self):
        """Test encoding castVote function call."""
        data = encode_cast_vote(proposal_id=42, support=1)

        # Should have 4 byte selector + 64 bytes params (2 * 32)
        assert len(data) == 4 + 64

        # First 4 bytes are function selector
        selector = data[:4]
        assert len(selector) == 4

    def test_encode_cast_vote_with_reasoning_hash(self):
        """Test encoding castVoteWithReasoningHash function call."""
        reasoning_hash = bytes.fromhex("ab" * 32)

        data = encode_cast_vote_with_reasoning_hash(
            proposal_id=42,
            support=1,
            reasoning_hash=reasoning_hash,
        )

        # Should have 4 byte selector + 96 bytes params (3 * 32)
        assert len(data) == 4 + 96

    def test_encode_different_supports(self):
        """Test encoding different vote types."""
        against = encode_cast_vote(proposal_id=1, support=0)
        for_vote = encode_cast_vote(proposal_id=1, support=1)
        abstain = encode_cast_vote(proposal_id=1, support=2)

        # Same selector, different params
        assert against[:4] == for_vote[:4] == abstain[:4]
        assert against[4:] != for_vote[4:]
        assert for_vote[4:] != abstain[4:]


class TestLoadABI:
    """Tests for ABI loading."""

    def test_load_forwarder_abi_not_found(self):
        """Test error when ABI file doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_forwarder_abi(Path("/nonexistent/path/abi.json"))

        assert "Forwarder ABI not found" in str(exc_info.value)

    def test_load_forwarder_abi_from_artifacts(self):
        """Test loading ABI from compiled artifacts (if available)."""
        abi_path = Path(__file__).parent.parent / "contracts" / "artifacts" / "src" / "DAHAOForwarder.sol" / "DAHAOForwarder.json"

        if not abi_path.exists():
            pytest.skip("Contracts not compiled - run 'npx hardhat compile' first")

        abi = load_forwarder_abi(abi_path)

        assert isinstance(abi, list)
        assert len(abi) > 0

        # Check for expected functions
        function_names = [f.get("name") for f in abi if f.get("type") == "function"]
        assert "execute" in function_names
        assert "nonces" in function_names


class TestEndToEndSigning:
    """End-to-end tests for the full signing flow."""

    def test_full_vote_signing_flow(self, relayer):
        """Test the complete flow of building, signing, and verifying a vote."""
        # 1. Encode vote call
        proposal_id = 123
        support = 1  # For
        reasoning_hash = bytes.fromhex("cafe" * 16)

        call_data = encode_cast_vote_with_reasoning_hash(
            proposal_id=proposal_id,
            support=support,
            reasoning_hash=reasoning_hash,
        )

        # 2. Build ForwardRequest
        request = relayer.build_forward_request(
            from_addr=TEST_USER_ADDRESS,
            to_addr=TEST_GOVERNOR_ADDRESS,
            data=call_data,
            nonce=0,
            deadline=1700000000,
        )

        # 3. Get typed data (what user would see)
        typed_data = relayer.get_eip712_typed_data(request)
        assert typed_data["message"]["from"] == to_checksum_address(TEST_USER_ADDRESS)
        assert typed_data["message"]["to"] == to_checksum_address(TEST_GOVERNOR_ADDRESS)

        # 4. User signs (simulated)
        signature = relayer.sign_request(request, TEST_PRIVATE_KEY)
        assert len(signature) == 65  # r(32) + s(32) + v(1)

        # 5. Verify signature (what node does before submitting)
        is_valid, recovered = relayer.verify_signature(request, signature)
        assert is_valid
        assert recovered == to_checksum_address(TEST_USER_ADDRESS)

        print(f"\n✅ Full signing flow verified:")
        print(f"   User: {TEST_USER_ADDRESS[:10]}...")
        print(f"   Proposal: {proposal_id}")
        print(f"   Support: {'For' if support == 1 else 'Against' if support == 0 else 'Abstain'}")
        print(f"   Signature: {signature.hex()[:20]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
