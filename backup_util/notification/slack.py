import json
from typing import Optional
import requests

from backup_util.constants import BackupStatus
from backup_util.logger import get_logger
from backup_util.models import BackupMetadata
from backup_util.notification.base import BaseNotifier

logger = get_logger()


def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


class SlackNotifier(BaseNotifier):
    """Sends backup status notifications to Slack via incoming webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_notification(self, metadata: BackupMetadata, error: Optional[Exception] = None) -> bool:
        if not self.webhook_url:
            return False

        is_success = metadata.status == BackupStatus.COMPLETED
        status_text = "SUCCESS" if is_success else "FAILED"
        status_emoji = ":white_check_mark:" if is_success else ":x:"
        color = "#2EB886" if is_success else "#E01E5A"

        title = f"{status_emoji} *Database Backup {status_text}* [{metadata.db_type.upper()}]"

        fields = [
            {"title": "Database", "value": f"`{metadata.database_name}`", "short": True},
            {"title": "Backup Type", "value": f"`{metadata.backup_type.upper()}`", "short": True},
            {"title": "Backup ID", "value": f"`{metadata.backup_id}`", "short": True},
            {"title": "Duration", "value": f"{metadata.duration_seconds:.2f}s", "short": True},
            {"title": "Uncompressed Size", "value": format_bytes(metadata.uncompressed_size_bytes), "short": True},
            {"title": "Compressed Size", "value": format_bytes(metadata.compressed_size_bytes), "short": True},
            {"title": "Compression", "value": f"`{metadata.compression_algorithm}`", "short": True},
            {"title": "SHA-256", "value": f"`{metadata.checksum_sha256[:16]}...`" if metadata.checksum_sha256 else "N/A", "short": True},
        ]

        if metadata.storage_locations:
            locations_str = "\n".join(f"• `{loc}`" for loc in metadata.storage_locations)
            fields.append({"title": "Storage Destination", "value": locations_str, "short": False})

        attachment = {
            "color": color,
            "fields": fields,
            "footer": "Database Backup Utility CLI",
            "ts": int(metadata.duration_seconds),
        }

        if not is_success:
            err_msg = str(error) if error else (metadata.error_message or "Unknown error")
            attachment["text"] = f"*:warning: Error Details:*\n```{err_msg}```"

        payload = {
            "text": title,
            "attachments": [attachment],
        }

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Slack notification sent successfully for backup '{metadata.backup_id}'")
                return True
            else:
                logger.warning(f"Slack notification returned HTTP {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Failed to send Slack notification: {e}")
            return False
