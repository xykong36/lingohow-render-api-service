"""
Episode Storage Service

Manages episode JSON file storage with concurrent access control.
Provides CRUD operations for episode data with file locking.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)


class EpisodeServiceError(Exception):
    """Base exception for episode service errors."""
    pass


class EpisodeNotFoundError(EpisodeServiceError):
    """Raised when episode file is not found."""
    pass


class EpisodeLockError(EpisodeServiceError):
    """Raised when file lock cannot be acquired."""
    pass


class EpisodeService:
    """Service for managing episode JSON files with concurrent access control."""

    def __init__(self, storage_dir: str = "data/episodes"):
        """
        Initialize episode service.

        Args:
            storage_dir: Directory to store episode JSON files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Episode storage initialized at: {self.storage_dir}")

    def _get_episode_path(self, episode_id: int) -> Path:
        """Get the file path for an episode."""
        return self.storage_dir / f"EP{episode_id}.json"

    def _get_lock_path(self, episode_id: int) -> Path:
        """Get the lock file path for an episode."""
        return self.storage_dir / f"EP{episode_id}.lock"

    def save_episode(
        self,
        episode_id: int,
        sentences: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """
        Save episode data to JSON file with file locking.

        Args:
            episode_id: Episode ID
            sentences: List of sentence dictionaries
            metadata: Optional metadata to include
            timeout: Lock acquisition timeout in seconds

        Returns:
            Dict with save result information

        Raises:
            EpisodeLockError: If lock cannot be acquired
        """
        episode_path = self._get_episode_path(episode_id)
        lock_path = self._get_lock_path(episode_id)

        episode_data = {
            "episode_id": episode_id,
            "sentences": sentences,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "version": 1
        }

        try:
            with FileLock(lock_path, timeout=timeout):
                # Check if file exists to preserve creation time
                if episode_path.exists():
                    try:
                        existing_data = json.loads(episode_path.read_text(encoding='utf-8'))
                        episode_data["created_at"] = existing_data.get("created_at", episode_data["created_at"])
                        episode_data["version"] = existing_data.get("version", 0) + 1
                    except (json.JSONDecodeError, KeyError):
                        logger.warning(f"Could not read existing episode {episode_id}, creating new")

                # Write to file
                episode_path.write_text(
                    json.dumps(episode_data, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )

                logger.info(f"✅ Saved episode {episode_id} with {len(sentences)} sentences (version {episode_data['version']})")

                return {
                    "episode_id": episode_id,
                    "file_path": str(episode_path),
                    "sentence_count": len(sentences),
                    "version": episode_data["version"],
                    "saved_at": episode_data["updated_at"]
                }

        except Timeout:
            raise EpisodeLockError(f"Could not acquire lock for episode {episode_id} within {timeout} seconds")

    def read_episode(self, episode_id: int, timeout: int = 5) -> Dict[str, Any]:
        """
        Read episode data from JSON file.

        Args:
            episode_id: Episode ID
            timeout: Lock acquisition timeout in seconds

        Returns:
            Episode data dictionary

        Raises:
            EpisodeNotFoundError: If episode file does not exist
            EpisodeLockError: If lock cannot be acquired
        """
        episode_path = self._get_episode_path(episode_id)
        lock_path = self._get_lock_path(episode_id)

        if not episode_path.exists():
            raise EpisodeNotFoundError(f"Episode {episode_id} not found")

        try:
            with FileLock(lock_path, timeout=timeout):
                data = json.loads(episode_path.read_text(encoding='utf-8'))
                logger.info(f"📖 Read episode {episode_id} (version {data.get('version', 'unknown')})")
                return data

        except Timeout:
            raise EpisodeLockError(f"Could not acquire lock for episode {episode_id} within {timeout} seconds")
        except json.JSONDecodeError as e:
            raise EpisodeServiceError(f"Invalid JSON in episode {episode_id}: {e}")

    def update_episode(
        self,
        episode_id: int,
        sentences: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """
        Update entire episode data (full replacement).

        Args:
            episode_id: Episode ID
            sentences: New list of sentences
            metadata: Optional new metadata
            timeout: Lock acquisition timeout in seconds

        Returns:
            Update result information
        """
        # Full replacement uses same logic as save
        return self.save_episode(episode_id, sentences, metadata, timeout)

    def update_sentence(
        self,
        episode_id: int,
        sentence_index: int,
        sentence_data: Dict[str, Any],
        timeout: int = 10
    ) -> Dict[str, Any]:
        """
        Update a specific sentence in an episode.

        Args:
            episode_id: Episode ID
            sentence_index: Index of sentence to update (0-based)
            sentence_data: New sentence data
            timeout: Lock acquisition timeout in seconds

        Returns:
            Update result information

        Raises:
            EpisodeNotFoundError: If episode does not exist
            IndexError: If sentence_index is out of range
        """
        episode_path = self._get_episode_path(episode_id)
        lock_path = self._get_lock_path(episode_id)

        if not episode_path.exists():
            raise EpisodeNotFoundError(f"Episode {episode_id} not found")

        try:
            with FileLock(lock_path, timeout=timeout):
                # Read current data
                episode_data = json.loads(episode_path.read_text(encoding='utf-8'))

                # Validate index
                if sentence_index < 0 or sentence_index >= len(episode_data["sentences"]):
                    raise IndexError(f"Sentence index {sentence_index} out of range (0-{len(episode_data['sentences'])-1})")

                # Update sentence
                episode_data["sentences"][sentence_index] = sentence_data
                episode_data["updated_at"] = datetime.utcnow().isoformat()
                episode_data["version"] = episode_data.get("version", 0) + 1

                # Write back
                episode_path.write_text(
                    json.dumps(episode_data, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )

                logger.info(f"✅ Updated sentence {sentence_index} in episode {episode_id} (version {episode_data['version']})")

                return {
                    "episode_id": episode_id,
                    "sentence_index": sentence_index,
                    "version": episode_data["version"],
                    "updated_at": episode_data["updated_at"]
                }

        except Timeout:
            raise EpisodeLockError(f"Could not acquire lock for episode {episode_id} within {timeout} seconds")
        except json.JSONDecodeError as e:
            raise EpisodeServiceError(f"Invalid JSON in episode {episode_id}: {e}")

    def list_episodes(self) -> List[Dict[str, Any]]:
        """
        List all available episode files.

        Returns:
            List of episode information dictionaries
        """
        episodes = []

        for episode_file in sorted(self.storage_dir.glob("EP*.json")):
            try:
                # Extract episode ID from filename
                episode_id = int(episode_file.stem[2:])  # Remove "EP" prefix

                # Try to read basic info
                try:
                    data = json.loads(episode_file.read_text(encoding='utf-8'))
                    episodes.append({
                        "episode_id": episode_id,
                        "file_name": episode_file.name,
                        "sentence_count": len(data.get("sentences", [])),
                        "version": data.get("version", 0),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "file_size_bytes": episode_file.stat().st_size
                    })
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Could not read episode {episode_id}: {e}")
                    episodes.append({
                        "episode_id": episode_id,
                        "file_name": episode_file.name,
                        "error": "Invalid JSON or missing data",
                        "file_size_bytes": episode_file.stat().st_size
                    })

            except ValueError:
                logger.warning(f"Skipping invalid episode file: {episode_file.name}")
                continue

        logger.info(f"📋 Found {len(episodes)} episode files")
        return episodes

    def delete_episode(self, episode_id: int, timeout: int = 10) -> Dict[str, Any]:
        """
        Delete an episode file.

        Args:
            episode_id: Episode ID to delete
            timeout: Lock acquisition timeout in seconds

        Returns:
            Deletion result information

        Raises:
            EpisodeNotFoundError: If episode does not exist
        """
        episode_path = self._get_episode_path(episode_id)
        lock_path = self._get_lock_path(episode_id)

        if not episode_path.exists():
            raise EpisodeNotFoundError(f"Episode {episode_id} not found")

        try:
            with FileLock(lock_path, timeout=timeout):
                episode_path.unlink()
                logger.info(f"🗑️  Deleted episode {episode_id}")

                # Clean up lock file if it exists
                if lock_path.exists():
                    lock_path.unlink()

                return {
                    "episode_id": episode_id,
                    "deleted": True,
                    "deleted_at": datetime.utcnow().isoformat()
                }

        except Timeout:
            raise EpisodeLockError(f"Could not acquire lock for episode {episode_id} within {timeout} seconds")

    def episode_exists(self, episode_id: int) -> bool:
        """Check if an episode file exists."""
        return self._get_episode_path(episode_id).exists()
