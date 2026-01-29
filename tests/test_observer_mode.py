"""Integration tests for DAHAO Observer Mode API.

Run with:
    uv run pytest tests/test_observer_mode.py -v

These tests spin up a test FastAPI client and verify all Observer Mode endpoints.
"""

from __future__ import annotations

import base64
import hashlib
import sys
import time

import pytest
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, ".")

from api.server import app_state, create_app
from validator.signature import create_test_keypair, sign_payload


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    with TestClient(app) as client:
        yield client
    # Clear app state after each test
    app_state.sessions.clear()
    app_state.voters.clear()


@pytest.fixture
def test_keypair():
    """Generate a test ECDSA keypair."""
    priv_key, pub_key = create_test_keypair()
    return {
        "private_key": priv_key,
        "public_key": pub_key,
        "public_key_b64": base64.b64encode(pub_key).decode(),
        "address": "cosmos1test" + hashlib.sha256(pub_key).hexdigest()[:32],
    }


@pytest.fixture
def registered_voter(client, test_keypair):
    """Create a registered voter for tests that need one."""
    # Get invite
    resp = client.get("/api/v1/invite")
    invite_code = resp.json()["invite_code"]

    # Connect
    resp = client.post("/api/v1/connect", json={"invite_code": invite_code})
    session_token = resp.json()["session_token"]

    # Register
    resp = client.post(
        "/api/v1/register",
        json={
            "session_token": session_token,
            "voter_address": test_keypair["address"],
            "authz_tx_hash": "MOCK_TX_HASH",
            "pub_key": test_keypair["public_key_b64"],
        },
    )
    assert resp.status_code == 200

    return test_keypair


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check(self, client):
        """Test that health endpoint returns ok status."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["mode"] == "observer"


class TestInviteFlow:
    """Tests for GET /invite endpoint."""

    def test_get_invite(self, client):
        """Test that invite endpoint returns valid invite."""
        resp = client.get("/api/v1/invite")
        assert resp.status_code == 200

        data = resp.json()
        assert "invite_code" in data
        assert len(data["invite_code"]) == 6
        assert "invite_link" in data
        assert "dahao://connect" in data["invite_link"]
        assert "expires_at" in data
        assert "node_address" in data
        assert "chain_id" in data

    def test_invite_codes_are_unique(self, client):
        """Test that each invite generates a unique code."""
        codes = set()
        for _ in range(5):
            resp = client.get("/api/v1/invite")
            codes.add(resp.json()["invite_code"])

        assert len(codes) == 5, "Invite codes should be unique"


class TestConnectFlow:
    """Tests for POST /connect endpoint."""

    def test_connect_with_valid_invite(self, client):
        """Test successful connection with valid invite."""
        # Get invite
        invite_resp = client.get("/api/v1/invite")
        invite_code = invite_resp.json()["invite_code"]

        # Connect
        resp = client.post("/api/v1/connect", json={"invite_code": invite_code})
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "connected"
        assert "session_token" in data
        assert "node_address" in data
        assert "chain_id" in data

    def test_connect_with_invalid_invite(self, client):
        """Test rejection of invalid invite code."""
        resp = client.post("/api/v1/connect", json={"invite_code": "INVALID"})
        assert resp.status_code == 400

        data = resp.json()
        assert data["detail"]["error"] == "invalid_invite"

    def test_connect_case_insensitive(self, client):
        """Test that invite codes are case-insensitive."""
        invite_resp = client.get("/api/v1/invite")
        invite_code = invite_resp.json()["invite_code"]

        # Try lowercase
        resp = client.post("/api/v1/connect", json={"invite_code": invite_code.lower()})
        assert resp.status_code == 200


class TestRegisterFlow:
    """Tests for POST /register endpoint."""

    def test_register_success(self, client, test_keypair):
        """Test successful voter registration."""
        # Get invite and connect
        invite_resp = client.get("/api/v1/invite")
        invite_code = invite_resp.json()["invite_code"]

        connect_resp = client.post("/api/v1/connect", json={"invite_code": invite_code})
        session_token = connect_resp.json()["session_token"]

        # Register
        resp = client.post(
            "/api/v1/register",
            json={
                "session_token": session_token,
                "voter_address": test_keypair["address"],
                "authz_tx_hash": "TX_HASH_123",
                "pub_key": test_keypair["public_key_b64"],
            },
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "registered"
        assert data["voter_address"] == test_keypair["address"]
        assert "grant_expires_at" in data

    def test_register_invalid_session(self, client, test_keypair):
        """Test rejection of invalid session token."""
        resp = client.post(
            "/api/v1/register",
            json={
                "session_token": "invalid_token",
                "voter_address": test_keypair["address"],
                "authz_tx_hash": "TX_HASH_123",
                "pub_key": test_keypair["public_key_b64"],
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_session"

    def test_register_double_registration(self, client, test_keypair):
        """Test rejection of double registration with same session."""
        # Get invite and connect
        invite_resp = client.get("/api/v1/invite")
        connect_resp = client.post(
            "/api/v1/connect", json={"invite_code": invite_resp.json()["invite_code"]}
        )
        session_token = connect_resp.json()["session_token"]

        # First registration
        reg_data = {
            "session_token": session_token,
            "voter_address": test_keypair["address"],
            "authz_tx_hash": "TX_HASH_123",
            "pub_key": test_keypair["public_key_b64"],
        }
        resp = client.post("/api/v1/register", json=reg_data)
        assert resp.status_code == 200

        # Second registration should fail (session consumed)
        resp = client.post("/api/v1/register", json=reg_data)
        assert resp.status_code == 400  # Session no longer exists


class TestProposalsEndpoint:
    """Tests for GET /proposals endpoint."""

    def test_get_proposals(self, client):
        """Test that proposals endpoint returns list."""
        resp = client.get("/api/v1/proposals")
        assert resp.status_code == 200

        data = resp.json()
        assert "proposals" in data
        assert "count" in data
        assert "chain_connected" in data
        assert isinstance(data["proposals"], list)

    def test_proposal_structure(self, client):
        """Test that proposals have expected fields."""
        resp = client.get("/api/v1/proposals")
        data = resp.json()

        if data["proposals"]:
            proposal = data["proposals"][0]
            assert "id" in proposal
            assert "title" in proposal
            assert "description" in proposal
            assert "proposal_type" in proposal


class TestSubmitVoteEndpoint:
    """Tests for POST /submit_vote endpoint."""

    def test_submit_vote_valid(self, client, registered_voter):
        """Test successful vote submission with valid signature."""
        # Create vote intent
        intent = {
            "proposal_id": 1,
            "voter_address": registered_voter["address"],
            "vote_option": "YES",
            "public_reasoning": "I support this proposal because it benefits the network.",
            "confidence_score": 0.85,
            "timestamp": int(time.time()),
            "nonce": "test_nonce_123",
        }

        # Sign intent
        signature = sign_payload(intent, registered_voter["private_key"])

        # Submit vote
        resp = client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": registered_voter["public_key_b64"],
            },
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "broadcasted"
        assert "tx_hash" in data
        assert "audit_log" in data

    def test_submit_vote_invalid_signature(self, client, registered_voter):
        """Test rejection of vote with invalid/tampered signature."""
        # Create and sign intent
        intent = {
            "proposal_id": 1,
            "voter_address": registered_voter["address"],
            "vote_option": "YES",
            "public_reasoning": "Original reasoning",
            "confidence_score": 0.85,
            "timestamp": int(time.time()),
            "nonce": "test_nonce_456",
        }
        signature = sign_payload(intent, registered_voter["private_key"])

        # Tamper with payload after signing
        intent["vote_option"] = "NO"

        # Submit tampered vote
        resp = client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": registered_voter["public_key_b64"],
            },
        )
        assert resp.status_code == 400

        data = resp.json()
        assert data["detail"]["stage"] == "signature"

    def test_submit_vote_unregistered(self, client, test_keypair):
        """Test rejection of vote from unregistered voter."""
        intent = {
            "proposal_id": 1,
            "voter_address": test_keypair["address"],
            "vote_option": "YES",
            "public_reasoning": "Test reasoning",
            "confidence_score": 0.85,
            "timestamp": int(time.time()),
            "nonce": "test_nonce_789",
        }
        signature = sign_payload(intent, test_keypair["private_key"])

        resp = client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": test_keypair["public_key_b64"],
            },
        )
        assert resp.status_code == 403

        data = resp.json()
        assert data["detail"]["error"] == "voter_not_registered"
        assert data["detail"]["stage"] == "registration"

    def test_submit_vote_malformed_signature(self, client, registered_voter):
        """Test rejection of malformed signature."""
        intent = {
            "proposal_id": 1,
            "voter_address": registered_voter["address"],
            "vote_option": "YES",
            "public_reasoning": "Test reasoning",
            "confidence_score": 0.85,
            "timestamp": int(time.time()),
            "nonce": "test_nonce_abc",
        }

        resp = client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": "not_valid_base64!!!",
                "pub_key": registered_voter["public_key_b64"],
            },
        )
        assert resp.status_code == 400

        data = resp.json()
        assert data["detail"]["stage"] == "signature"

    def test_submit_vote_different_voter_address(self, client, registered_voter):
        """Test rejection when signature doesn't match voter address."""
        # Create intent for different address
        intent = {
            "proposal_id": 1,
            "voter_address": "cosmos1different_address",  # Not registered
            "vote_option": "YES",
            "public_reasoning": "Test reasoning",
            "confidence_score": 0.85,
            "timestamp": int(time.time()),
            "nonce": "test_nonce_def",
        }
        signature = sign_payload(intent, registered_voter["private_key"])

        resp = client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": registered_voter["public_key_b64"],
            },
        )
        # Should fail at registration stage (voter not registered)
        assert resp.status_code == 403


