from abc import ABC, abstractmethod
from typing import Optional
from backup_util.models import BackupMetadata


class BaseNotifier(ABC):
    """Abstract base notifier for sending backup status alerts."""

    @abstractmethod
    def send_notification(self, metadata: BackupMetadata, error: Optional[Exception] = None) -> bool:
        """Sends notification for a backup execution. Returns True if successful."""
        pass
