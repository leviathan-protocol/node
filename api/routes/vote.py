"""POST /submit_vote endpoint - Submit signed voting intents.

This is the core of Gasless Voting. The endpoint:
1. Verifies the intent signature
2. Checks authz grant exists
3. Validates reasoning consistency (semantic firewall)
4. If all pass: executes vote via MsgExec
5. Returns tx_hash or rejection reason
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.server import app_state
from chain.authz import AuthzVoteError, vote_on_behalf_mock
from validator import (
    SignatureVerificationError,
    check_authz_grant_mock,
    validate_reasoning_quick,
    verify_intent_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class VoteSubmitRequest(BaseModel):
    """Request model for POST /submit_vote."""

    proposal_id: int = Field(..., description="ID of the proposal to vote on")
    voter_address: str = Field(..., description="User's Cosmos address")
    vote_option: str = Field(
        ...,
        description="Vote choice: YES, NO, ABSTAIN, or NO_WITH_VETO",
    )
    public_reasoning: str = Field(
        ...,
        description="User's explanation for their vote (checked for consistency)",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0",
    )
    timestamp: int = Field(..., description="Unix timestamp when intent was created")
    nonce: str = Field(..., description="Random nonce for replay protection")
    intent_signature: str = Field(..., description="Base64-encoded ECDSA signature")
    pub_key: str = Field(..., description="Base64-encoded public key")


class VoteSubmitResponse(BaseModel):
    """Response model for POST /submit_vote - success."""

    status: str = "broadcasted"
    tx_hash: str = Field(..., description="Transaction hash on chain")
    audit_log: str = Field(..., description="Validation summary")


class VoteRejectResponse(BaseModel):
    """Response model for POST /submit_vote - rejection."""

    status: str = "rejected"
    error: str = Field(..., description="Error code")
    detail: str = Field(..., description="Human-readable error message")
    stage: str = Field(..., description="Which validation stage failed")


@router.post("/submit_vote")
async def submit_vote(request: VoteSubmitRequest) -> VoteSubmitResponse:
    """Submit a signed voting intent for execution.

    Validation pipeline:
    1. **Signature verification**: Verify ECDSA secp256k1 signature on intent
    2. **Authz check**: Verify user has granted MsgVote authorization to node
    3. **Semantic validation**: Verify reasoning is consistent with vote
    4. **Execute**: Wrap in MsgExec and broadcast via node wallet

    Args:
        request: Voting intent with signature.

    Returns:
        VoteSubmitResponse with tx_hash if successful.

    Raises:
        HTTPException 400: Signature verification failed
        HTTPException 403: Authz grant not found
        HTTPException 422: Semantic validation failed
        HTTPException 500: Vote execution failed
    """
    logger.info(
        f"Vote submission: proposal={request.proposal_id}, "
        f"voter={request.voter_address}, vote={request.vote_option}"
    )

    # Check if voter is registered
    voter_info = app_state.voters.get(request.voter_address)
    if voter_info is None:
        logger.warning(f"Unregistered voter: {request.voter_address}")
        raise HTTPException(
            status_code=403,
            detail={
                "status": "rejected",
                "error": "voter_not_registered",
                "detail": "Voter is not registered with this node. Please complete pairing first.",
                "stage": "registration",
            },
        )

    # Build payload for signature verification (must match what mobile signed)
    payload = {
        "proposal_id": request.proposal_id,
        "voter_address": request.voter_address,
        "vote_option": request.vote_option,
        "public_reasoning": request.public_reasoning,
        "confidence_score": request.confidence_score,
        "timestamp": request.timestamp,
        "nonce": request.nonce,
    }

    # Stage 1: Signature verification
    logger.debug("Stage 1: Verifying signature")
    try:
        sig_valid = verify_intent_signature(
            payload=payload,
            signature=request.intent_signature,
            pub_key=request.pub_key,
        )

        if not sig_valid:
            logger.warning(f"Invalid signature for voter {request.voter_address}")
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "rejected",
                    "error": "invalid_signature",
                    "detail": "Intent signature verification failed",
                    "stage": "signature",
                },
            )
    except SignatureVerificationError as e:
        logger.warning(f"Signature error: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": e.reason,
                "detail": str(e),
                "stage": "signature",
            },
        )

    logger.debug("Stage 1: Signature valid")

    # Stage 2: Authz grant check
    logger.debug("Stage 2: Checking authz grant")

    # Get node address (would come from config in production)
    node_address = getattr(app_state, "node_address", "cosmos1node...")

    # Check authz grant (using mock for now)
    authz_result = check_authz_grant_mock(
        granter=request.voter_address,
        grantee=node_address,
    )

    if not authz_result.is_valid:
        logger.warning(
            f"Authz check failed for {request.voter_address}: {authz_result.status.value}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "status": "rejected",
                "error": f"authz_{authz_result.status.value}",
                "detail": authz_result.error_message or "Authorization grant not found or invalid",
                "stage": "authz",
            },
        )

    logger.debug(f"Stage 2: Authz valid (expires: {authz_result.expires_at})")

    # Stage 3: Semantic validation
    logger.debug("Stage 3: Validating reasoning consistency")

    # Get proposal info for semantic check
    # TODO: Fetch actual proposal from chain
    proposal_title = f"Proposal #{request.proposal_id}"
    proposal_description = "Proposal description not available"

    # Use quick heuristic validation for now (LLM validation can be added)
    semantic_result = validate_reasoning_quick(
        proposal_title=proposal_title,
        proposal_description=proposal_description,
        vote_option=request.vote_option,
        public_reasoning=request.public_reasoning,
    )

    if not semantic_result.should_accept:
        logger.warning(
            f"Semantic validation failed for {request.voter_address}: {semantic_result.issues}"
        )
        raise HTTPException(
            status_code=422,
            detail={
                "status": "rejected",
                "error": "semantic_inconsistency",
                "detail": "; ".join(semantic_result.issues) or "Reasoning is inconsistent with vote",
                "stage": "semantic",
            },
        )

    logger.debug("Stage 3: Reasoning consistent")

    # Stage 4: Execute vote on behalf
    logger.debug("Stage 4: Executing vote on chain")

    try:
        # Use mock for now (real implementation needs chain client)
        tx_hash = vote_on_behalf_mock(
            voter_address=request.voter_address,
            proposal_id=request.proposal_id,
            vote_option=request.vote_option,
            should_succeed=True,
        )
    except AuthzVoteError as e:
        logger.error(f"Vote execution failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "rejected",
                "error": e.reason,
                "detail": str(e),
                "stage": "execution",
            },
        )

    logger.info(f"Vote executed successfully: tx={tx_hash}")

    # Build audit log
    audit_log = (
        f"Signature: valid | "
        f"Authz: {authz_result.status.value} | "
        f"Semantic: {semantic_result.recommendation} | "
        f"Executed at: {datetime.now(timezone.utc).isoformat()}"
    )

    return VoteSubmitResponse(
        status="broadcasted",
        tx_hash=tx_hash,
        audit_log=audit_log,
    )
