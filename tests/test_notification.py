from unittest.mock import MagicMock, patch
import pytest

from backup_util.constants import BackupStatus, BackupType, CompressionType
from backup_util.models import BackupMetadata, NotificationConfig
from backup_util.notification.slack import SlackNotifier
from backup_util.notification import NotificationDispatcher


@pytest.fixture
def sample_metadata():
    return BackupMetadata(
        backup_id="test_db_full_20261101",
        db_type="mysql",
        database_name="production_db",
        backup_type=BackupType.FULL,
        filename="test_db.sql.gz",
        uncompressed_size_bytes=1048576,
        compressed_size_bytes=262144,
        checksum_sha256="abc123def4567890",
        start_time="2026-11-01T12:00:00",
        end_time="2026-11-01T12:00:05",
        duration_seconds=5.25,
        status=BackupStatus.COMPLETED,
        storage_locations=["s3://my-bucket/db-backups/test_db.sql.gz"],
    )


@patch("requests.post")
def test_slack_notifier_success(mock_post, sample_metadata):
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = "ok"

    notifier = SlackNotifier("https://hooks.slack.com/services/T00/B00/X00")
    success = notifier.send_notification(sample_metadata)

    assert success is True
    assert mock_post.called
    payload = mock_post.call_args[1]["json"]
    assert "Database Backup SUCCESS" in payload["text"]
    assert payload["attachments"][0]["color"] == "#2EB886"


@patch("requests.post")
def test_slack_notifier_failure(mock_post, sample_metadata):
    mock_post.return_value.status_code = 200

    sample_metadata.status = BackupStatus.FAILED
    sample_metadata.error_message = "Connection timed out"

    notifier = SlackNotifier("https://hooks.slack.com/services/T00/B00/X00")
    success = notifier.send_notification(sample_metadata, error=Exception("Connection timed out"))

    assert success is True
    payload = mock_post.call_args[1]["json"]
    assert "Database Backup FAILED" in payload["text"]
    assert payload["attachments"][0]["color"] == "#E01E5A"
    assert "Connection timed out" in payload["attachments"][0]["text"]


@patch("requests.post")
def test_notification_dispatcher(mock_post, sample_metadata):
    mock_post.return_value.status_code = 200

    conf = NotificationConfig(
        slack_webhook_url="https://hooks.slack.com/services/test",
        notify_on_success=True,
    )
    dispatcher = NotificationDispatcher(conf)
    dispatcher.dispatch(sample_metadata)
    assert mock_post.called
