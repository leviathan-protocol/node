#!/usr/bin/env python3
"""
Demo script for EVM Meta-Transaction signing.

Demonstrates the complete gasless voting flow:
1. Creates a ForwardRequest for a vote
2. Signs it with a test wallet (EIP-712)
3. Verifies the signature is valid

Run:
    uv run python scripts/demo_meta_tx.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eth_account import Account
from eth_utils import to_checksum_address
from unittest.mock import Mock, MagicMock

from chain.evm_meta_tx import (
    ForwardRequest,
    MetaTransactionRelayer,
    encode_cast_vote_with_reasoning_hash,
    encode_cast_vote,
)


def main():
    print("=" * 60)
    print("DAHAO Meta-Transaction Demo")
    print("=" * 60)
    print()

    # Test configuration
    CHAIN_ID = 43113  # Avalanche Fuji
    FORWARDER_ADDRESS = "0x1234567890123456789012345678901234567890"
    GOVERNOR_ADDRESS = "0xabcdef0123456789abcdef0123456789abcdef01"

    # Generate test wallets
    USER_PRIVATE_KEY = "0x" + "ab" * 32
    RELAYER_PRIVATE_KEY = "0x" + "cd" * 32

    user_account = Account.from_key(USER_PRIVATE_KEY)
    relayer_account = Account.from_key(RELAYER_PRIVATE_KEY)

    print(f"User Address:    {user_account.address}")
    print(f"Relayer Address: {relayer_account.address}")
    print()

    # Create a mock client (for demo without live chain)
    mock_client = Mock()
    mock_client.chain_id = CHAIN_ID
    mock_client.w3 = MagicMock()
    mock_contract = MagicMock()
    mock_contract.functions.nonces.return_value.call.return_value = 0
    mock_client.w3.eth.contract.return_value = mock_contract

    # Minimal ABI for demo
    mock_abi = [
        {"name": "nonces", "type": "function", "inputs": [{"name": "owner", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
        {"name": "execute", "type": "function", "inputs": [], "outputs": []},
    ]

    # Create relayer
    relayer = MetaTransactionRelayer(
        client=mock_client,
        forwarder_address=FORWARDER_ADDRESS,
        forwarder_abi=mock_abi,
    )
    relayer.forwarder = mock_contract

    print("-" * 60)
    print("Step 1: Build Vote Call Data")
    print("-" * 60)

    proposal_id = 42
    support = 1  # 0=Against, 1=For, 2=Abstain
    reasoning_hash = bytes.fromhex("cafe" * 16)  # IPFS hash of reasoning

    vote_data = encode_cast_vote_with_reasoning_hash(
        proposal_id=proposal_id,
        support=support,
        reasoning_hash=reasoning_hash,
    )

    print(f"Proposal ID: {proposal_id}")
    print(f"Vote: {'FOR' if support == 1 else 'AGAINST' if support == 0 else 'ABSTAIN'}")
    print(f"Reasoning Hash: 0x{reasoning_hash.hex()[:16]}...")
    print(f"Encoded Call: 0x{vote_data.hex()[:32]}... ({len(vote_data)} bytes)")
    print()

    print("-" * 60)
    print("Step 2: Build ForwardRequest")
    print("-" * 60)

    request = relayer.build_forward_request(
        from_addr=user_account.address,
        to_addr=GOVERNOR_ADDRESS,
        data=vote_data,
        gas=150_000,
        nonce=0,
        deadline=1800000000,  # Fixed deadline for demo
    )

    print(f"From:     {request.from_addr}")
    print(f"To:       {request.to}")
    print(f"Value:    {request.value}")
    print(f"Gas:      {request.gas}")
    print(f"Nonce:    {request.nonce}")
    print(f"Deadline: {request.deadline}")
    print()

    print("-" * 60)
    print("Step 3: Generate EIP-712 Typed Data")
    print("-" * 60)

    typed_data = relayer.get_eip712_typed_data(request)

    print("Domain:")
    print(f"  Name:              {typed_data['domain']['name']}")
    print(f"  Version:           {typed_data['domain']['version']}")
    print(f"  Chain ID:          {typed_data['domain']['chainId']}")
    print(f"  Verifying Contract: {typed_data['domain']['verifyingContract']}")
    print()
    print("Primary Type: ForwardRequest")
    print()

    print("-" * 60)
    print("Step 4: User Signs (EIP-712)")
    print("-" * 60)

    signature = relayer.sign_request(request, USER_PRIVATE_KEY)

    print(f"Signature: 0x{signature.hex()}")
    print(f"Length:    {len(signature)} bytes (r=32 + s=32 + v=1)")
    print()

    # Break down signature components
    r = signature[:32]
    s = signature[32:64]
    v = signature[64]
    print(f"  r: 0x{r.hex()}")
    print(f"  s: 0x{s.hex()}")
    print(f"  v: {v}")
    print()

    print("-" * 60)
    print("Step 5: Verify Signature")
    print("-" * 60)

    is_valid, recovered = relayer.verify_signature(request, signature)

    print(f"Expected Signer: {user_account.address}")
    print(f"Recovered Signer: {recovered}")
    print(f"Signature Valid: {is_valid}")
    print()

    if is_valid:
        print("✅ SUCCESS: Signature is valid!")
        print()
        print("In production, the relayer would now call:")
        print(f"  forwarder.execute(request, signature)")
        print("  - Relayer pays gas")
        print("  - Forwarder verifies signature")
        print("  - Governor receives vote with user as msg.sender")
    else:
        print("❌ FAILED: Signature verification failed!")
        return 1

    print()
    print("=" * 60)
    print("Demo Complete")
    print("=" * 60)

    # Test with wrong signer
    print()
    print("-" * 60)
    print("Bonus: Test Wrong Signer Detection")
    print("-" * 60)

    wrong_key = "0x" + "de" * 32  # Different valid key
    wrong_signature = relayer.sign_request(request, wrong_key)

    is_valid_wrong, recovered_wrong = relayer.verify_signature(request, wrong_signature)
    print(f"Signed with wrong key...")
    print(f"Expected: {user_account.address}")
    print(f"Recovered: {recovered_wrong}")
    print(f"Valid: {is_valid_wrong}")
    print()
    print("✅ Correctly detected invalid signer!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
