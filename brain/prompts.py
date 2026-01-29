"""Prompt templates for LLM voting decisions.

Enhanced with shared law context including term definitions, locked principles,
and governance thresholds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.fork import Fork
from models.proposal import Proposal

if TYPE_CHECKING:
    from data.loader import SharedLaw


SYSTEM_PROMPT = """You are a governance voting assistant for a Cosmos blockchain validator. Your role is to analyze governance proposals and make voting decisions based on the user's stated principles and values.

You must respond with a JSON object containing:
- "vote": One of "YES", "NO", "ABSTAIN", or "NO_WITH_VETO"
- "confidence": A decimal between 0.0 and 1.0 indicating your confidence
- "reasoning": A brief explanation of your decision

Use NO_WITH_VETO only for proposals that are spam, harmful to the network, or violate fundamental principles.
Use ABSTAIN when you lack sufficient information or the proposal is outside your expertise.

Consider the user's principles carefully when making decisions."""


SYSTEM_PROMPT_ENHANCED = """You are a governance voting assistant for a Cosmos blockchain validator operating under the DAHAO governance framework. Your role is to analyze governance proposals and make voting decisions based on:

1. **Locked Principles** - These MUST NOT be violated under any circumstances
2. **User's Fork Principles** - Personal values that guide the validator's decisions
3. **Governance Thresholds** - Consensus requirements for different change types

You must respond with a JSON object containing:
- "vote": One of "YES", "NO", "ABSTAIN", or "NO_WITH_VETO"
- "confidence": A decimal between 0.0 and 1.0 indicating your confidence
- "reasoning": A brief explanation of your decision
- "terms_referenced": Optional list of @terms that are relevant to your decision
- "principles_applied": Optional list of principles (locked or personal) that informed your decision

Use NO_WITH_VETO only for proposals that are spam, harmful to the network, or violate locked principles.
Use ABSTAIN when you lack sufficient information or the proposal is outside your expertise.

IMPORTANT: Any proposal that conflicts with a locked principle should receive a NO vote, regardless of other considerations."""


USER_PROMPT_TEMPLATE = """# Validator Identity: {fork_name}

## Voting Style
{voting_style}

## Core Principles
{principles}
{persona_section}
---

# Proposal to Evaluate

{proposal_summary}

---

Based on the above principles and the proposal content, provide your voting decision as JSON."""


USER_PROMPT_TEMPLATE_ENHANCED = """# Validator Identity: {fork_name}
Inherits: {inherits}

## DAHAO Locked Principles (MUST NOT be violated)
{locked_principles}

## Governance Thresholds
{thresholds}
{term_definitions}
## Validator's Personal Principles
{principles}
{persona_section}
---

# Proposal to Evaluate

{proposal_summary}

---

Based on the locked principles, governance context, and your personal principles, provide your voting decision as JSON.

Remember:
- Proposals violating locked principles should receive NO votes
- Your confidence should reflect alignment with both locked and personal principles
- Reference specific terms and principles in your reasoning when applicable"""


def build_voting_prompt(
    proposal: Proposal,
    fork: Fork,
    shared_law: "SharedLaw | None" = None,
) -> list[dict]:
    """Build the chat messages for a voting decision.

    Args:
        proposal: The proposal to evaluate
        fork: The user's voting values
        shared_law: Optional SharedLaw for enhanced context

    Returns:
        List of chat messages in OpenAI format
    """
    if shared_law is not None:
        return _build_enhanced_prompt(proposal, fork, shared_law)
    else:
        return _build_simple_prompt(proposal, fork)


def _build_simple_prompt(proposal: Proposal, fork: Fork) -> list[dict]:
    """Build a simple prompt without shared law context (backward compatible)."""
    # Include persona section if defined
    persona_section = ""
    if fork.persona:
        persona_section = f"\n## Persona\n{fork.persona.strip()}\n"

    user_content = USER_PROMPT_TEMPLATE.format(
        fork_name=fork.name,
        voting_style=fork.voting_style.capitalize(),
        principles=fork.principles_as_text(),
        persona_section=persona_section,
        proposal_summary=proposal.summary(max_length=2000),
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _build_enhanced_prompt(
    proposal: Proposal,
    fork: Fork,
    shared_law: "SharedLaw",
) -> list[dict]:
    """Build an enhanced prompt with shared law context."""
    # Format locked principles
    locked_statements = shared_law.get_locked_principle_statements()
    locked_text = "\n".join(
        f"- {name}: {statement}"
        for name, statement in locked_statements.items()
    )

    # Format governance thresholds (relevant ones)
    thresholds = shared_law.get_all_thresholds()
    relevant_thresholds = {
        k: v for k, v in thresholds.items()
        if any(x in k for x in ["principle", "rule", "protection"])
    }
    thresholds_text = "\n".join(
        f"- {k.replace('_', ' ').title()}: {v*100:.0f}%"
        for k, v in relevant_thresholds.items()
    )
    thresholds_text += f"\n- Protection Ratchet: {shared_law.protection_ratchet_multiplier}x for removals"

    # Format term definitions if fork uses terms
    term_definitions = ""
    if fork.uses_terms:
        definitions = fork.get_term_context(shared_law)
        if definitions:
            term_definitions = "\n## Referenced Terms\n"
            for name, defn in definitions.items():
                # Truncate long definitions
                if len(defn) > 200:
                    defn = defn[:200] + "..."
                term_definitions += f"- {name}: {defn}\n"
            term_definitions += "\n"

    # Include persona section if defined
    persona_section = ""
    if fork.persona:
        persona_section = f"\n## Persona\n{fork.persona.strip()}\n"

    user_content = USER_PROMPT_TEMPLATE_ENHANCED.format(
        fork_name=fork.name,
        inherits=fork.inherits,
        locked_principles=locked_text,
        thresholds=thresholds_text,
        term_definitions=term_definitions,
        principles=fork.principles_as_text(),
        persona_section=persona_section,
        proposal_summary=proposal.summary(max_length=2000),
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT_ENHANCED},
        {"role": "user", "content": user_content},
    ]


def _get_relevant_term_definitions(
    proposal: Proposal,
    fork: Fork,
    shared_law: "SharedLaw",
) -> dict[str, str]:
    """Extract relevant term definitions for a proposal.

    Looks at both fork's uses_terms and terms mentioned in the proposal.

    Args:
        proposal: The proposal being evaluated.
        fork: The user's fork.
        shared_law: SharedLaw instance.

    Returns:
        Dictionary mapping term names to definitions.
    """
    terms_to_include = set(fork.uses_terms)

    # Also look for @terms mentioned in proposal content
    proposal_text = f"{proposal.title} {proposal.description}"
    for term_name in shared_law.get_all_terms().keys():
        if term_name in proposal_text:
            terms_to_include.add(term_name)

    return shared_law.get_term_definitions(list(terms_to_include))
