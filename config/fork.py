"""Fork model - represents user's voting values and principles."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Fork(BaseModel):
    """User's voting values and principles that guide LLM decisions."""

    name: str = Field(description="Human-readable name for this fork/persona")
    principles: list[str] = Field(
        default_factory=list,
        description="Core principles that guide voting decisions",
    )
    voting_style: str = Field(
        default="balanced",
        description="Overall voting approach: cautious, balanced, aggressive",
    )
    abstain_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence threshold below which to abstain",
    )
    persona: str | None = Field(
        default=None,
        description="Optional persona description for more nuanced LLM behavior",
    )

    @classmethod
    def from_yaml(cls, fork_path: str | Path = "fork.yaml") -> "Fork":
        """Load fork from YAML file."""
        fork_path = Path(fork_path)
        if not fork_path.exists():
            raise FileNotFoundError(f"Fork file not found: {fork_path}")

        with open(fork_path) as f:
            fork_config = yaml.safe_load(f)

        return cls(**fork_config)

    def principles_as_text(self) -> str:
        """Format principles as numbered list for prompt inclusion."""
        if not self.principles:
            return "No specific principles defined."
        return "\n".join(f"{i+1}. {p}" for i, p in enumerate(self.principles))
