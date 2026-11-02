from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from backup_util.models import BackupMetadata


class BaseStorage(ABC):
    """Abstract base class for backup storage backends."""

    @abstractmethod
    def store(self, src_local_path: str, destination_name: str, metadata: Optional[BackupMetadata] = None) -> str:
        """
        Store a local backup file into the storage target.
        Returns the persistent location string (file path, s3:// URI, etc.).
        """
        pass

    @abstractmethod
    def retrieve(self, location: str, dest_local_path: str) -> str:
        """
        Retrieve a backup file from storage and save it to dest_local_path.
        Returns dest_local_path.
        """
        pass

    @abstractmethod
    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups stored in this backend."""
        pass

    @abstractmethod
    def delete(self, location: str) -> bool:
        """Delete a backup file from storage."""
        pass

    @abstractmethod
    def cleanup_retention(self, retention_count: Optional[int] = None, retention_days: Optional[int] = None) -> int:
        """Prune older backups based on count or age in days. Returns number of backups deleted."""
        pass
