from typing import List, Optional
from backup_util.constants import BackupStatus
from backup_util.models import BackupMetadata, NotificationConfig
from backup_util.notification.base import BaseNotifier
from backup_util.notification.slack import SlackNotifier
from backup_util.notification.webhook import WebhookNotifier


class NotificationDispatcher:
    """Manages and dispatches notifications across all configured channels."""

    def __init__(self, config: NotificationConfig):
        self.config = config
        self.notifiers: List[BaseNotifier] = []

        if config.slack_webhook_url:
            self.notifiers.append(SlackNotifier(config.slack_webhook_url))
        if config.discord_webhook_url:
            self.notifiers.append(WebhookNotifier(config.discord_webhook_url, is_discord=True))
        if config.generic_webhook_url:
            self.notifiers.append(WebhookNotifier(config.generic_webhook_url, is_discord=False))

    def dispatch(self, metadata: BackupMetadata, error: Optional[Exception] = None) -> None:
        is_success = metadata.status == BackupStatus.COMPLETED
        if is_success and not self.config.notify_on_success:
            return
        if not is_success and not self.config.notify_on_failure:
            return

        for notifier in self.notifiers:
            try:
                notifier.send_notification(metadata, error)
            except Exception:
                pass


__all__ = ["BaseNotifier", "SlackNotifier", "WebhookNotifier", "NotificationDispatcher"]
