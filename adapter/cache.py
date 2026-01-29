"""ForkCache for caching compiled Fork configurations.

Provides caching of LLM-generated Fork configurations as YAML files
for inspection and faster subsequent runs.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from config.fork import Fork

if TYPE_CHECKING:
    from .models import Persona

logger = logging.getLogger(__name__)


class ForkCache:
    """Cache for compiled Fork configurations.

    Stores Fork configurations as YAML files indexed by a hash of:
    - Persona content (excluding timestamps)
    - SharedLaw core version

    This allows inspection of generated Forks and avoids re-running
    LLM mapping when the same persona is used repeatedly.

    Default location: ~/.cache/dahao/forks/

    Usage:
        cache = ForkCache()
        fork = cache.get(persona, "1.0.0")
        if fork is None:
            fork = mapper.map(persona)
            cache.put(persona, "1.0.0", fork)
    """

    DEFAULT_CACHE_DIR = Path.home() / ".cache" / "dahao" / "forks"

    def __init__(self, cache_dir: str | Path | None = None):
        """Initialize the ForkCache.

        Args:
            cache_dir: Optional custom cache directory.
                      Defaults to ~/.cache/dahao/forks/
        """
        if cache_dir is None:
            self._cache_dir = self.DEFAULT_CACHE_DIR
        else:
            self._cache_dir = Path(cache_dir)

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"ForkCache initialized at: {self._cache_dir}")

    def _compute_cache_key(self, persona: "Persona", core_version: str) -> str:
        """Compute cache key from persona and version.

        Args:
            persona: The persona to hash.
            core_version: SharedLaw core version string.

        Returns:
            Hash string for cache key.
        """
        # Combine persona content hash with version
        content = f"{persona.content_hash()}:{core_version}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key.

        Args:
            cache_key: The cache key.

        Returns:
            Path to the cache file.
        """
        return self._cache_dir / f"fork_{cache_key}.yaml"

    def get(self, persona: "Persona", core_version: str) -> Fork | None:
        """Get a cached Fork if available and valid.

        The cache is invalidated if:
        - The cache file doesn't exist
        - The persona's last_updated is newer than the cache file

        Args:
            persona: The persona to look up.
            core_version: SharedLaw core version string.

        Returns:
            Cached Fork if available and valid, None otherwise.
        """
        cache_key = self._compute_cache_key(persona, core_version)
        cache_path = self._cache_path(cache_key)

        if not cache_path.exists():
            logger.debug(f"Cache miss: {cache_path}")
            return None

        # Check if cache is stale (persona updated after cache)
        cache_mtime = cache_path.stat().st_mtime
        persona_updated = persona.last_updated.timestamp()

        if persona_updated > cache_mtime:
            logger.debug(
                f"Cache stale: persona updated at {persona.last_updated}, "
                f"cache from {cache_mtime}"
            )
            return None

        # Load cached Fork
        try:
            fork = Fork.from_yaml(cache_path)
            logger.info(f"Loaded Fork from cache: {cache_path}")
            return fork
        except Exception as e:
            logger.warning(f"Failed to load cached Fork: {e}")
            return None

    def put(self, persona: "Persona", core_version: str, fork: Fork) -> Path:
        """Cache a Fork configuration.

        Args:
            persona: The source persona.
            core_version: SharedLaw core version string.
            fork: The Fork to cache.

        Returns:
            Path to the cache file.
        """
        cache_key = self._compute_cache_key(persona, core_version)
        cache_path = self._cache_path(cache_key)

        # Write Fork to YAML
        fork.to_yaml(cache_path)
        logger.info(f"Cached Fork to: {cache_path}")

        return cache_path

    def invalidate(self, persona: "Persona", core_version: str) -> bool:
        """Invalidate a cached Fork.

        Args:
            persona: The persona whose cache to invalidate.
            core_version: SharedLaw core version string.

        Returns:
            True if cache was removed, False if it didn't exist.
        """
        cache_key = self._compute_cache_key(persona, core_version)
        cache_path = self._cache_path(cache_key)

        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"Invalidated cache: {cache_path}")
            return True
        return False

    def clear(self) -> int:
        """Clear all cached Forks.

        Returns:
            Number of cache files removed.
        """
        count = 0
        for cache_file in self._cache_dir.glob("fork_*.yaml"):
            cache_file.unlink()
            count += 1
        logger.info(f"Cleared {count} cached Fork(s)")
        return count

    def list_cached(self) -> list[Path]:
        """List all cached Fork files.

        Returns:
            List of paths to cached Fork files.
        """
        return list(self._cache_dir.glob("fork_*.yaml"))
