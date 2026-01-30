#!/usr/bin/env python3
"""
Mock EVM Phone Client - Simulates mobile voting on EVM chains.

This script demonstrates the full gasless voting flow for EVM chains:
1. Connect to Observer Mode node
2. Register voter address
3. Sign EIP-712 ForwardRequest
4. Submit signed vote to node
5. Node executes meta-transaction

Usage:
    # Start observer mode with EVM config
    python main.py --mode observer --config config_evm.yaml

    # Run mock phone
    python tests/mock_phone_evm.py --node-url http://localhost:8000

Requirements:
    - Observer mode running with EVM config
    - eth-account for signing
"""

import argparse
import json
import secrets
import sys
import time
from dataclasses import dataclass

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data


@dataclass
class EVMVoter:
    """Simulated EVM voter with private key."""

    private_key: str
    address: str

    @classmethod
    def generate(cls) -> "EVMVoter":
        """Generate a random voter."""
        private_key = "0x" + secrets.token_hex(32)
        account = Account.from_key(private_key)
        return cls(private_key=private_key, address=account.address)

    @classmethod
    def from_private_key(cls, private_key: str) -> "EVMVoter":
        """Create voter from existing private key."""
        account = Account.from_key(private_key)
        return cls(private_key=private_key, address=account.address)


class MockEVMPhoneClient:
    """Simulates an EVM mobile voting client."""

    def __init__(self, node_url: str, voter: EVMVoter):
        self.node_url = node_url.rstrip("/")
        self.voter = voter
        self.session_token = None
        self.client = httpx.Client(timeout=30)

    def get_invite(self) -> str:
        """Get invite code from node."""
        response = self.client.get(f"{self.node_url}/api/v1/invite")
        response.raise_for_status()
        data = response.json()
        return data["invite_code"]

    def connect(self, invite_code: str) -> dict:
        """Connect to node with invite code."""
        response = self.client.post(
            f"{self.node_url}/api/v1/connect",
            json={"invite_code": invite_code},
        )
        response.raise_for_status()
        data = response.json()
        self.session_token = data.get("session_token")
        return data

    def register(self) -> dict:
        """Register voter address with node."""
        if not self.session_token:
            raise RuntimeError("Not connected - call connect() first")

        response = self.client.post(
            f"{self.node_url}/api/v1/register",
            json={
                "session_token": self.session_token,
                "voter_address": self.voter.address,
                "authz_tx_hash": "evm_delegation_tx",  # Not needed for EVM
            },
        )
        response.raise_for_status()
        return response.json()

    def get_proposals(self) -> list[dict]:
        """Fetch active proposals."""
        response = self.client.get(f"{self.node_url}/api/v1/proposals")
        response.raise_for_status()
        return response.json()["proposals"]

    def sign_eip712_vote(
        self,
        proposal_id: int,
        vote_option: str,
        reasoning: str,
        forwarder_address: str,
        governor_address: str,
        chain_id: int,
        nonce: int = 0,
        deadline: int = None,
    ) -> tuple[bytes, dict]:
        """Sign a vote using EIP-712 typed data.

        Returns:
            Tuple of (signature, typed_data)
        """
        from chain.evm_meta_tx import encode_cast_vote, ForwardRequest

        # Map vote option
        support_map = {"YES": 1, "NO": 0, "ABSTAIN": 2}
        support = support_map.get(vote_option.upper(), 2)

        # Encode vote call
        call_data = encode_cast_vote(proposal_id, support)

        # Build EIP-712 typed data
        if deadline is None:
            deadline = int(time.time()) + 3600  # 1 hour from now

        typed_data = {
            "types": {
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
            },
            "primaryType": "ForwardRequest",
            "domain": {
                "name": "DAHAOForwarder",
                "version": "1",
                "chainId": chain_id,
                "verifyingContract": forwarder_address,
            },
            "message": {
                "from": self.voter.address,
                "to": governor_address,
                "value": 0,
                "gas": 150000,
                "nonce": nonce,
                "deadline": deadline,
                "data": call_data,
            },
        }

        # Sign
        signable = encode_typed_data(full_message=typed_data)
        signed = Account.sign_message(signable, self.voter.private_key)

        return signed.signature, typed_data

    def submit_vote(
        self,
        proposal_id: int,
        vote_option: str,
        reasoning: str,
        eip712_signature: bytes,
        reasoning_hash: str | None = None,
    ) -> dict:
        """Submit signed vote to node."""
        timestamp = int(time.time())
        nonce = secrets.token_hex(16)

        payload = {
            "proposal_id": proposal_id,
            "voter_address": self.voter.address,
            "vote_option": vote_option,
            "public_reasoning": reasoning,
            "confidence_score": 0.85,
            "timestamp": timestamp,
            "nonce": nonce,
            "eip712_signature": "0x" + eip712_signature.hex(),
        }

        if reasoning_hash:
            payload["reasoning_hash"] = reasoning_hash

        response = self.client.post(
            f"{self.node_url}/api/v1/submit_vote",
            json=payload,
        )

        if response.status_code == 200:
            return response.json()
        else:
            return {
                "status": "rejected",
                "status_code": response.status_code,
                **response.json().get("detail", {}),
            }


