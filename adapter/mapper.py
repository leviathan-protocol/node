"""PersonaMapper for converting Persona to Fork configurations.

Uses LLM to semantically map external persona values to valid Fork
configurations that respect the Leviathan SharedLaw governance framework.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from config.fork import Fork, ForkPrinciple

from .models import Persona
from .prompts import PERSONA_MAPPING_SCHEMA, build_system_prompt, build_user_prompt

if TYPE_CHECKING:
    from brain.llm import LLMWrapper
    from data.loader import SharedLaw

logger = logging.getLogger(__name__)


class PersonaMappingError(Exception):
    """Raised when persona mapping fails."""

    pass


class PersonaMapper:
    """Maps external Persona objects to valid Fork configurations.

    Uses an LLM to semantically convert persona values and decision styles
    into Fork configurations that:
    - Preserve the user's core values
    - Map values to SharedLaw principles
    - Respect locked principles
    - Use appropriate SharedLaw terms

    Usage:
        mapper = PersonaMapper(llm, shared_law)
        fork = mapper.map(persona)
    """

    def __init__(self, llm: "LLMWrapper", shared_law: "SharedLaw"):
        """Initialize the PersonaMapper.

        Args:
            llm: LLMWrapper instance for generating mappings.
            shared_law: SharedLaw instance for term and principle references.
        """
        self._llm = llm
        self._shared_law = shared_law

    def _get_term_definitions(self) -> dict[str, str]:
        """Get all term definitions from shared law.

        Returns:
            Dictionary mapping term names to definitions.
        """
        terms = self._shared_law.get_all_terms()
        return {name: term.definition for name, term in terms.items()}

    def _get_locked_principle_statements(self) -> dict[str, str]:
        """Get statements for all locked principles.

        Returns:
            Dictionary mapping principle names to statements.
        """
        return self._shared_law.get_locked_principle_statements()

    def _get_unlocked_principle_statements(self) -> dict[str, str]:
        """Get statements for all unlocked principles.

        Returns:
            Dictionary mapping principle names to statements.
        """
        unlocked_names = self._shared_law.get_unlocked_principles()
        result = {}
        for name in unlocked_names:
            principle = self._shared_law.get_principle(name)
            if principle:
                result[name] = principle.statement
        return result

    def map(self, persona: Persona) -> Fork:
        """Map a Persona to a Fork configuration.

        Uses LLM to semantically convert the persona's values and
        decision style into a valid Fork configuration.

        Args:
            persona: The Persona to convert.

        Returns:
            A valid Fork configuration.

        Raises:
            PersonaMappingError: If mapping fails.
        """
        logger.info(f"Mapping persona '{persona.archetype}' to Fork configuration")

        # Build prompts with shared law context
        system_prompt = build_system_prompt(
            terms=self._get_term_definitions(),
            locked_principles=self._get_locked_principle_statements(),
            unlocked_principles=self._get_unlocked_principle_statements(),
        )

        user_prompt = build_user_prompt(
            user_id=persona.user_id,
            archetype=persona.archetype,
            core_values=persona.core_values,
            decision_style=persona.decision_style,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # Call LLM with structured output
            response = self._llm.client.chat(
                model=self._llm.model,
                messages=messages,
                format=PERSONA_MAPPING_SCHEMA,
                options={
                    "temperature": 0.5,  # Balance creativity with consistency
                    "num_ctx": self._llm.config.n_ctx,
                },
            )

            result = json.loads(response.message.content)
            logger.debug(f"LLM mapping result: {result}")

        except json.JSONDecodeError as e:
            raise PersonaMappingError(f"Failed to parse LLM response as JSON: {e}")
        except Exception as e:
            raise PersonaMappingError(f"LLM call failed: {e}")

        # Convert LLM result to Fork object
        try:
            fork = self._result_to_fork(result)
            logger.info(f"Successfully mapped persona to Fork: {fork.name}")
            return fork
        except Exception as e:
            raise PersonaMappingError(f"Failed to create Fork from mapping: {e}")

    def _get_valid_principle_names(self) -> set[str]:
        """Get all valid principle names (for aligns_with validation).

        Returns:
            Set of valid principle names.
        """
        locked = set(self._shared_law.get_locked_principles())
        unlocked = set(self._shared_law.get_unlocked_principles())
        return locked | unlocked

    def _result_to_fork(self, result: dict) -> Fork:
        """Convert LLM result dict to a Fork object.

        Args:
            result: Dictionary from LLM structured output.

        Returns:
            Fork instance.

        Raises:
            PersonaMappingError: If aligns_with contains invalid values.
        """
        valid_principles = self._get_valid_principle_names()
        term_names = set(self._shared_law.get_all_terms().keys())

        # Convert principles from dicts to ForkPrinciple objects
        principles = []
        for p in result.get("principles", []):
            if isinstance(p, dict):
                aligns_with = p.get("aligns_with")

                # Validate aligns_with is a principle, not a term
                if aligns_with:
                    if aligns_with in term_names:
                        raise PersonaMappingError(
                            f"LLM used term '{aligns_with}' in aligns_with, but only "
                            f"principles are valid. Valid principles: {sorted(valid_principles)}"
                        )
                    if aligns_with not in valid_principles:
                        raise PersonaMappingError(
                            f"LLM used invalid aligns_with '{aligns_with}'. "
                            f"Valid principles: {sorted(valid_principles)}"
                        )

                principles.append(
                    ForkPrinciple(
                        statement=p.get("statement", ""),
                        aligns_with=aligns_with,
                    )
                )
            else:
                # Handle simple string principles
                principles.append(str(p))

        return Fork(
            name=result.get("name", "Generated Fork"),
            inherits=result.get("inherits", "leviathan-core v1.0.0"),
            uses_terms=result.get("uses_terms", []),
            principles=principles,
            voting_style=result.get("voting_style", "balanced"),
            abstain_threshold=result.get("abstain_threshold", 0.6),
            persona=result.get("persona"),
        )
