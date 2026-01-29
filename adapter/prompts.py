"""LLM prompts and schemas for persona-to-fork mapping.

Provides the structured output schema and prompt templates used by
PersonaMapper to convert external personas into valid Fork configurations.
"""

# JSON Schema for LLM structured output when mapping persona to fork
PERSONA_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Human-readable name for this fork, derived from archetype",
        },
        "inherits": {
            "type": "string",
            "description": "Core DAHAO version to inherit from (always 'dahao-core v1.0.0')",
        },
        "uses_terms": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of @terms from shared vocabulary this fork references",
        },
        "principles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "The principle statement",
                    },
                    "aligns_with": {
                        "type": "string",
                        "description": "MUST be a PRINCIPLE name (e.g., '@precautionary_default', '@purpose_primacy'). NEVER use term names like @protection or @harm here.",
                    },
                },
                "required": ["statement", "aligns_with"],
            },
            "description": "Fork principles mapped from core values",
        },
        "voting_style": {
            "type": "string",
            "enum": ["cautious", "balanced", "aggressive"],
            "description": "Overall voting approach inferred from decision_style",
        },
        "abstain_threshold": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence threshold below which to abstain (0.0-1.0)",
        },
        "persona": {
            "type": "string",
            "description": "LLM persona description for nuanced voting behavior",
        },
    },
    "required": [
        "name",
        "inherits",
        "uses_terms",
        "principles",
        "voting_style",
        "abstain_threshold",
        "persona",
    ],
}


def build_system_prompt(
    terms: dict[str, str],
    locked_principles: dict[str, str],
    unlocked_principles: dict[str, str],
) -> str:
    """Build the system prompt for persona mapping.

    Args:
        terms: Dictionary mapping term names to definitions.
        locked_principles: Dictionary mapping locked principle names to statements.
        unlocked_principles: Dictionary mapping unlocked principle names to statements.

    Returns:
        System prompt string for the LLM.
    """
    # Format terms section
    terms_text = "\n".join(f"- {name}: {definition}" for name, definition in terms.items())

    # Format locked principles section
    locked_text = "\n".join(
        f"- {name}: {statement}" for name, statement in locked_principles.items()
    )

    # Format unlocked principles section
    unlocked_text = "\n".join(
        f"- {name}: {statement}" for name, statement in unlocked_principles.items()
    )

    # Build valid aligns_with list (principle names only)
    all_principle_names = list(locked_principles.keys()) + list(unlocked_principles.keys())
    valid_aligns_with = ", ".join(all_principle_names)

    return f"""You are a governance configuration specialist for the DAHAO framework. Your task is to convert external user personas into valid Fork configurations that respect the governance framework.

## Available Terms (for uses_terms field ONLY)
These are vocabulary terms that can ONLY be used in the "uses_terms" array. DO NOT use these in "aligns_with":
{terms_text}

## Locked Principles (MUST NOT VIOLATE)
These are immutable principles. You can reference their names in "aligns_with":
{locked_text}

## Unlocked Principles (can align with)
These are principles you can reference in "aligns_with":
{unlocked_text}

## CRITICAL: Valid aligns_with Values
The "aligns_with" field MUST ONLY contain one of these PRINCIPLE names:
{valid_aligns_with}

DO NOT use term names (like @protection, @harm, @evidence) in aligns_with!
Terms go in "uses_terms", principles go in "aligns_with".

## Your Task
Convert the user's persona into a Fork configuration that:
1. Preserves the user's core values and decision-making style
2. Maps values to principles with aligns_with references to EXISTING PRINCIPLES ONLY
3. NEVER creates principles that violate locked principles
4. Selects appropriate terms for uses_terms (vocabulary only)
5. Infers voting_style and abstain_threshold from decision_style

## Voting Style Mapping
- "High caution" / "requires strong evidence" / "conservative" → "cautious" with abstain_threshold 0.7-0.8
- "Moderate" / "balanced" / "flexible" → "balanced" with abstain_threshold 0.5-0.6
- "Progressive" / "risk-tolerant" / "fast-moving" → "aggressive" with abstain_threshold 0.3-0.4

## Principle Mapping Guidelines
- Each core value should map to ONE principle
- aligns_with MUST be one of: {valid_aligns_with}
- NEVER use term names in aligns_with (e.g., @protection is a TERM, not a principle)
- Principles must be actionable and specific to voting decisions
- NEVER include principles that directly contradict locked principles

## Name Generation
- Derive a descriptive name from the archetype
- Format: "[Archetype] Node" (e.g., "Deep Ecologist Node")

## Persona Field
- Write a 2-3 sentence persona description for LLM context
- Describe how this persona approaches governance decisions
- Include their key priorities and decision-making philosophy"""


def build_user_prompt(
    user_id: str,
    archetype: str,
    core_values: list[str],
    decision_style: str,
) -> str:
    """Build the user prompt for persona mapping.

    Args:
        user_id: User identifier.
        archetype: Persona archetype.
        core_values: List of core values.
        decision_style: Decision-making style description.

    Returns:
        User prompt string for the LLM.
    """
    values_text = "\n".join(f"  - {value}" for value in core_values)

    return f"""Convert this persona to a Fork configuration:

## Persona Details
- User ID: {user_id}
- Archetype: {archetype}
- Decision Style: {decision_style}

## Core Values
{values_text}

Generate a valid Fork configuration as JSON. Ensure all principles align with existing locked or unlocked principles, and that no principle violates the locked principles."""
