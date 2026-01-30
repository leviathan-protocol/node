"""POST /submit_vote endpoint - Submit signed voting intents.

This is the core of Gasless Voting. The endpoint:
1. Verifies the intent signature
2. Checks authorization (authz grant for Cosmos, delegation for EVM)
3. Validates reasoning consistency (semantic firewall)
4. If all pass: executes vote on behalf of user
5. Returns tx_hash or rejection reason

Supports both:
- Cosmos chains: Uses Authz MsgExec for delegated voting
- EVM chains: Uses EIP-2771 meta-transactions via Forwarder
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.server import app_state
from chain.adapter import ChainType
from models.vote import VoteChoice

logger = logging.getLogger(__name__)

router = APIRouter()


class VoteSubmitRequest(BaseModel):
    """Request model for POST /submit_vote.

    For Cosmos chains:
        - intent_signature: Base64-encoded ECDSA signature of payload
        - pub_key: Base64-encoded public key

    For EVM chains:
        - eip712_signature: Hex-encoded EIP-712 signature (0x...)
        - voter_address: Ethereum address (0x...)
    """

    proposal_id: int = Field(..., description="ID of the proposal to vote on")
    voter_address: str = Field(..., description="User's address (cosmos1... or 0x...)")
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

    # Cosmos-specific fields
    intent_signature: str | None = Field(
        None, description="Base64-encoded ECDSA signature (Cosmos)"
    )
    pub_key: str | None = Field(None, description="Base64-encoded public key (Cosmos)")

    # EVM-specific fields
    eip712_signature: str | None = Field(
        None, description="Hex-encoded EIP-712 signature (EVM)"
    )
    reasoning_hash: str | None = Field(
        None, description="Bytes32 hex hash of reasoning for on-chain storage (EVM)"
    )


class VoteSubmitResponse(BaseModel):
    """Response model for POST /submit_vote - success."""

    status: str = "broadcasted"
    tx_hash: str = Field(..., description="Transaction hash on chain")
    audit_log: str = Field(..., description="Validation summary")
    chain_type: str = Field(..., description="Chain type used (cosmos or evm)")


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
    1. **Signature verification**: Verify signature on intent
    2. **Authorization check**: Verify user has granted authorization to node
    3. **Semantic validation**: Verify reasoning is consistent with vote
    4. **Execute**: Submit vote on behalf of user

    Args:
        request: Voting intent with signature.

    Returns:
        VoteSubmitResponse with tx_hash if successful.

    Raises:
        HTTPException 400: Signature verification failed
        HTTPException 403: Authorization not found
        HTTPException 422: Semantic validation failed
        HTTPException 500: Vote execution failed
    """
    # Determine chain type from app state
    chain_adapter = getattr(app_state, "chain_adapter", None)
    chain_type = chain_adapter.chain_type if chain_adapter else ChainType.COSMOS

    logger.info(
        f"Vote submission ({chain_type.value}): proposal={request.proposal_id}, "
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

    # Route to chain-specific handler
    if chain_type == ChainType.EVM:
        return await _handle_evm_vote(request, chain_adapter)
    else:
        return await _handle_cosmos_vote(request)


async def _handle_cosmos_vote(request: VoteSubmitRequest) -> VoteSubmitResponse:
    """Handle vote submission for Cosmos chains using Authz."""
    from chain.authz import AuthzVoteError, vote_on_behalf_mock
    from validator import (
        SignatureVerificationError,
        check_authz_grant_mock,
        validate_reasoning_quick,
        verify_intent_signature,
    )

    # Validate Cosmos-specific fields
    if not request.intent_signature or not request.pub_key:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": "missing_cosmos_fields",
                "detail": "Cosmos votes require intent_signature and pub_key",
                "stage": "validation",
            },
        )

    # Build payload for signature verification
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
    logger.debug("Stage 1: Verifying Cosmos signature")
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
    node_address = getattr(app_state, "node_address", "cosmos1node...")

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
                "detail": authz_result.error_message or "Authorization grant not found",
                "stage": "authz",
            },
        )

    logger.debug(f"Stage 2: Authz valid (expires: {authz_result.expires_at})")

    # Stage 3: Semantic validation
    logger.debug("Stage 3: Validating reasoning consistency")
    semantic_result = validate_reasoning_quick(
        proposal_title=f"Proposal #{request.proposal_id}",
        proposal_description="Proposal description not available",
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
                "detail": "; ".join(semantic_result.issues) or "Reasoning inconsistent",
                "stage": "semantic",
            },
        )

    logger.debug("Stage 3: Reasoning consistent")

    # Stage 4: Execute vote
    logger.debug("Stage 4: Executing vote on chain")
    try:
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

    logger.info(f"Cosmos vote executed: tx={tx_hash}")

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
        chain_type="cosmos",
    )


