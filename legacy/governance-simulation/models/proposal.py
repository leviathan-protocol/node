"""Proposal data model."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProposalStatus(Enum):
    """Cosmos governance proposal status."""

    UNSPECIFIED = 0
    DEPOSIT_PERIOD = 1
    VOTING_PERIOD = 2
    PASSED = 3
    REJECTED = 4
    FAILED = 5


@dataclass
class Proposal:
    """Represents a governance proposal."""

    id: int
    title: str
    description: str
    status: ProposalStatus
    submit_time: datetime | None = None
    voting_start_time: datetime | None = None
    voting_end_time: datetime | None = None
    proposal_type: str = "unknown"

    def summary(self, max_length: int = 500) -> str:
        """Return a truncated summary of the proposal for LLM context."""
        desc = self.description
        if len(desc) > max_length:
            desc = desc[: max_length - 3] + "..."
        return f"Proposal #{self.id}: {self.title}\n\n{desc}"
