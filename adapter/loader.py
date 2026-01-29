"""PersonaLoader for finding and loading persona.json files.

Implements a search path for persona files:
1. Explicit path from CLI argument
2. ./persona.json in current directory
3. ~/.config/dahao/persona.json for user default
"""

from __future__ import annotations

import logging
from pathlib import Path

from .models import Persona

logger = logging.getLogger(__name__)


class PersonaNotFoundError(Exception):
    """Raised when no persona file can be found in any search path."""

    pass


class PersonaLoadError(Exception):
    """Raised when a persona file exists but cannot be loaded."""

    pass


class PersonaLoader:
    """Loads Persona configurations from JSON files.

    Searches multiple locations for persona.json files:
    1. Explicit path provided via CLI
    2. ./persona.json in current working directory
    3. ~/.config/dahao/persona.json for user default

    Usage:
        # With explicit path
        loader = PersonaLoader("/path/to/persona.json")
        persona = loader.load_or_raise()

        # Without explicit path (searches default locations)
        loader = PersonaLoader()
        persona = loader.load()  # Returns None if not found
    """

    DEFAULT_LOCATIONS = [
        Path("./persona.json"),
        Path.home() / ".config" / "dahao" / "persona.json",
    ]

    def __init__(self, explicit_path: str | Path | None = None):
        """Initialize the PersonaLoader.

        Args:
            explicit_path: Optional explicit path to persona.json.
                          If provided, only this path will be checked.
        """
        self._explicit_path = Path(explicit_path) if explicit_path else None

    def find_persona_file(self) -> Path | None:
        """Find the first available persona.json file.

        Searches in order:
        1. Explicit path (if provided)
        2. ./persona.json
        3. ~/.config/dahao/persona.json

        Returns:
            Path to the found persona file, or None if not found.
        """
        # If explicit path was provided, only check that
        if self._explicit_path:
            if self._explicit_path.exists():
                logger.debug(f"Found persona at explicit path: {self._explicit_path}")
                return self._explicit_path
            logger.debug(f"Explicit persona path not found: {self._explicit_path}")
            return None

        # Search default locations
        for path in self.DEFAULT_LOCATIONS:
            if path.exists():
                logger.debug(f"Found persona at default location: {path}")
                return path
            logger.debug(f"Persona not found at: {path}")

        return None

    def load(self) -> Persona | None:
        """Load a persona from the first available location.

        Returns:
            Loaded Persona instance, or None if no persona file found.

        Raises:
            PersonaLoadError: If a file was found but couldn't be loaded.
        """
        path = self.find_persona_file()
        if path is None:
            return None

        try:
            persona = Persona.from_json_file(path)
            logger.info(f"Loaded persona '{persona.archetype}' from {path}")
            return persona
        except (ValueError, OSError) as e:
            raise PersonaLoadError(f"Failed to load persona from {path}: {e}")

    def load_or_raise(self) -> Persona:
        """Load a persona, raising an error if not found.

        Returns:
            Loaded Persona instance.

        Raises:
            PersonaNotFoundError: If no persona file could be found.
            PersonaLoadError: If a file was found but couldn't be loaded.
        """
        persona = self.load()
        if persona is None:
            if self._explicit_path:
                raise PersonaNotFoundError(
                    f"Persona file not found at: {self._explicit_path}"
                )
            else:
                search_paths = [str(p) for p in self.DEFAULT_LOCATIONS]
                raise PersonaNotFoundError(
                    f"No persona file found. Searched: {search_paths}"
                )
        return persona
