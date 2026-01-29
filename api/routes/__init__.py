"""API route handlers for DAHAO Sidecar Observer Mode."""

from . import pair, proposals, status, vote
from .pair import (
    ConnectRequest,
    ConnectResponse,
    InviteResponse,
    RegisterRequest,
    RegisterResponse,
)
from .proposals import ProposalInfo, ProposalsResponse
from .status import StatusResponse
from .vote import VoteRejectResponse, VoteSubmitRequest, VoteSubmitResponse

__all__ = [
    # Route modules
    "pair",
    "status",
    "vote",
    "proposals",
    # Pair models
    "InviteResponse",
    "ConnectRequest",
    "ConnectResponse",
    "RegisterRequest",
    "RegisterResponse",
    # Status models
    "StatusResponse",
    # Vote models
    "VoteSubmitRequest",
    "VoteSubmitResponse",
    "VoteRejectResponse",
    # Proposals models
    "ProposalInfo",
    "ProposalsResponse",
]
