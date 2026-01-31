"""Invite-based pairing endpoints for mobile connection.

Flow:
1. Operator calls GET /invite to generate shareable invite link
2. Operator shares link via Twitter/Telegram/website
3. User clicks link → Flutter app opens with deep link
4. App calls POST /connect with invite code to get node info
5. App prompts user to grant Authz on chain
6. App calls POST /register with authz_tx_hash to complete pairing
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.server import app_state

logger = logging.getLogger(__name__)

router = APIRouter()

# Default invite expiry (24 hours - longer than QR since it's shared async)
INVITE_EXPIRY_HOURS = 24

# Invite code length (6 alphanumeric characters, easy to type)
INVITE_CODE_LENGTH = 6


class InviteResponse(BaseModel):
    """Response model for GET /invite."""

    invite_code: str = Field(..., description="Short code for the invite")
    invite_link: str = Field(..., description="Full deep link for mobile app")
    expires_at: str = Field(..., description="ISO 8601 expiration time")
    node_address: str = Field(..., description="Node's Cosmos address")
    chain_id: str = Field(..., description="Chain identifier")


class ConnectRequest(BaseModel):
    """Request model for POST /connect."""

    invite_code: str = Field(..., description="Invite code from the link")


class ConnectResponse(BaseModel):
    """Response model for POST /connect - node info for mobile app."""

    status: str = "connected"
    node_address: str = Field(..., description="Node's Cosmos address for Authz grant")
    chain_id: str = Field(..., description="Chain to submit Authz grant")
    node_url: str = Field(..., description="API URL for subsequent requests")
    session_token: str = Field(..., description="Token to use for registration")


class RegisterRequest(BaseModel):
    """Request model for POST /register."""

    session_token: str = Field(..., description="Session token from /connect response")
    voter_address: str = Field(..., description="User's Cosmos address (cosmos1...)")
    authz_tx_hash: str = Field(..., description="Transaction hash of MsgGrant")
    pub_key: str = Field(..., description="Base64-encoded public key")


class RegisterResponse(BaseModel):
    """Response model for POST /register."""

    status: str = "registered"
    voter_address: str
    grant_expires_at: str | None = None


def _generate_invite_code(length: int = INVITE_CODE_LENGTH) -> str:
    """Generate a random alphanumeric invite code.

    Uses uppercase letters and digits, excluding ambiguous characters (0, O, I, L).

    Args:
        length: Number of characters (default 6).

    Returns:
        Random alphanumeric string like "A3B7K9".
    """
    # Exclude ambiguous characters: 0, O, I, L, 1
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@router.get("/invite", response_model=InviteResponse)
async def generate_invite() -> InviteResponse:
    """Generate an invite link for users to connect.

    Operators call this to get a shareable link they can post on
    Twitter, Telegram, their website, etc.

    The invite link uses a deep link format that Flutter apps can handle:
    dahao://connect?node=https://node.example.com&code=ABC123

    Returns:
        InviteResponse with invite code, full link, and node info.
    """
    logger.info("Invite generation requested")

    # Generate invite code
    invite_code = _generate_invite_code()

    # Calculate expiration (24 hours for async sharing)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS)
    expires_at_iso = expires_at.isoformat().replace("+00:00", "Z")

    # Get node info from config or use defaults
    # TODO: Get from actual config when integrated
    node_address = getattr(app_state, "node_address", "cosmos1node...")
    chain_id = getattr(app_state, "chain_id", "dahao")
    node_url = getattr(app_state, "node_url", "http://localhost:8080")

    # Build deep link URL
    # Format: dahao://connect?node=<url>&code=<code>
    invite_link = f"dahao://connect?node={node_url}&code={invite_code}"

    # Store invite in memory
    app_state.sessions[invite_code] = {
        "type": "invite",
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
        "used": False,
        "connected": False,  # True after /connect called
        "session_token": None,  # Set when /connect is called
    }

    logger.info(
        f"Created invite {invite_code} (expires: {expires_at_iso})"
    )

    return InviteResponse(
        invite_code=invite_code,
        invite_link=invite_link,
        expires_at=expires_at_iso,
        node_address=node_address,
        chain_id=chain_id,
    )


@router.post("/connect", response_model=ConnectResponse)
async def connect_with_invite(request: ConnectRequest) -> ConnectResponse:
    """Validate invite code and return node info for Authz grant.

    Called by Flutter app when user clicks an invite link.
    Returns the node info needed to create the Authz grant.

    Args:
        request: Connect request with invite code.

    Returns:
        ConnectResponse with node info and session token for registration.

    Raises:
        HTTPException 400: Invalid invite code
        HTTPException 410: Invite expired
    """
    invite_code = request.invite_code.upper()  # Normalize to uppercase
    logger.info(f"Connect attempt with invite code: {invite_code}")

    # Validate invite exists
    invite = app_state.sessions.get(invite_code)
    if invite is None or invite.get("type") != "invite":
        logger.warning(f"Invalid invite code: {invite_code}")
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": "invalid_invite",
                "detail": "Invite code not found or invalid",
            },
        )

    # Check if invite is expired
    if datetime.now(timezone.utc) > invite["expires_at"]:
        logger.warning(f"Expired invite: {invite_code}")
        # Clean up expired invite
        del app_state.sessions[invite_code]
        raise HTTPException(
            status_code=410,
            detail={
                "status": "rejected",
                "error": "invite_expired",
                "detail": "This invite has expired. Please request a new one.",
            },
        )

    # Generate session token for this connection
    # Multiple users can connect with same invite code
    session_token = secrets.token_urlsafe(32)

    # Store connection session (separate from invite)
    app_state.sessions[session_token] = {
        "type": "connection",
        "invite_code": invite_code,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),  # 1 hour to complete registration
        "registered": False,
    }

    # Mark invite as connected (for tracking, but don't invalidate)
    invite["connected"] = True
    invite["last_connect_at"] = datetime.now(timezone.utc)

    # Get node info
    node_address = getattr(app_state, "node_address", "cosmos1node...")
    chain_id = getattr(app_state, "chain_id", "dahao")
    node_url = getattr(app_state, "node_url", "http://localhost:8080")

    logger.info(f"User connected with invite {invite_code}, session: {session_token[:16]}...")

    return ConnectResponse(
        status="connected",
        node_address=node_address,
        chain_id=chain_id,
        node_url=node_url,
        session_token=session_token,
    )


@router.post("/register", response_model=RegisterResponse)
async def register_voter(request: RegisterRequest) -> RegisterResponse:
    """Complete pairing after user grants Authz on chain.

    Called by Flutter app after the user has:
    1. Called /connect to get node info
    2. Created MsgGrant transaction on chain
    3. Received tx confirmation

    Validates:
    1. Session token is valid (from /connect)
    2. Session is not expired
    3. Session hasn't been registered already
    4. (TODO) Authz grant exists on chain

    Args:
        request: Registration request with session token and authz info.

    Returns:
        RegisterResponse confirming registration.

    Raises:
        HTTPException 400: Invalid session token
        HTTPException 410: Session expired
        HTTPException 409: Already registered
    """
    logger.info(f"Registration attempt for voter {request.voter_address}")

    # Validate session token exists and is a connection session
    session = app_state.sessions.get(request.session_token)
    if session is None or session.get("type") != "connection":
        logger.warning(f"Invalid session token: {request.session_token[:16]}...")
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": "invalid_session",
                "detail": "Session token not found or invalid. Please reconnect.",
            },
        )

    # Check if session is expired
    if datetime.now(timezone.utc) > session["expires_at"]:
        logger.warning(f"Expired session: {request.session_token[:16]}...")
        del app_state.sessions[request.session_token]
        raise HTTPException(
            status_code=410,
            detail={
                "status": "rejected",
                "error": "session_expired",
                "detail": "Connection session expired. Please reconnect with the invite.",
            },
        )

    # Check if already registered with this session
    if session.get("registered"):
        logger.warning(f"Session already registered: {request.session_token[:16]}...")
        raise HTTPException(
            status_code=409,
            detail={
                "status": "rejected",
                "error": "already_registered",
                "detail": "This session has already been used for registration.",
            },
        )

    # TODO: Verify authz grant on chain
    # Query /cosmos.authz.v1beta1.Query/Grants to confirm MsgVote authorization
    logger.info(f"(Mock) Verifying authz tx: {request.authz_tx_hash}")

    # Mark session as registered
    session["registered"] = True
    session["voter_address"] = request.voter_address

    # Calculate grant expiration (default 90 days)
    # TODO: Get actual expiration from chain query
    grant_expires = datetime.now(timezone.utc) + timedelta(days=90)
    grant_expires_iso = grant_expires.isoformat().replace("+00:00", "Z")

    # Store voter information
    app_state.voters[request.voter_address] = {
        "pub_key": request.pub_key,
        "authz_tx_hash": request.authz_tx_hash,
        "registered_at": datetime.now(timezone.utc),
        "grant_expires_at": grant_expires,
        "session_token": request.session_token,
        "invite_code": session.get("invite_code"),
    }

    logger.info(
        f"Registered voter {request.voter_address} "
        f"(grant expires: {grant_expires_iso})"
    )

    # Clean up connection session after successful registration
    del app_state.sessions[request.session_token]

    return RegisterResponse(
        status="registered",
        voter_address=request.voter_address,
        grant_expires_at=grant_expires_iso,
    )


# =============================================================================
# EVM Registration (Simplified for testing)
# =============================================================================


class EVMRegisterRequest(BaseModel):
    """Request model for POST /register_evm - simplified EVM registration."""

    voter_address: str = Field(..., description="User's EVM address (0x...)")


class EVMRegisterResponse(BaseModel):
    """Response model for POST /register_evm."""

    status: str = "registered"
    voter_address: str
    chain_type: str = "evm"


@router.post("/register_evm", response_model=EVMRegisterResponse)
async def register_evm_voter(request: EVMRegisterRequest) -> EVMRegisterResponse:
    """Register an EVM address for testing.

    Simplified registration for EVM chains that doesn't require the full
    invite/connect/authz flow. Useful for testing the semantic firewall.

    For production, EVM voters would register via token delegation which
    can be verified on-chain.

    Args:
        request: Registration request with EVM address.

    Returns:
        EVMRegisterResponse confirming registration.
    """
    voter_address = request.voter_address

    # Validate address format (basic check)
    if not voter_address.startswith("0x") or len(voter_address) != 42:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": "invalid_address",
                "detail": "Invalid EVM address format. Must be 0x followed by 40 hex characters.",
            },
        )

    logger.info(f"Registering EVM voter: {voter_address}")

    # Store voter information (simplified for EVM)
    app_state.voters[voter_address] = {
        "chain_type": "evm",
        "registered_at": datetime.now(timezone.utc),
        "grant_expires_at": datetime.now(timezone.utc) + timedelta(days=365),
    }

    logger.info(f"Registered EVM voter {voter_address}")

    return EVMRegisterResponse(
        status="registered",
        voter_address=voter_address,
        chain_type="evm",
    )