def run_demo(node_url: str, voter: EVMVoter | None = None):
    """Run the EVM voting demo."""
    print("=" * 60)
    print("DAHAO EVM Mock Phone - Gasless Voting Demo")
    print("=" * 60)
    print()

    # Create voter
    if voter is None:
        voter = EVMVoter.generate()

    print(f"Voter Address: {voter.address}")
    print(f"Node URL: {node_url}")
    print()

    # Create client
    client = MockEVMPhoneClient(node_url, voter)

    # Step 1: Get invite
    print("-" * 40)
    print("Step 1: Get Invite Code")
    print("-" * 40)
    try:
        invite_code = client.get_invite()
        print(f"Invite Code: {invite_code}")
    except Exception as e:
        print(f"ERROR: {e}")
        print("Make sure Observer Mode is running with: python main.py --mode observer")
        return 1
    print()

    # Step 2: Connect
    print("-" * 40)
    print("Step 2: Connect to Node")
    print("-" * 40)
    result = client.connect(invite_code)
    print(f"Status: {result['status']}")
    print(f"Session Token: {result.get('session_token', 'N/A')[:20]}...")
    print()

    # Step 3: Register
    print("-" * 40)
    print("Step 3: Register Voter")
    print("-" * 40)
    result = client.register()
    print(f"Status: {result['status']}")
    print()

    # Step 4: Get Proposals
    print("-" * 40)
    print("Step 4: Fetch Proposals")
    print("-" * 40)
    proposals = client.get_proposals()
    print(f"Found {len(proposals)} proposals")
    for p in proposals[:3]:
        print(f"  - #{p['id']}: {p['title'][:40]}...")
    print()

    if not proposals:
        print("No proposals available to vote on")
        return 0

    # Step 5: Sign and Submit Vote
    print("-" * 40)
    print("Step 5: Sign EIP-712 and Submit Vote")
    print("-" * 40)

    proposal = proposals[0]
    vote_option = "YES"
    reasoning = "This proposal benefits the ecosystem and I support it."

    # For demo, we use dummy contract addresses
    # In production, these come from config or API
    forwarder_address = "0x1234567890123456789012345678901234567890"
    governor_address = "0xabcdef0123456789abcdef0123456789abcdef01"
    chain_id = 43113  # Fuji

    print(f"Proposal: #{proposal['id']} - {proposal['title'][:30]}...")
    print(f"Vote: {vote_option}")
    print(f"Reasoning: {reasoning[:40]}...")
    print()

    # Sign
    print("Signing EIP-712 ForwardRequest...")
    signature, typed_data = client.sign_eip712_vote(
        proposal_id=proposal["id"],
        vote_option=vote_option,
        reasoning=reasoning,
        forwarder_address=forwarder_address,
        governor_address=governor_address,
        chain_id=chain_id,
    )
    print(f"Signature: 0x{signature.hex()[:40]}...")
    print()

    # Submit
    print("Submitting vote to node...")
    result = client.submit_vote(
        proposal_id=proposal["id"],
        vote_option=vote_option,
        reasoning=reasoning,
        eip712_signature=signature,
    )

    print()
    print("=" * 60)
    print("Result")
    print("=" * 60)
    print(json.dumps(result, indent=2))

    if result.get("status") == "broadcasted":
        print()
        print("✅ SUCCESS: Vote submitted via meta-transaction!")
        print(f"   TX Hash: {result.get('tx_hash', 'N/A')}")
        return 0
    else:
        print()
        print(f"❌ FAILED: {result.get('error', 'Unknown error')}")
        print(f"   Detail: {result.get('detail', 'N/A')}")
        # This is expected without a real chain connection
        if "mock" in str(result.get("detail", "")).lower():
            print()
            print("Note: This is expected in mock mode without chain connection")
            return 0
        return 1


def main():
    parser = argparse.ArgumentParser(description="Mock EVM Phone Client")
    parser.add_argument(
        "--node-url",
        default="http://localhost:8000",
        help="Observer Mode node URL",
    )
    parser.add_argument(
        "--private-key",
        help="Voter private key (generates random if not provided)",
    )
    args = parser.parse_args()

    voter = None
    if args.private_key:
        voter = EVMVoter.from_private_key(args.private_key)

    return run_demo(args.node_url, voter)


if __name__ == "__main__":
    sys.exit(main())
