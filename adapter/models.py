"""Pydantic models for the Identity Adapter.

Provides the Persona model for loading external persona.json files from
the Journal App and converting them to Fork configurations.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class Persona(BaseModel):
    """A user persona from the Journal App.

    Represents an external identity file that can be converted to a Fork
    configuration for DAHAO governance participation.

    Example persona.json:
    ```json
    {
        "user_id": "alice_123",
        "archetype": "Deep Ecologist",
        "core_values": [
            "Nature has intrinsic rights regardless of human utility",
            "Slow down technological acceleration if it harms ecosystems",
            "Privacy is essential for individual freedom"
        ],
        "decision_style": "High caution, requires strong evidence",
        "last_updated": "2026-01-29T14:00:00Z"
    }
    ```
    """

    user_id: str = Field(description="Unique identifier for the user")
    archetype: str = Field(description="High-level persona archetype (e.g., 'Deep Ecologist')")
    core_values: list[str] = Field(
        default_factory=list,
        description="List of core values that guide decision-making",
    )
    decision_style: str = Field(
        default="balanced",
        description="Decision-making style (e.g., 'High caution, requires strong evidence')",
    )
    last_updated: datetime = Field(
        default_factory=datetime.now,
        description="When this persona was last updated",
    )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "Persona":
        """Load a Persona from a JSON file.

        Args:
            path: Path to the persona.json file.

        Returns:
            Parsed Persona instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the JSON is invalid or missing required fields.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Persona file not found: {path}")

        try:
            with open(path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in persona file {path}: {e}")

        return cls.model_validate(data)

    def content_hash(self) -> str:
        """Generate a hash of the persona content for caching.

        Returns:
            SHA256 hash of the serialized persona content.
        """
        import hashlib

        # Serialize to JSON with sorted keys for consistent hashing
        content = self.model_dump_json(exclude={"last_updated"})
        return hashlib.sha256(content.encode()).hexdigest()[:16]
