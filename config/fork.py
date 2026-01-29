"""Fork model - represents user's voting values and principles.

Supports both simple (backward-compatible) and enhanced formats with
validation against shared law.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from brain.llm import LLMWrapper
    from data.loader import SharedLaw


class ForkValidationError(Exception):
    """Raised when fork validation fails against shared law."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__(f"Fork validation failed: {', '.join(violations)}")


class ForkPrinciple(BaseModel):
    """A structured fork principle with alignment metadata.

    Enhanced format that links to shared law terms and principles.
    """

    statement: str = Field(description="The principle statement")
    aligns_with: str | None = Field(
        default=None,
        description="Core principle this aligns with (e.g., '@precautionary_default')",
    )
    applies_to: str | None = Field(
        default=None,
        description="What this principle applies to (e.g., '@stakeholder.direct')",
    )


class Fork(BaseModel):
    """User's voting values and principles that guide LLM decisions.

    Supports two formats:

    Simple (backward-compatible):
    ```yaml
    name: "Security-First Validator"
    principles:
      - "Prioritize network security"
    ```

    Enhanced (with shared law references):
    ```yaml
    name: "Security-First Validator"
    inherits: "dahao-core v1.0.0"
    uses_terms:
      - "@protection"
      - "@harm"
    principles:
      - statement: "Prioritize network security"
        aligns_with: "@precautionary_default"
    ```
    """

    name: str = Field(description="Human-readable name for this fork/persona")

    # Enhanced format fields
    inherits: str = Field(
        default="dahao-core v1.0.0",
        description="Core DAHAO version this fork inherits from",
    )
    uses_terms: list[str] = Field(
        default_factory=list,
        description="Terms from shared vocabulary this fork references",
    )

    # Principles can be simple strings or structured ForkPrinciple objects
    principles: list[str | ForkPrinciple] = Field(
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

    # Internal tracking
    _validated_against: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_principles(cls, data: dict) -> dict:
        """Normalize principles to support both formats."""
        if "principles" not in data:
            return data

        principles = data["principles"]
        if not isinstance(principles, list):
            return data

        # Convert mixed formats to consistent internal format
        normalized = []
        for p in principles:
            if isinstance(p, str):
                normalized.append(p)
            elif isinstance(p, dict):
                normalized.append(ForkPrinciple.model_validate(p))
            else:
                normalized.append(p)

        data["principles"] = normalized
        return data

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

        lines = []
        for i, p in enumerate(self.principles):
            if isinstance(p, str):
                lines.append(f"{i+1}. {p}")
            elif isinstance(p, ForkPrinciple):
                text = f"{i+1}. {p.statement}"
                if p.aligns_with:
                    text += f" (aligns with {p.aligns_with})"
                lines.append(text)

        return "\n".join(lines)

    def get_principle_statements(self) -> list[str]:
        """Get just the statement text from all principles."""
        statements = []
        for p in self.principles:
            if isinstance(p, str):
                statements.append(p)
            elif isinstance(p, ForkPrinciple):
                statements.append(p.statement)
        return statements

    def get_aligned_principles(self) -> dict[str, str]:
        """Get mapping of aligned core principles to fork statements.

        Returns:
            Dictionary mapping core principle names to fork principle statements.
        """
        aligned = {}
        for p in self.principles:
            if isinstance(p, ForkPrinciple) and p.aligns_with:
                aligned[p.aligns_with] = p.statement
        return aligned

    @property
    def inherits_version(self) -> str:
        """Extract version from inherits string.

        Returns:
            Version string (e.g., "1.0.0") or "1.0.0" as default.
        """
        if " v" in self.inherits:
            return self.inherits.split(" v")[-1]
        elif " " in self.inherits:
            return self.inherits.split()[-1]
        return "1.0.0"

    @property
    def inherits_source(self) -> str:
        """Extract source from inherits string.

        Returns:
            Source name (e.g., "dahao-core").
        """
        if " v" in self.inherits:
            return self.inherits.split(" v")[0]
        elif " " in self.inherits:
            parts = self.inherits.split()
            return " ".join(parts[:-1])
        return self.inherits

    def validate_against(self, shared_law: "SharedLaw") -> None:
        """Validate this fork against shared law.

        Checks:
        1. All referenced terms exist
        2. Principles don't violate locked principles
        3. Aligned principles exist

        Args:
            shared_law: SharedLaw instance to validate against.

        Raises:
            ForkValidationError: If validation fails.
        """
        violations = []

        # Check term references exist
        if self.uses_terms:
            invalid_terms = shared_law.validate_term_references(self.uses_terms)
            if invalid_terms:
                violations.append(f"Invalid terms: {invalid_terms}")

        # Check principle alignments
        locked_principles = shared_law.get_locked_principles()

        for p in self.principles:
            if isinstance(p, ForkPrinciple):
                # Check that aligned principles exist
                if p.aligns_with:
                    principle = shared_law.get_principle(p.aligns_with)
                    if principle is None:
                        violations.append(
                            f"Aligned principle '{p.aligns_with}' does not exist"
                        )

                # Check statement doesn't violate locked principles
                alignment = shared_law.check_principle_alignment(
                    p.statement, p.aligns_with
                )
                if alignment["has_conflict"]:
                    conflicts = alignment["conflicts"]
                    violations.append(
                        f"Statement '{p.statement[:50]}...' conflicts with "
                        f"locked principles: {conflicts}"
                    )

            elif isinstance(p, str):
                # Simple string principle - check for conflicts
                alignment = shared_law.check_principle_alignment(p)
                if alignment["has_conflict"]:
                    conflicts = alignment["conflicts"]
                    violations.append(
                        f"Principle '{p[:50]}...' may conflict with "
                        f"locked principles: {conflicts}"
                    )

        if violations:
            raise ForkValidationError(violations)

        # Mark as validated
        self._validated_against = shared_law.core_version

    def is_validated(self) -> bool:
        """Check if fork has been validated against shared law."""
        return self._validated_against is not None

    def get_term_context(self, shared_law: "SharedLaw") -> dict[str, str]:
        """Get term definitions for this fork's uses_terms.

        Args:
            shared_law: SharedLaw instance.

        Returns:
            Dictionary mapping term names to definitions.
        """
        return shared_law.get_term_definitions(self.uses_terms)

    def validate_against_with_llm(
        self,
        shared_law: "SharedLaw",
        llm: "LLMWrapper",
    ) -> None:
        """Validate this fork against shared law using LLM semantic analysis.

        This provides more accurate validation than simple pattern matching
        by using the LLM to understand if principles semantically conflict.

        Checks:
        1. All referenced terms exist (fast, no LLM)
        2. Aligned principles exist (fast, no LLM)
        3. Fork principles don't violate locked principles (LLM-based)

        Args:
            shared_law: SharedLaw instance to validate against.
            llm: LLMWrapper instance for semantic validation.

        Raises:
            ForkValidationError: If validation fails.
        """
        from brain.llm import LLMWrapper  # Import here to avoid circular

        violations = []

        # Fast checks first (no LLM needed)
        if self.uses_terms:
            invalid_terms = shared_law.validate_term_references(self.uses_terms)
            if invalid_terms:
                violations.append(f"Invalid terms: {invalid_terms}")

        # Check aligned principles exist
        for p in self.principles:
            if isinstance(p, ForkPrinciple) and p.aligns_with:
                principle = shared_law.get_principle(p.aligns_with)
                if principle is None:
                    violations.append(
                        f"Aligned principle '{p.aligns_with}' does not exist"
                    )

        # If basic checks failed, don't bother with LLM
        if violations:
            raise ForkValidationError(violations)

        # LLM-based semantic validation
        fork_statements = self.get_principle_statements()
        locked_statements = shared_law.get_locked_principle_statements()

        if fork_statements and locked_statements:
            result = llm.validate_fork(fork_statements, locked_statements)

            if not result.get("valid", True):
                for v in result.get("violations", []):
                    violations.append(
                        f"'{v.get('fork_principle', 'Unknown')[:50]}...' "
                        f"violates {v.get('locked_principle', 'unknown')}: "
                        f"{v.get('reason', 'no reason given')}"
                    )

        if violations:
            raise ForkValidationError(violations)

        # Mark as validated
        self._validated_against = shared_law.core_version

    def to_yaml(self, path: str | Path) -> None:
        """Serialize this Fork to a YAML file.

        Useful for caching generated Fork configurations or exporting
        for manual inspection.

        Args:
            path: Path to write the YAML file.
        """
        path = Path(path)

        # Convert to serializable dict
        data = {
            "name": self.name,
            "inherits": self.inherits,
            "voting_style": self.voting_style,
            "abstain_threshold": self.abstain_threshold,
        }

        # Add uses_terms if present
        if self.uses_terms:
            data["uses_terms"] = self.uses_terms

        # Convert principles to serializable format
        principles_data = []
        for p in self.principles:
            if isinstance(p, str):
                principles_data.append(p)
            elif isinstance(p, ForkPrinciple):
                p_dict = {"statement": p.statement}
                if p.aligns_with:
                    p_dict["aligns_with"] = p.aligns_with
                if p.applies_to:
                    p_dict["applies_to"] = p.applies_to
                principles_data.append(p_dict)

        data["principles"] = principles_data

        # Add persona if present
        if self.persona:
            data["persona"] = self.persona

        # Write YAML with nice formatting
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