async def _handle_evm_vote(
    request: VoteSubmitRequest,
    chain_adapter,
) -> VoteSubmitResponse:
    """Handle vote submission for EVM chains using meta-transactions."""
    from validator import validate_reasoning_quick

    # Validate EVM-specific fields
    if not request.eip712_signature:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": "missing_evm_fields",
                "detail": "EVM votes require eip712_signature",
                "stage": "validation",
            },
        )

    # Parse signature
    try:
        sig_hex = request.eip712_signature
        if sig_hex.startswith("0x"):
            sig_hex = sig_hex[2:]
        signature = bytes.fromhex(sig_hex)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "error": "invalid_signature_format",
                "detail": "EIP-712 signature must be valid hex",
                "stage": "signature",
            },
        )

    # Stage 1: Check voting power (EVM equivalent of authz)
    logger.debug("Stage 1: Checking voting power")
    voting_power = chain_adapter.get_voting_power(request.voter_address)

    if voting_power == 0:
        # Check if they have tokens but haven't delegated
        token_balance = chain_adapter.get_balance(
            request.voter_address,
            chain_adapter.config.token_address,
        )

        if token_balance > 0:
            logger.warning(f"Voter {request.voter_address} has tokens but no voting power (not delegated)")
            raise HTTPException(
                status_code=403,
                detail={
                    "status": "rejected",
                    "error": "not_delegated",
                    "detail": "You have tokens but no voting power. Please delegate to yourself or another address.",
                    "stage": "authorization",
                },
            )
        else:
            logger.warning(f"Voter {request.voter_address} has no voting power")
            raise HTTPException(
                status_code=403,
                detail={
                    "status": "rejected",
                    "error": "no_voting_power",
                    "detail": "No voting power. Acquire DAHAO tokens and delegate to vote.",
                    "stage": "authorization",
                },
            )

    logger.debug(f"Stage 1: Voting power = {voting_power}")

    # Stage 2: Semantic validation
    logger.debug("Stage 2: Validating reasoning consistency")
    semantic_result = validate_reasoning_quick(
        proposal_title=f"Proposal #{request.proposal_id}",
        proposal_description="Proposal description not available",
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
                "detail": "; ".join(semantic_result.issues) or "Reasoning inconsistent",
                "stage": "semantic",
            },
        )

    logger.debug("Stage 2: Reasoning consistent")

    # Stage 3: Execute vote via meta-transaction
    logger.debug("Stage 3: Executing EVM vote via meta-transaction")

    # Parse vote option
    vote_choice = VoteChoice[request.vote_option.upper()]

    # Parse reasoning hash if provided
    reasoning_hash = None
    if request.reasoning_hash:
        try:
            rh = request.reasoning_hash
            if rh.startswith("0x"):
                rh = rh[2:]
            reasoning_hash = bytes.fromhex(rh)
        except ValueError:
            logger.warning("Invalid reasoning_hash format, ignoring")

    # Execute via adapter
    result = chain_adapter.submit_vote_on_behalf(
        voter_address=request.voter_address,
        proposal_id=request.proposal_id,
        vote_option=vote_choice,
        signature=signature,
        reasoning_hash=reasoning_hash,
    )

    if not result.success:
        logger.error(f"EVM vote execution failed: {result.error}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "rejected",
                "error": "execution_failed",
                "detail": result.error or "Meta-transaction execution failed",
                "stage": "execution",
            },
        )

    logger.info(f"EVM vote executed: tx={result.tx_hash}")

    audit_log = (
        f"Voting Power: {voting_power} | "
        f"Semantic: {semantic_result.recommendation} | "
        f"Gas Used: {result.gas_used or 'N/A'} | "
        f"Executed at: {datetime.now(timezone.utc).isoformat()}"
    )

    return VoteSubmitResponse(
        status="broadcasted",
        tx_hash=result.tx_hash,
        audit_log=audit_log,
        chain_type="evm",
    )
