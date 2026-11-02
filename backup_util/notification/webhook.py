import json
from typing import Optional
import requests

from backup_util.constants import BackupStatus
from backup_util.logger import get_logger
from backup_util.models import BackupMetadata
from backup_util.notification.base import BaseNotifier

logger = get_logger()


class WebhookNotifier(BaseNotifier):
    """Sends JSON webhook alerts to arbitrary webhook endpoints or Discord."""

    def __init__(self, webhook_url: str, is_discord: bool = False):
        self.webhook_url = webhook_url
        self.is_discord = is_discord

    def send_notification(self, metadata: BackupMetadata, error: Optional[Exception] = None) -> bool:
        if not self.webhook_url:
            return False

        if self.is_discord:
            return self._send_discord(metadata, error)

        # Standard generic JSON payload
        payload = {
            "event": "database_backup",
            "status": metadata.status.value,
            "backup_id": metadata.backup_id,
            "database_name": metadata.database_name,
            "db_type": metadata.db_type,
            "backup_type": metadata.backup_type.value,
            "duration_seconds": metadata.duration_seconds,
            "uncompressed_bytes": metadata.uncompressed_size_bytes,
            "compressed_bytes": metadata.compressed_size_bytes,
            "checksum_sha256": metadata.checksum_sha256,
            "storage_locations": metadata.storage_locations,
            "error": str(error) if error else metadata.error_message,
        }

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            return resp.status_code in (200, 201, 202, 204)
        except Exception as e:
            logger.warning(f"Failed to send generic webhook notification: {e}")
            return False

    def _send_discord(self, metadata: BackupMetadata, error: Optional[Exception] = None) -> bool:
        is_success = metadata.status == BackupStatus.COMPLETED
        color = 3066993 if is_success else 15158332

        embed = {
            "title": f"Database Backup {'Success' if is_success else 'Failure'}: {metadata.database_name}",
            "color": color,
            "fields": [
                {"name": "DBMS", "value": metadata.db_type, "inline": True},
                {"name": "Type", "value": metadata.backup_type.value, "inline": True},
                {"name": "Duration", "value": f"{metadata.duration_seconds:.2f}s", "inline": True},
                {"name": "Compressed Size", "value": f"{metadata.compressed_size_bytes:,} bytes", "inline": True},
                {"name": "Locations", "value": "\n".join(metadata.storage_locations) or "Local", "inline": False},
            ],
        }

        if not is_success:
            embed["description"] = f"**Error:**\n```{str(error) if error else metadata.error_message}```"

        try:
            resp = requests.post(
                self.webhook_url,
                json={"embeds": [embed]},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Failed to send Discord notification: {e}")
            return False
