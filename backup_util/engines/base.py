from abc import ABC, abstractmethod
from typing import Any, BinaryIO, Dict, List, Optional

from backup_util.models import BackupMetadata, BackupOptions, DatabaseConfig


class BaseEngine(ABC):
    """Abstract base class for DBMS backup and restore engines."""

    def __init__(self, config: DatabaseConfig):
        self.config = config

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Tests database connectivity, validates credentials, and returns
        diagnostic info (e.g., version, database name, table/collection count).
        Raises ConnectionFailedError if testing fails.
        """
        pass

    @abstractmethod
    def list_tables_or_collections(self) -> List[str]:
        """Returns a list of tables or collections in the target database."""
        pass

    @abstractmethod
    def backup(
        self,
        output_stream: BinaryIO,
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata] = None,
    ) -> List[str]:
        """
        Dumps database contents directly into output_stream.
        Returns a list of tables/collections backed up.
        """
        pass

    @abstractmethod
    def restore(
        self,
        input_stream: BinaryIO,
        options: BackupOptions,
    ) -> Dict[str, Any]:
        """
        Restores database from input_stream.
        Supports selective restore via options.tables or options.collections.
        Returns a summary dict of restore operations.
        """
        pass
