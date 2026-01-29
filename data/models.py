"""Pydantic models for DAHAO shared law data structures.

These models represent the terms, principles, rules, and governance
configuration that all DAHAO instances inherit.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TermMeta(BaseModel):
    """Metadata for the terms collection."""

    type: str = "terms"
    description: str = ""
    version: str = "1.0.0"
    created: str | None = None
    updated: str | None = None


class EvidenceQualityTier(BaseModel):
    """A single evidence quality tier definition."""

    name: str
    description: str
    weight: float = Field(ge=0.0, le=1.0)


class Term(BaseModel):
    """A term definition from the shared vocabulary.

    Terms provide universal definitions that all DAHAO domains use.
    Examples: @purpose, @stakeholder, @vote, @evidence, etc.
    """

    version: str = "1.0.0"
    definition: str
    required: bool = False
    types: list[str] | None = None
    properties: dict[str, str] | None = None
    note: str | None = None
    examples: list[str] | None = None
    assessment: str | None = None
    ratchet: str | None = None
    required_fields: list[str] | None = None
    lifecycle: list[str] | None = None
    thresholds: dict[str, float | str] | None = None
    default: float | None = None
    calculation: str | None = None
    phases: list[dict] | None = None
    minimum_duration_days: int | None = None
    quality_tiers: dict[str, EvidenceQualityTier] | None = None
    minimum_for_proposal: dict[str, str | int] | None = None
    format: str | None = None
    rules: dict[str, str] | None = None
    rights: list[str] | None = None
    identification: str | None = None
    relationship: str | None = None
    freedom: str | None = None
    contribution: str | None = None
    requirements: list[str] | None = None


class PrincipleMeta(BaseModel):
    """Metadata for the principles collection."""

    type: str = "principles"
    description: str = ""
    version: str = "1.0.0"
    created: str | None = None
    updated: str | None = None
    note: str | None = None


class Principle(BaseModel):
    """A core principle from the DAHAO governance framework.

    Principles can be locked (cannot be violated) or unlocked (domains may adjust).
    """

    version: str = "1.0.0"
    statement: str
    locked: bool = False
    lock_reason: str | None = None
    uses_terms: list[str] = Field(default_factory=list)
    implications: list[str] = Field(default_factory=list)
    rationale: str | None = None
    note: str | None = None
    mechanism: str | None = None


class RuleMeta(BaseModel):
    """Metadata for the rules collection."""

    type: str = "rules"
    description: str = ""
    version: str = "1.0.0"
    created: str | None = None
    updated: str | None = None
    note: str | None = None


class Rule(BaseModel):
    """An executable governance rule.

    Rules implement principles and reference terms to define
    specific governance procedures.
    """

    version: str = "1.0.0"
    description: str
    logic: str | dict[str, str] = ""
    uses_terms: list[str] = Field(default_factory=list)
    implements_principles: list[str] = Field(default_factory=list)
    phases: dict | None = None
    thresholds: dict[str, float] | None = None
    rationale: str | None = None
    examples: dict[str, str | list[str]] | None = None
    active_definition: str | None = None
    format: str | None = None
    example: str | None = None
    labels: dict[str, str] | None = None
    completion: str | None = None
    minimum: dict[str, str | int] | None = None
    exemptions: list[str] | None = None
    checks: list[str] | None = None
    executor: str | None = None
    enforcement: str | None = None
    on_violation: str | None = None
    requirements: list[str] | None = None
    validation: str | None = None
    tracking: dict | None = None
    note: str | None = None


class GovernanceInstance(BaseModel):
    """Instance configuration for a DAHAO governance instance."""

    id: str
    name: str
    type: str = "core"
    description: str = ""
    purpose: str = ""
    created: str | None = None
    maintainers: list[dict] = Field(default_factory=list)


class GovernanceVersioning(BaseModel):
    """Version tracking for governance components."""

    current: dict[str, str] = Field(default_factory=dict)
    format: str = "semantic"
    history_retention: str = "forever"


class GovernanceConsensus(BaseModel):
    """Consensus thresholds and settings."""

    thresholds: dict[str, float] = Field(default_factory=dict)
    protection_ratchet_multiplier: float = 1.5
    quorum_percentage: float = 0.30
    quorum_window_days: int = 90


class GovernanceTiming(BaseModel):
    """Timing requirements for governance processes."""

    discussion_minimum_days: dict[str, int] = Field(default_factory=dict)
    voting_minimum_days: dict[str, int] = Field(default_factory=dict)


class GovernanceAutomation(BaseModel):
    """Automation settings for governance."""

    alignment_check_on_proposal: bool = True
    auto_reject_principle_conflicts: bool = True
    auto_merge_on_consensus: bool = True
    auto_version_bump: bool = True
    llm_assistance_allowed: bool = True


class GovernanceLockedItems(BaseModel):
    """Lists of locked items that cannot be modified."""

    principles: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)


class GovernanceDomainRequirements(BaseModel):
    """Requirements for domain inheritance."""

    must_inherit_core: bool = True
    must_declare_purpose: bool = True
    must_respect_locked_principles: bool = True
    may_add_stricter_rules: bool = True
    may_not_loosen_core_rules: bool = True


class Governance(BaseModel):
    """Complete governance configuration."""

    instance: GovernanceInstance
    versioning: GovernanceVersioning = Field(default_factory=GovernanceVersioning)
    consensus: GovernanceConsensus = Field(default_factory=GovernanceConsensus)
    timing: GovernanceTiming = Field(default_factory=GovernanceTiming)
    automation: GovernanceAutomation = Field(default_factory=GovernanceAutomation)
    locked_items: GovernanceLockedItems = Field(default_factory=GovernanceLockedItems)
    platforms: dict[str, str] = Field(default_factory=dict)
    domain_requirements: GovernanceDomainRequirements = Field(
        default_factory=GovernanceDomainRequirements
    )


class DomainEntry(BaseModel):
    """A domain instance entry in the registry."""

    id: str
    name: str
    purpose: str
    inherits_core_version: str
    status: str = "active"
    created: str | None = None


class DomainsMeta(BaseModel):
    """Metadata for the domains registry."""

    type: str = "domains_registry"
    description: str = ""
    version: str = "1.0.0"
    updated: str | None = None


class DomainsRegistry(BaseModel):
    """Registry of known DAHAO domains."""

    domains: list[DomainEntry] = Field(default_factory=list)
    statistics: dict[str, int] = Field(default_factory=dict)
