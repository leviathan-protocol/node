"""GET /status endpoint - Node health and statistics."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from api.server import app_state

logger = logging.getLogger(__name__)

router = APIRouter()


class StatusResponse(BaseModel):
    """Response model for GET /status."""

    mode: str = "observer"
    chain_connected: bool = False
    llm_connected: bool = False
    registered_voters: int = 0
    active_sessions: int = 0
    pending_proposals: int = 0
    node_balance: str | None = None


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get node health and statistics.

    Returns current operational status including:
    - Mode (always 'observer' for this API)
    - Connection status for chain and LLM
    - Number of registered voters
    - Number of active pairing sessions
    - Number of pending proposals (if chain connected)
    - Node wallet balance (if chain connected)
    """
    logger.debug("Status check requested")

    # Check chain connection
    chain_connected = app_state.chain_client is not None

    # Check LLM connection
    llm_connected = app_state.llm is not None

    # Count registered voters and active sessions
    registered_voters = len(app_state.voters)
    active_sessions = len(app_state.sessions)

    # TODO: Query pending proposals from chain when connected
    pending_proposals = 0

    # TODO: Query node balance when connected
    node_balance = None

    return StatusResponse(
        mode="observer",
        chain_connected=chain_connected,
        llm_connected=llm_connected,
        registered_voters=registered_voters,
        active_sessions=active_sessions,
        pending_proposals=pending_proposals,
        node_balance=node_balance,
    )
