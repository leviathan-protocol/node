"""Vote decision data model."""

from dataclasses import dataclass
from enum import Enum


class VoteChoice(Enum):
    """Cosmos governance vote options."""

    YES = 1
    ABSTAIN = 2
    NO = 3
    NO_WITH_VETO = 4

    @classmethod
    def from_string(cls, value: str) -> "VoteChoice":
        """Convert string to VoteChoice."""
        mapping = {
            "YES": cls.YES,
            "ABSTAIN": cls.ABSTAIN,
            "NO": cls.NO,
            "NO_WITH_VETO": cls.NO_WITH_VETO,
        }
        return mapping[value.upper()]


@dataclass
class VoteDecision:
    """Represents an LLM's voting decision."""

    choice: VoteChoice
    confidence: float
    reasoning: str

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0 and 1, got {self.confidence}")