class TestStatusEndpoint:
    """Tests for GET /status endpoint."""

    def test_status(self, client):
        """Test that status endpoint returns expected fields."""
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200

        data = resp.json()
        assert data["mode"] == "observer"
        assert "chain_connected" in data
        assert "active_sessions" in data
        assert "registered_voters" in data


class TestEndToEndFlow:
    """End-to-end integration tests."""

    def test_full_voting_flow(self, client, test_keypair):
        """Test complete flow: invite → connect → register → vote."""
        # Step 1: Get invite
        invite_resp = client.get("/api/v1/invite")
        assert invite_resp.status_code == 200
        invite_code = invite_resp.json()["invite_code"]

        # Step 2: Connect
        connect_resp = client.post("/api/v1/connect", json={"invite_code": invite_code})
        assert connect_resp.status_code == 200
        session_token = connect_resp.json()["session_token"]

        # Step 3: Register
        register_resp = client.post(
            "/api/v1/register",
            json={
                "session_token": session_token,
                "voter_address": test_keypair["address"],
                "authz_tx_hash": "MOCK_TX_HASH",
                "pub_key": test_keypair["public_key_b64"],
            },
        )
        assert register_resp.status_code == 200

        # Step 4: Get proposals
        proposals_resp = client.get("/api/v1/proposals")
        assert proposals_resp.status_code == 200
        proposals = proposals_resp.json()["proposals"]
        assert len(proposals) > 0

        # Step 5: Create and sign vote
        intent = {
            "proposal_id": proposals[0]["id"],
            "voter_address": test_keypair["address"],
            "vote_option": "YES",
            "public_reasoning": "This proposal improves the network.",
            "confidence_score": 0.9,
            "timestamp": int(time.time()),
            "nonce": "e2e_test_nonce",
        }
        signature = sign_payload(intent, test_keypair["private_key"])

        # Step 6: Submit vote
        vote_resp = client.post(
            "/api/v1/submit_vote",
            json={
                **intent,
                "intent_signature": signature,
                "pub_key": test_keypair["public_key_b64"],
            },
        )
        assert vote_resp.status_code == 200
        assert "tx_hash" in vote_resp.json()

    def test_multiple_voters_same_invite(self, client):
        """Test that multiple voters can use the same invite code."""
        # Get invite
        invite_resp = client.get("/api/v1/invite")
        invite_code = invite_resp.json()["invite_code"]

        # First voter
        keypair1 = create_test_keypair()
        connect1 = client.post("/api/v1/connect", json={"invite_code": invite_code})
        assert connect1.status_code == 200
        token1 = connect1.json()["session_token"]

        reg1 = client.post(
            "/api/v1/register",
            json={
                "session_token": token1,
                "voter_address": "cosmos1voter1",
                "authz_tx_hash": "TX1",
                "pub_key": base64.b64encode(keypair1[1]).decode(),
            },
        )
        assert reg1.status_code == 200

        # Second voter (same invite code)
        keypair2 = create_test_keypair()
        connect2 = client.post("/api/v1/connect", json={"invite_code": invite_code})
        assert connect2.status_code == 200
        token2 = connect2.json()["session_token"]

        reg2 = client.post(
            "/api/v1/register",
            json={
                "session_token": token2,
                "voter_address": "cosmos1voter2",
                "authz_tx_hash": "TX2",
                "pub_key": base64.b64encode(keypair2[1]).decode(),
            },
        )
        assert reg2.status_code == 200

        # Verify both voters are registered
        assert "cosmos1voter1" in app_state.voters
        assert "cosmos1voter2" in app_state.voters
