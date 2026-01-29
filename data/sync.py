"""Hybrid data source for SharedLaw with local cache and IPFS sync.

Provides functionality to sync shared law data from IPFS while maintaining
a local cache for offline operation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class SharedLawSyncError(Exception):
    """Base exception for sync operations."""

    pass


class SharedLawSync:
    """Hybrid local + IPFS data source for shared law.

    Maintains a local cache of shared law files with support for syncing
    from IPFS. The local cache is always used for reading, with IPFS
    sync available for updates.

    Usage:
        sync = SharedLawSync()

        # Check if local data is outdated
        if sync.is_outdated("QmXxx..."):
            sync.sync_from_ipfs("QmXxx...")

        # Get current version info
        version = sync.get_local_version()
    """

    # Files that make up the shared law
    SHARED_LAW_FILES = [
        "terms.json",
        "principles.json",
        "rules.json",
        "governance.json",
        "domains.json",
    ]

    def __init__(
        self,
        local_dir: Path | str | None = None,
        ipfs_gateway: str = "https://ipfs.io",
        timeout: float = 30.0,
    ):
        """Initialize SharedLawSync.

        Args:
            local_dir: Path to local data directory.
                      Defaults to 'data/' relative to this file.
            ipfs_gateway: IPFS gateway URL for fetching content.
            timeout: HTTP request timeout in seconds.
        """
        if local_dir is None:
            local_dir = Path(__file__).parent
        else:
            local_dir = Path(local_dir)

        self._local_dir = local_dir
        self._ipfs_gateway = ipfs_gateway.rstrip("/")
        self._timeout = timeout

        # Create local dir if it doesn't exist
        self._local_dir.mkdir(parents=True, exist_ok=True)

    @property
    def local_dir(self) -> Path:
        """Get the local data directory path."""
        return self._local_dir

    def get_local_version(self) -> str | None:
        """Get the version from the local governance.json.

        Returns:
            Version string (e.g., "1.0.0") or None if not found.
        """
        governance_path = self._local_dir / "governance.json"
        if not governance_path.exists():
            return None

        try:
            with open(governance_path) as f:
                data = json.load(f)
            return data.get("versioning", {}).get("current", {}).get("governance")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read local version: {e}")
            return None

    def get_local_hash(self) -> str:
        """Compute a hash of all local shared law files.

        Returns:
            SHA256 hash of concatenated file contents.
        """
        hasher = hashlib.sha256()

        for filename in sorted(self.SHARED_LAW_FILES):
            filepath = self._local_dir / filename
            if filepath.exists():
                with open(filepath, "rb") as f:
                    hasher.update(f.read())

        return hasher.hexdigest()

    def get_local_metadata(self) -> dict:
        """Get metadata about local shared law files.

        Returns:
            Dictionary with file modification times and sizes.
        """
        metadata = {
            "version": self.get_local_version(),
            "hash": self.get_local_hash(),
            "files": {},
        }

        for filename in self.SHARED_LAW_FILES:
            filepath = self._local_dir / filename
            if filepath.exists():
                stat = filepath.stat()
                metadata["files"][filename] = {
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "exists": True,
                }
            else:
                metadata["files"][filename] = {
                    "exists": False,
                }

        return metadata

    def _fetch_ipfs_content(self, cid: str, filename: str | None = None) -> bytes:
        """Fetch content from IPFS gateway.

        Args:
            cid: IPFS content ID (CID).
            filename: Optional filename for directory CIDs.

        Returns:
            Raw content bytes.

        Raises:
            SharedLawSyncError: If fetch fails.
        """
        if filename:
            url = f"{self._ipfs_gateway}/ipfs/{cid}/{filename}"
        else:
            url = f"{self._ipfs_gateway}/ipfs/{cid}"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPStatusError as e:
            raise SharedLawSyncError(f"IPFS fetch failed with status {e.response.status_code}: {url}")
        except httpx.RequestError as e:
            raise SharedLawSyncError(f"IPFS fetch failed: {e}")

    def get_remote_version(self, cid: str) -> str | None:
        """Get the version from remote IPFS governance.json.

        Args:
            cid: IPFS CID pointing to shared law directory.

        Returns:
            Version string or None if not found.
        """
        try:
            content = self._fetch_ipfs_content(cid, "governance.json")
            data = json.loads(content)
            return data.get("versioning", {}).get("current", {}).get("governance")
        except (SharedLawSyncError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to get remote version: {e}")
            return None

    def is_outdated(self, remote_cid: str) -> bool:
        """Check if local data is outdated compared to remote.

        Args:
            remote_cid: IPFS CID of the latest shared law.

        Returns:
            True if local version is older than remote.
        """
        local_version = self.get_local_version()
        if local_version is None:
            return True  # No local data

        remote_version = self.get_remote_version(remote_cid)
        if remote_version is None:
            return False  # Can't check, assume not outdated

        # Simple semantic version comparison
        try:
            local_parts = [int(x) for x in local_version.split(".")]
            remote_parts = [int(x) for x in remote_version.split(".")]
            return remote_parts > local_parts
        except ValueError:
            # Fallback to string comparison
            return remote_version > local_version

    def sync_from_ipfs(self, cid: str, backup: bool = True) -> bool:
        """Sync shared law files from IPFS.

        Downloads all shared law files from the given IPFS CID
        and replaces local copies.

        Args:
            cid: IPFS CID pointing to shared law directory.
            backup: If True, backup existing files before overwriting.

        Returns:
            True if sync succeeded, False otherwise.
        """
        logger.info(f"Syncing shared law from IPFS: {cid}")

        # Create backup if requested
        if backup:
            self._backup_local()

        # Download all files
        downloaded = {}
        for filename in self.SHARED_LAW_FILES:
            try:
                content = self._fetch_ipfs_content(cid, filename)
                # Validate JSON
                json.loads(content)
                downloaded[filename] = content
                logger.debug(f"Downloaded {filename}")
            except (SharedLawSyncError, json.JSONDecodeError) as e:
                logger.error(f"Failed to download {filename}: {e}")
                return False

        # All files downloaded successfully, write to disk
        for filename, content in downloaded.items():
            filepath = self._local_dir / filename
            with open(filepath, "wb") as f:
                f.write(content)

        logger.info(f"Successfully synced {len(downloaded)} files from IPFS")
        return True

    def _backup_local(self) -> Path | None:
        """Create a backup of local shared law files.

        Returns:
            Path to backup directory, or None if no files to backup.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self._local_dir / f"backup_{timestamp}"

        files_backed_up = 0
        for filename in self.SHARED_LAW_FILES:
            filepath = self._local_dir / filename
            if filepath.exists():
                if files_backed_up == 0:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filepath, backup_dir / filename)
                files_backed_up += 1

        if files_backed_up > 0:
            logger.info(f"Backed up {files_backed_up} files to {backup_dir}")
            return backup_dir
        return None

    def validate_local(self) -> dict[str, bool]:
        """Validate that all local shared law files are valid JSON.

        Returns:
            Dictionary mapping filename to validity status.
        """
        results = {}
        for filename in self.SHARED_LAW_FILES:
            filepath = self._local_dir / filename
            if not filepath.exists():
                results[filename] = False
                continue

            try:
                with open(filepath) as f:
                    json.load(f)
                results[filename] = True
            except (json.JSONDecodeError, IOError):
                results[filename] = False

        return results

    def get_ipfs_cid_for_version(self, version: str) -> str | None:
        """Look up the IPFS CID for a specific version.

        This would typically be implemented with a version registry.
        For now, returns None (not implemented).

        Args:
            version: Version string to look up.

        Returns:
            IPFS CID or None if not found.
        """
        # TODO: Implement version registry lookup
        # This could be a JSON file or an on-chain registry
        logger.warning("Version-to-CID lookup not yet implemented")
        return None
