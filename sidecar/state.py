"""Persistent state for tracking processed proposals."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SidecarState:
    """Tracks which proposals have been processed to avoid re-voting."""

    processed_proposals: set[int] = field(default_factory=set)
    state_file: Path = field(default=Path("sidecar_state.json"))

    def __post_init__(self):
        if isinstance(self.state_file, str):
            self.state_file = Path(self.state_file)

    @classmethod
    def load(cls, state_file: str | Path = "sidecar_state.json") -> "SidecarState":
        """Load state from file, or create new if doesn't exist."""
        state_file = Path(state_file)
        state = cls(state_file=state_file)

        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                    state.processed_proposals = set(data.get("processed_proposals", []))
                logger.info(f"Loaded state: {len(state.processed_proposals)} processed proposals")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load state file, starting fresh: {e}")

        return state

    def save(self):
        """Save state to file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(
                    {"processed_proposals": list(self.processed_proposals)},
                    f,
                    indent=2,
                )
            logger.debug(f"Saved state: {len(self.processed_proposals)} processed proposals")
        except IOError as e:
            logger.error(f"Failed to save state: {e}")

    def mark_processed(self, proposal_id: int):
        """Mark a proposal as processed and save state."""
        self.processed_proposals.add(proposal_id)
        self.save()

    def is_processed(self, proposal_id: int) -> bool:
        """Check if a proposal has been processed."""
        return proposal_id in self.processed_proposals
