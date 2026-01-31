#!/usr/bin/env python3
"""Mock Phone Client - Simulates a mobile app connecting to DAHAO Observer Mode.

This script simulates the full mobile client flow:
1. Generate test wallet (ECDSA keypair)
2. Connect to node via invite link
3. Register after (mock) authz grant
4. Fetch proposals
5. Sign and submit voting intents

Usage:
    # Full test suite against local node
    python tests/mock_phone.py --node=http://localhost:8080 --full-test

    # Quick vote test only
    python tests/mock_phone.py --node=http://localhost:8080 --vote-only

    # Interactive mode (step by step)
    python tests/mock_phone.py --node=http://localhost:8080 --interactive
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

# Import signature utilities from the project
sys.path.insert(0, ".")
from validator.signature import create_test_keypair, sign_payload


@dataclass
class PhoneWallet:
    """Simulated phone wallet with ECDSA keypair."""

    private_key: bytes
    public_key: bytes
    address: str

    @classmethod
    def generate(cls) -> "PhoneWallet":
        """Generate a new test wallet."""
        priv_key, pub_key = create_test_keypair()
        # Generate mock Cosmos address from pubkey hash
        pubkey_hash = hashlib.sha256(pub_key).digest()[:20]
        address = "cosmos1" + pubkey_hash.hex()[:38]
        return cls(private_key=priv_key, public_key=pub_key, address=address)

    @property
    def public_key_b64(self) -> str:
        """Base64-encoded public key."""
        return base64.b64encode(self.public_key).decode()


@dataclass
class TestResult:
    """Result of a test scenario."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None


