"""GET /proposals endpoint - List active governance proposals.

Returns proposals currently in voting period from the chain.
Mobile clients use this to display votable proposals to users.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.server import app_state

logger = logging.getLogger(__name__)

router = APIRouter()


class ProposalInfo(BaseModel):
    """Proposal information for API response."""

    id: int = Field(..., description="Proposal ID")
    title: str = Field(..., description="Proposal title")
    description: str = Field(..., description="Proposal description (may be truncated)")
    proposal_type: str = Field(default="TextProposal", description="Type of proposal")
    voting_start: str | None = Field(None, description="ISO 8601 voting start time")
    voting_end: str | None = Field(None, description="ISO 8601 voting end time")


class ProposalsResponse(BaseModel):
    """Response model for GET /proposals."""

    proposals: list[ProposalInfo] = Field(
        default_factory=list,
        description="List of proposals in voting period",
    )
    count: int = Field(0, description="Number of proposals")
    chain_connected: bool = Field(False, description="Whether chain is connected")


@router.get("/proposals", response_model=ProposalsResponse)
async def list_proposals() -> ProposalsResponse:
    """List all proposals currently in voting period.

    Returns proposals that users can vote on. For each proposal:
    - id: Unique proposal identifier
    - title: Human-readable title
    - description: Full or truncated description
    - voting_start/end: Voting period timestamps

    Returns:
        ProposalsResponse with list of active proposals.
    """
    logger.info("Fetching proposals in voting period")

    # Check if we have a governance client connected
    if app_state.chain_client is None:
        logger.warning("Chain client not connected, returning empty proposals")
        return ProposalsResponse(
            proposals=_get_mock_proposals(),
            count=len(_get_mock_proposals()),
            chain_connected=False,
        )

    try:
        # Use existing GovernanceClient to fetch proposals
        from chain.client import ChainClient
        from chain.governance import GovernanceClient
        from config.settings import ChainConfig

        # Get config from app state
        config = getattr(app_state, "chain_config", None)
        if config is None:
            # Create default config
            config = ChainConfig(
                chain_id="dahao",
                grpc_url="grpc+http://localhost:9090",
            )

        gov_client = GovernanceClient(app_state.chain_client, config)
        proposals = gov_client.fetch_voting_proposals()

        # Convert to API model
        proposal_infos = []
        for p in proposals:
            proposal_infos.append(
                ProposalInfo(
                    id=p.id,
                    title=p.title,
                    description=p.description[:500] if p.description else "",
                    proposal_type=p.proposal_type or "TextProposal",
                    voting_start=p.voting_start_time.isoformat() if p.voting_start_time else None,
                    voting_end=p.voting_end_time.isoformat() if p.voting_end_time else None,
                )
            )

        logger.info(f"Found {len(proposal_infos)} proposals in voting period")

        return ProposalsResponse(
            proposals=proposal_infos,
            count=len(proposal_infos),
            chain_connected=True,
        )

    except Exception as e:
        logger.error(f"Failed to fetch proposals: {e}")
        # Return mock data on error
        return ProposalsResponse(
            proposals=_get_mock_proposals(),
            count=len(_get_mock_proposals()),
            chain_connected=False,
        )


def _get_mock_proposals() -> list[ProposalInfo]:
    """Return mock proposals for testing when chain is not connected."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    voting_end = now + timedelta(days=7)
    return [
        ProposalInfo(
            id=1,
            title="[Mock] Increase Block Size to 2MB",
            description="This proposal aims to increase the maximum block size from 1MB to 2MB to improve transaction throughput.",
            proposal_type="TextProposal",
            voting_start=now.isoformat(),
            voting_end=voting_end.isoformat(),
        ),
        ProposalInfo(
            id=2,
            title="[Mock] Enable IBC with TestChain",
            description="Enable Inter-Blockchain Communication with TestChain network.",
            proposal_type="TextProposal",
            voting_start=now.isoformat(),
            voting_end=voting_end.isoformat(),
        ),
    ]
