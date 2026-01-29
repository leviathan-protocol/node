"""SharedLaw loader for DAHAO governance data.

Loads and parses the shared law JSON files (terms, principles, rules, governance)
and provides methods to access and validate against them.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    DomainEntry,
    DomainsRegistry,
    Governance,
    GovernanceConsensus,
    GovernanceInstance,
    GovernanceLockedItems,
    Principle,
    Rule,
    Term,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SharedLawError(Exception):
    """Base exception for shared law operations."""

    pass


class SharedLawLoadError(SharedLawError):
    """Raised when loading shared law fails."""

    pass


class SharedLaw:
    """Loader and accessor for DAHAO shared law data.

    Loads terms, principles, rules, and governance configuration from JSON files
    and provides methods to access, query, and validate against them.

    Usage:
        shared_law = SharedLaw()  # Loads from default data/ directory
        shared_law = SharedLaw(Path("/custom/data/dir"))

        # Access terms
        term = shared_law.get_term("@purpose")

        # Access principles
        principle = shared_law.get_principle("@purpose_primacy")
        locked = shared_law.get_locked_principles()

        # Get governance thresholds
        threshold = shared_law.get_threshold("principle_modification")

        # Validate term references
        invalid = shared_law.validate_term_references(["@purpose", "@invalid"])
    """

    def __init__(self, data_dir: Path | str | None = None):
        """Initialize SharedLaw loader.

        Args:
            data_dir: Path to the data directory containing JSON files.
                     Defaults to 'data/' relative to this file's location.
        """
        if data_dir is None:
            # Default to data/ directory relative to this file
            data_dir = Path(__file__).parent
        else:
            data_dir = Path(data_dir)

        self._data_dir = data_dir
        self._terms: dict[str, Term] = {}
        self._principles: dict[str, Principle] = {}
        self._rules: dict[str, Rule] = {}
        self._governance: Governance | None = None
        self._domains: DomainsRegistry | None = None

        # Load all data files
        self._load_all()

    def _load_all(self) -> None:
        """Load all shared law JSON files."""
        self._load_terms()
        self._load_principles()
        self._load_rules()
        self._load_governance()
        self._load_domains()

    def _load_json(self, filename: str) -> dict:
        """Load a JSON file from the data directory.

        Args:
            filename: Name of the JSON file to load.

        Returns:
            Parsed JSON as a dictionary.

        Raises:
            SharedLawLoadError: If the file cannot be loaded or parsed.
        """
        filepath = self._data_dir / filename
        try:
            with open(filepath) as f:
                return json.load(f)
        except FileNotFoundError:
            raise SharedLawLoadError(f"Shared law file not found: {filepath}")
        except json.JSONDecodeError as e:
            raise SharedLawLoadError(f"Invalid JSON in {filepath}: {e}")

    def _load_terms(self) -> None:
        """Load terms from terms.json."""
        data = self._load_json("terms.json")

        for key, value in data.items():
            if key.startswith("_"):
                continue  # Skip metadata
            if key.startswith("@"):
                try:
                    self._terms[key] = Term.model_validate(value)
                except Exception as e:
                    logger.warning(f"Failed to parse term {key}: {e}")

        logger.debug(f"Loaded {len(self._terms)} terms")

    def _load_principles(self) -> None:
        """Load principles from principles.json."""
        data = self._load_json("principles.json")

        for key, value in data.items():
            if key.startswith("_"):
                continue  # Skip metadata
            if key.startswith("@"):
                try:
                    self._principles[key] = Principle.model_validate(value)
                except Exception as e:
                    logger.warning(f"Failed to parse principle {key}: {e}")

        logger.debug(f"Loaded {len(self._principles)} principles")

    def _load_rules(self) -> None:
        """Load rules from rules.json."""
        data = self._load_json("rules.json")

        for key, value in data.items():
            if key.startswith("_"):
                continue  # Skip metadata
            if key.startswith("@"):
                try:
                    self._rules[key] = Rule.model_validate(value)
                except Exception as e:
                    logger.warning(f"Failed to parse rule {key}: {e}")

        logger.debug(f"Loaded {len(self._rules)} rules")

    def _load_governance(self) -> None:
        """Load governance configuration from governance.json."""
        data = self._load_json("governance.json")

        # Remove metadata before parsing
        data = {k: v for k, v in data.items() if not k.startswith("_")}

        try:
            self._governance = Governance.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to parse governance config: {e}")
            # Create minimal governance config
            self._governance = Governance(
                instance=GovernanceInstance(id="unknown", name="Unknown"),
                consensus=GovernanceConsensus(),
                locked_items=GovernanceLockedItems(),
            )

        logger.debug("Loaded governance configuration")

    def _load_domains(self) -> None:
        """Load domains registry from domains.json."""
        data = self._load_json("domains.json")

        # Remove metadata before parsing
        meta_removed = {k: v for k, v in data.items() if not k.startswith("_")}

        try:
            domains = DomainsRegistry.model_validate(meta_removed)
            self._domains = domains
            logger.debug(f"Loaded {len(domains.domains)} domains")
        except Exception as e:
            logger.warning(f"Failed to parse domains registry: {e}")
            self._domains = DomainsRegistry()
            logger.debug("Using empty domains registry")

    # --- Term accessors ---

    def get_term(self, name: str) -> Term | None:
        """Get a term by name.

        Args:
            name: Term name (e.g., "@purpose" or "purpose").

        Returns:
            The Term if found, None otherwise.
        """
        # Normalize name to start with @
        if not name.startswith("@"):
            name = f"@{name}"
        return self._terms.get(name)

    def get_all_terms(self) -> dict[str, Term]:
        """Get all loaded terms."""
        return self._terms.copy()

    def term_exists(self, name: str) -> bool:
        """Check if a term exists.

        Args:
            name: Term name (with or without @ prefix).

        Returns:
            True if the term exists.
        """
        return self.get_term(name) is not None

    def validate_term_references(self, terms: list[str]) -> list[str]:
        """Validate a list of term references.

        Args:
            terms: List of term names to validate.

        Returns:
            List of invalid term names that don't exist.
        """
        invalid = []
        for term in terms:
            if not self.term_exists(term):
                invalid.append(term)
        return invalid

    def get_term_definition(self, name: str) -> str | None:
        """Get the definition of a term.

        Args:
            name: Term name.

        Returns:
            The term's definition string, or None if not found.
        """
        term = self.get_term(name)
        return term.definition if term else None

    def get_term_definitions(self, names: list[str]) -> dict[str, str]:
        """Get definitions for multiple terms.

        Args:
            names: List of term names.

        Returns:
            Dictionary mapping term names to their definitions.
            Missing terms are omitted.
        """
        result = {}
        for name in names:
            definition = self.get_term_definition(name)
            if definition:
                result[name] = definition
        return result

    # --- Principle accessors ---

    def get_principle(self, name: str) -> Principle | None:
        """Get a principle by name.

        Args:
            name: Principle name (e.g., "@purpose_primacy" or "purpose_primacy").

        Returns:
            The Principle if found, None otherwise.
        """
        if not name.startswith("@"):
            name = f"@{name}"
        return self._principles.get(name)

    def get_all_principles(self) -> dict[str, Principle]:
        """Get all loaded principles."""
        return self._principles.copy()

    def is_locked(self, principle_name: str) -> bool:
        """Check if a principle is locked.

        Args:
            principle_name: Principle name.

        Returns:
            True if the principle exists and is locked.
        """
        principle = self.get_principle(principle_name)
        return principle.locked if principle else False

    def get_locked_principles(self) -> list[str]:
        """Get list of all locked principle names.

        Returns:
            List of locked principle names (e.g., ["@purpose_primacy", ...]).
        """
        # First check governance config for explicit list
        if self._governance and self._governance.locked_items.principles:
            return self._governance.locked_items.principles

        # Fall back to scanning principles
        return [name for name, p in self._principles.items() if p.locked]

    def get_locked_principle_statements(self) -> dict[str, str]:
        """Get locked principles with their statements.

        Returns:
            Dictionary mapping locked principle names to their statements.
        """
        result = {}
        for name in self.get_locked_principles():
            principle = self.get_principle(name)
            if principle:
                result[name] = principle.statement
        return result

    def get_unlocked_principles(self) -> list[str]:
        """Get list of all unlocked principle names.

        Returns:
            List of unlocked principle names.
        """
        return [name for name, p in self._principles.items() if not p.locked]

    # --- Rule accessors ---

    def get_rule(self, name: str) -> Rule | None:
        """Get a rule by name.

        Args:
            name: Rule name (e.g., "@rule_proposal_process").

        Returns:
            The Rule if found, None otherwise.
        """
        if not name.startswith("@"):
            name = f"@{name}"
        return self._rules.get(name)

    def get_all_rules(self) -> dict[str, Rule]:
        """Get all loaded rules."""
        return self._rules.copy()

    def get_rules_implementing(self, principle_name: str) -> list[str]:
        """Get rules that implement a specific principle.

        Args:
            principle_name: Principle name.

        Returns:
            List of rule names that implement the principle.
        """
        if not principle_name.startswith("@"):
            principle_name = f"@{principle_name}"

        return [
            name
            for name, rule in self._rules.items()
            if principle_name in rule.implements_principles
        ]

    # --- Governance accessors ---

    @property
    def governance(self) -> Governance:
        """Get the governance configuration."""
        if self._governance is None:
            raise SharedLawError("Governance not loaded")
        return self._governance

    def get_threshold(self, change_type: str) -> float:
        """Get the consensus threshold for a change type.

        Args:
            change_type: Type of change (e.g., "principle_modification").

        Returns:
            The consensus threshold (e.g., 0.90).
            Returns 0.75 as default if not found.
        """
        thresholds = self.governance.consensus.thresholds
        return thresholds.get(change_type, 0.75)

    def get_all_thresholds(self) -> dict[str, float]:
        """Get all consensus thresholds."""
        return self.governance.consensus.thresholds.copy()

    @property
    def protection_ratchet_multiplier(self) -> float:
        """Get the protection ratchet multiplier."""
        return self.governance.consensus.protection_ratchet_multiplier

    @property
    def quorum_percentage(self) -> float:
        """Get the quorum percentage requirement."""
        return self.governance.consensus.quorum_percentage

    @property
    def core_version(self) -> str:
        """Get the current core version string."""
        versions = self.governance.versioning.current
        # Return the governance version as the core version
        return versions.get("governance", "1.0.0")

    @property
    def instance_id(self) -> str:
        """Get the instance ID."""
        return self.governance.instance.id

    @property
    def instance_purpose(self) -> str:
        """Get the instance purpose."""
        return self.governance.instance.purpose

    # --- Domain accessors ---

    def get_domain(self, domain_id: str) -> DomainEntry | None:
        """Get a domain by ID.

        Args:
            domain_id: Domain ID (e.g., "animal-welfare").

        Returns:
            The DomainEntry if found, None otherwise.
        """
        if self._domains is None:
            return None
        for domain in self._domains.domains:
            if domain.id == domain_id:
                return domain
        return None

    def get_all_domains(self) -> list[DomainEntry]:
        """Get all registered domains."""
        if self._domains is None:
            return []
        return self._domains.domains.copy()

    # --- Validation helpers ---

    def check_principle_alignment(
        self, statement: str, aligns_with: str | None = None
    ) -> dict[str, bool]:
        """Check if a statement aligns with or conflicts with locked principles.

        This is a simple keyword-based check that looks for direct negation
        of core principle concepts. For production use, consider using
        LLM-based semantic alignment checking.

        Args:
            statement: The statement to check.
            aligns_with: Optional principle name it claims to align with.

        Returns:
            Dictionary with 'has_conflict', 'conflicts', and 'alignment_valid' keys.
        """
        result = {
            "has_conflict": False,
            "conflicts": [],
            "alignment_valid": True,
        }

        statement_lower = statement.lower()

        # Only check for direct negation of core principle concepts
        # Map principle names to their core concepts that would indicate conflict
        conflict_patterns = {
            "@purpose_primacy": ["ignore purpose", "disregard purpose", "purpose doesn't matter"],
            "@democratic_evolution": ["unilateral", "without consensus", "bypass voting"],
            "@transparency": ["hide", "secret governance", "obscure decisions"],
            "@precautionary_default": ["ignore risk", "disregard harm", "skip protection"],
            "@protection_asymmetry": ["remove all protections", "eliminate safeguards"],
            "@inheritance_integrity": ["violate core", "ignore locked"],
        }

        for name, patterns in conflict_patterns.items():
            if name not in self.get_locked_principles():
                continue
            for pattern in patterns:
                if pattern in statement_lower:
                    result["has_conflict"] = True
                    result["conflicts"].append(name)
                    break

        # Validate claimed alignment
        if aligns_with:
            principle = self.get_principle(aligns_with)
            if principle is None:
                result["alignment_valid"] = False
            elif principle.locked:
                # Can claim alignment with locked principles
                pass

        return result

    def summary(self) -> dict:
        """Get a summary of loaded shared law data.

        Returns:
            Dictionary with counts and version info.
        """
        return {
            "instance_id": self.instance_id,
            "core_version": self.core_version,
            "terms_count": len(self._terms),
            "principles_count": len(self._principles),
            "locked_principles_count": len(self.get_locked_principles()),
            "rules_count": len(self._rules),
            "domains_count": len(self.get_all_domains()),
        }