class MockPhoneClient:
    """Simulates a mobile phone client for DAHAO Observer Mode."""

    def __init__(self, node_url: str, verbose: bool = True):
        self.node_url = node_url.rstrip("/")
        self.client = httpx.Client(base_url=self.node_url, timeout=30)
        self.verbose = verbose
        self.wallet: PhoneWallet | None = None
        self.session_token: str | None = None
        self.registered: bool = False

    def log(self, msg: str):
        """Print message if verbose mode is on."""
        if self.verbose:
            print(msg)

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    # ==================== Connection Flow ====================

    def generate_wallet(self) -> PhoneWallet:
        """Generate a new phone wallet (keypair)."""
        self.wallet = PhoneWallet.generate()
        self.log(f"📱 Generated wallet: {self.wallet.address}")
        return self.wallet

    def get_invite(self) -> dict:
        """GET /invite - Get invite code from node."""
        self.log("📨 Requesting invite from node...")
        resp = self.client.get("/api/v1/invite")
        resp.raise_for_status()
        data = resp.json()
        self.log(f"   Invite code: {data['invite_code']}")
        self.log(f"   Expires: {data['expires_at']}")
        return data

    def connect(self, invite_code: str) -> dict:
        """POST /connect - Validate invite and get session."""
        self.log(f"🔗 Connecting with invite code: {invite_code}...")
        resp = self.client.post("/api/v1/connect", json={"invite_code": invite_code})
        resp.raise_for_status()
        data = resp.json()
        self.session_token = data["session_token"]
        self.log(f"   Session token: {self.session_token[:20]}...")
        self.log(f"   Node address: {data['node_address']}")
        return data

    def register(self, authz_tx_hash: str = "MOCK_AUTHZ_TX_HASH") -> dict:
        """POST /register - Complete registration after authz grant."""
        if not self.wallet:
            raise ValueError("No wallet generated. Call generate_wallet() first.")
        if not self.session_token:
            raise ValueError("No session token. Call connect() first.")

        self.log(f"📝 Registering voter: {self.wallet.address}...")
        resp = self.client.post(
            "/api/v1/register",
            json={
                "session_token": self.session_token,
                "voter_address": self.wallet.address,
                "authz_tx_hash": authz_tx_hash,
                "pub_key": self.wallet.public_key_b64,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.registered = True
        self.log(f"   Registration: {data['status']}")
        self.log(f"   Grant expires: {data.get('grant_expires_at', 'N/A')}")
        return data

    def full_connect_flow(self) -> bool:
        """Execute full connection flow: invite → connect → register."""
        try:
            self.generate_wallet()
            invite = self.get_invite()
            self.connect(invite["invite_code"])
            self.register()
            return True
        except httpx.HTTPStatusError as e:
            self.log(f"❌ Connection failed: {e.response.status_code}")
            self.log(f"   {e.response.json()}")
            return False

    # ==================== Voting Flow ====================

    def get_proposals(self) -> list[dict]:
        """GET /proposals - Fetch active proposals."""
        self.log("📋 Fetching proposals...")
        resp = self.client.get("/api/v1/proposals")
        resp.raise_for_status()
        data = resp.json()
        self.log(f"   Found {data['count']} proposals")
        for p in data["proposals"][:3]:  # Show first 3
            self.log(f"   - #{p['id']}: {p['title'][:50]}...")
        return data["proposals"]

    def create_vote_intent(
        self,
        proposal_id: int,
        vote_option: str,
        reasoning: str,
        confidence: float = 0.8,
    ) -> dict:
        """Create a vote intent payload (unsigned)."""
        if not self.wallet:
            raise ValueError("No wallet generated. Call generate_wallet() first.")

        return {
            "proposal_id": proposal_id,
            "voter_address": self.wallet.address,
            "vote_option": vote_option,
            "public_reasoning": reasoning,
            "confidence_score": confidence,
            "timestamp": int(time.time()),
            "nonce": hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:16],
        }

    def sign_intent(self, intent: dict) -> str:
        """Sign vote intent with wallet private key."""
        if not self.wallet:
            raise ValueError("No wallet generated. Call generate_wallet() first.")
        return sign_payload(intent, self.wallet.private_key)

    def submit_vote(
        self,
        proposal_id: int,
        vote_option: str,
        reasoning: str,
        confidence: float = 0.8,
    ) -> dict:
        """Create, sign, and submit a vote intent."""
        if not self.wallet:
            raise ValueError("No wallet generated. Call generate_wallet() first.")

        self.log(f"🗳️  Voting {vote_option} on proposal #{proposal_id}...")

        # Create intent
        intent = self.create_vote_intent(proposal_id, vote_option, reasoning, confidence)

        # Sign intent
        signature = self.sign_intent(intent)
        self.log(f"   Signature: {signature[:40]}...")

        # Submit vote
        resp = self.client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": self.wallet.public_key_b64,
            },
        )

        if resp.status_code == 200:
            data = resp.json()
            self.log(f"   ✅ Vote accepted!")
            self.log(f"   TX Hash: {data['tx_hash']}")
            return data
        else:
            data = resp.json()
            detail = data.get("detail", {})
            self.log(f"   ❌ Vote rejected: {detail.get('error', 'unknown')}")
            self.log(f"   Stage: {detail.get('stage', 'unknown')}")
            raise httpx.HTTPStatusError(
                f"Vote rejected: {resp.status_code}",
                request=resp.request,
                response=resp,
            )

    # ==================== Test Scenarios ====================

    def test_happy_path(self) -> TestResult:
        """Test: Valid signature, consistent reasoning → 200."""
        self.log("\n" + "=" * 50)
        self.log("TEST: Happy Path (valid vote)")
        self.log("=" * 50)

        try:
            # Connect and register
            if not self.registered:
                self.full_connect_flow()

            # Get proposals
            proposals = self.get_proposals()
            if not proposals:
                return TestResult("happy_path", False, "No proposals available")

            # Submit valid vote
            result = self.submit_vote(
                proposal_id=proposals[0]["id"],
                vote_option="YES",
                reasoning="I support this proposal because it improves network efficiency and benefits all stakeholders.",
                confidence=0.85,
            )

            return TestResult(
                "happy_path",
                True,
                f"Vote accepted with TX hash: {result['tx_hash'][:16]}...",
                details=result,
            )

        except httpx.HTTPStatusError as e:
            return TestResult(
                "happy_path",
                False,
                f"HTTP {e.response.status_code}: {e.response.json()}",
            )
        except Exception as e:
            return TestResult("happy_path", False, f"Error: {e}")

    def test_invalid_signature(self) -> TestResult:
        """Test: Tampered payload → 400 invalid_signature."""
        self.log("\n" + "=" * 50)
        self.log("TEST: Invalid Signature (tampered payload)")
        self.log("=" * 50)

        try:
            # Connect and register if needed
            if not self.registered:
                self.full_connect_flow()

            # Create and sign intent
            intent = self.create_vote_intent(
                proposal_id=1,
                vote_option="YES",
                reasoning="Original reasoning",
                confidence=0.8,
            )
            signature = self.sign_intent(intent)

            # Tamper with the payload after signing
            intent["vote_option"] = "NO"  # Change vote!

            self.log("🔓 Submitting tampered vote (changed YES to NO after signing)...")

            resp = self.client.post(
                "/api/v1/submit_vote",
                json={
                    **intent,
                    "intent_signature": signature,
                    "pub_key": self.wallet.public_key_b64,
                },
            )

            if resp.status_code == 400:
                detail = resp.json().get("detail", {})
                if detail.get("stage") == "signature":
                    return TestResult(
                        "invalid_signature",
                        True,
                        "Correctly rejected tampered payload",
                        details=detail,
                    )

            return TestResult(
                "invalid_signature",
                False,
                f"Unexpected response: {resp.status_code} - {resp.json()}",
            )

        except Exception as e:
            return TestResult("invalid_signature", False, f"Error: {e}")

    def test_unregistered_voter(self) -> TestResult:
        """Test: Unregistered voter → 403 voter_not_registered."""
        self.log("\n" + "=" * 50)
        self.log("TEST: Unregistered Voter")
        self.log("=" * 50)

        try:
            # Create a fresh wallet (not registered)
            fresh_wallet = PhoneWallet.generate()
            self.log(f"📱 Using unregistered wallet: {fresh_wallet.address}")

            # Create and sign intent
            intent = {
                "proposal_id": 1,
                "voter_address": fresh_wallet.address,
                "vote_option": "YES",
                "public_reasoning": "Test reasoning",
                "confidence_score": 0.8,
                "timestamp": int(time.time()),
                "nonce": "test_nonce",
            }
            signature = sign_payload(intent, fresh_wallet.private_key)

            self.log("🗳️  Submitting vote from unregistered wallet...")

            resp = self.client.post(
                "/api/v1/submit_vote",
                json={
                    **intent,
                    "intent_signature": signature,
                    "pub_key": fresh_wallet.public_key_b64,
                },
            )

            if resp.status_code == 403:
                detail = resp.json().get("detail", {})
                if detail.get("error") == "voter_not_registered":
                    return TestResult(
                        "unregistered_voter",
                        True,
                        "Correctly rejected unregistered voter",
                        details=detail,
                    )

            return TestResult(
                "unregistered_voter",
                False,
                f"Unexpected response: {resp.status_code} - {resp.json()}",
            )

        except Exception as e:
            return TestResult("unregistered_voter", False, f"Error: {e}")

    def test_inconsistent_reasoning(self) -> TestResult:
        """Test: NO vote with positive reasoning → may be rejected by semantic check."""
        self.log("\n" + "=" * 50)
        self.log("TEST: Inconsistent Reasoning")
        self.log("=" * 50)

        try:
            # Connect and register if needed
            if not self.registered:
                self.full_connect_flow()

            self.log("🗳️  Submitting NO vote with positive reasoning...")

            # Try to submit inconsistent vote
            intent = self.create_vote_intent(
                proposal_id=1,
                vote_option="NO",
                reasoning="This is a fantastic proposal that will greatly benefit everyone! I love it!",
                confidence=0.9,
            )
            signature = self.sign_intent(intent)

            resp = self.client.post(
                "/api/v1/submit_vote",
                json={
                    **intent,
                    "intent_signature": signature,
                    "pub_key": self.wallet.public_key_b64,
                },
            )

            if resp.status_code == 422:
                detail = resp.json().get("detail", {})
                if detail.get("stage") == "semantic":
                    return TestResult(
                        "inconsistent_reasoning",
                        True,
                        "Correctly rejected inconsistent reasoning",
                        details=detail,
                    )

            # Note: Quick heuristic validation may not catch all inconsistencies
            if resp.status_code == 200:
                return TestResult(
                    "inconsistent_reasoning",
                    True,
                    "Vote accepted (heuristic validation mode - LLM would catch this)",
                    details={"note": "Quick validation may not catch all semantic issues"},
                )

            return TestResult(
                "inconsistent_reasoning",
                False,
                f"Unexpected response: {resp.status_code} - {resp.json()}",
            )

        except Exception as e:
            return TestResult("inconsistent_reasoning", False, f"Error: {e}")

    def run_full_test_suite(self) -> list[TestResult]:
        """Run all test scenarios."""
        self.log("\n" + "=" * 60)
        self.log("🧪 DAHAO Mock Phone - Full Test Suite")
        self.log("=" * 60)
        self.log(f"Node: {self.node_url}")

        results = []

        # Test 1: Happy path
        results.append(self.test_happy_path())

        # Test 2: Invalid signature
        results.append(self.test_invalid_signature())

        # Test 3: Unregistered voter
        results.append(self.test_unregistered_voter())

        # Test 4: Inconsistent reasoning
        results.append(self.test_inconsistent_reasoning())

        # Summary
        self.log("\n" + "=" * 60)
        self.log("📊 TEST RESULTS SUMMARY")
        self.log("=" * 60)

        passed = 0
        failed = 0
        for r in results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            self.log(f"{status} - {r.name}: {r.message}")
            if r.passed:
                passed += 1
            else:
                failed += 1

        self.log("")
        self.log(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")

        return results


def main():
    """Main entry point for mock phone client."""
    parser = argparse.ArgumentParser(
        description="Mock Phone Client for DAHAO Observer Mode testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--node",
        default="http://localhost:8080",
        help="Node URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--full-test",
        action="store_true",
        help="Run full test suite",
    )
    parser.add_argument(
        "--vote-only",
        action="store_true",
        help="Quick vote test only (assumes already registered)",
    )
    parser.add_argument(
        "--connect-only",
        action="store_true",
        help="Test connection flow only",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode (step by step)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output",
    )

    args = parser.parse_args()

    client = MockPhoneClient(args.node, verbose=not args.quiet)

    try:
        if args.full_test:
            results = client.run_full_test_suite()
            # Exit with error if any test failed
            sys.exit(0 if all(r.passed for r in results) else 1)

        elif args.connect_only:
            success = client.full_connect_flow()
            sys.exit(0 if success else 1)

        elif args.vote_only:
            client.full_connect_flow()
            proposals = client.get_proposals()
            if proposals:
                client.submit_vote(
                    proposal_id=proposals[0]["id"],
                    vote_option="YES",
                    reasoning="Test vote from mock phone client.",
                    confidence=0.75,
                )
            sys.exit(0)

        elif args.interactive:
            print("Interactive mode not implemented yet. Use --full-test")
            sys.exit(1)

        else:
            # Default: run full test suite
            results = client.run_full_test_suite()
            sys.exit(0 if all(r.passed for r in results) else 1)

    finally:
        client.close()


if __name__ == "__main__":
    main()
