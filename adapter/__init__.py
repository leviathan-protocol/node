"""Identity Adapter module for Leviathan.

Converts external persona.json files (from Journal App) into valid Fork
configurations for the Leviathan sidecar.

Usage:
    from adapter import PersonaLoader, PersonaMapper, Persona

    # Load persona
    loader = PersonaLoader("/path/to/persona.json")
    persona = loader.load_or_raise()

    # Map to Fork
    mapper = PersonaMapper(llm, shared_law)
    fork = mapper.map(persona)

    # Optional: Cache the generated Fork
    cache = ForkCache()
    cache.put(persona, shared_law.core_version, fork)
"""

from .cache import ForkCache
from .loader import PersonaLoader, PersonaLoadError, PersonaNotFoundError
from .mapper import PersonaMapper, PersonaMappingError
from .models import Persona

__all__ = [
    # Models
    "Persona",
    # Loader
    "PersonaLoader",
    "PersonaNotFoundError",
    "PersonaLoadError",
    # Mapper
    "PersonaMapper",
    "PersonaMappingError",
    # Cache
    "ForkCache",
]
