"""Leviathan shared law data module.

This module provides access to the shared law data structures that all
Leviathan instances inherit: terms, principles, rules, and governance config.
"""

from .loader import SharedLaw, SharedLawError, SharedLawLoadError
from .models import (
    DomainEntry,
    DomainsRegistry,
    EvidenceQualityTier,
    Governance,
    GovernanceAutomation,
    GovernanceConsensus,
    GovernanceDomainRequirements,
    GovernanceInstance,
    GovernanceLockedItems,
    GovernanceTiming,
    GovernanceVersioning,
    Principle,
    Rule,
    Term,
)
from .sync import SharedLawSync, SharedLawSyncError

__all__ = [
    # Main loader
    "SharedLaw",
    "SharedLawError",
    "SharedLawLoadError",
    # Sync
    "SharedLawSync",
    "SharedLawSyncError",
    # Models
    "Term",
    "EvidenceQualityTier",
    "Principle",
    "Rule",
    "Governance",
    "GovernanceInstance",
    "GovernanceVersioning",
    "GovernanceConsensus",
    "GovernanceTiming",
    "GovernanceAutomation",
    "GovernanceLockedItems",
    "GovernanceDomainRequirements",
    "DomainEntry",
    "DomainsRegistry",
]
