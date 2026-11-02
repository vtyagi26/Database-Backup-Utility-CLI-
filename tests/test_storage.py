import os
import tempfile
import time
from pathlib import Path
import pytest

from backup_util.constants import BackupStatus, BackupType, CompressionType
from backup_util.models import BackupMetadata, StorageConfig
from backup_util.storage.local import LocalStorage


def test_local_storage_lifecycle():
    with tempfile.TemporaryDirectory() as storage_dir:
        storage = LocalStorage(base_dir=storage_dir)

        # Create dummy backup file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Backup archive payload")
            src_file = f.name

        try:
            meta = BackupMetadata(
                backup_id="test_backup_001",
                db_type="sqlite",
                database_name="test.db",
                filename="test_backup_001.sql.gz",
                start_time="2026-11-01T12:00:00",
                status=BackupStatus.COMPLETED,
            )

            stored_path = storage.store(src_file, "test_backup_001.sql.gz", metadata=meta)
            assert os.path.exists(stored_path)
            assert os.path.exists(stored_path + ".meta.json")

            # List backups
            backups = storage.list_backups()
            assert len(backups) == 1
            assert backups[0]["name"] == "test_backup_001.sql.gz"
            assert backups[0]["metadata"]["backup_id"] == "test_backup_001"

            # Retrieve
            with tempfile.TemporaryDirectory() as retrieve_dir:
                dest = os.path.join(retrieve_dir, "restored.sql.gz")
                storage.retrieve(stored_path, dest)
                assert os.path.exists(dest)
                with open(dest, "rb") as rf:
                    assert rf.read() == b"Backup archive payload"

            # Delete
            assert storage.delete(stored_path) is True
            assert len(storage.list_backups()) == 0

        finally:
            if os.path.exists(src_file):
                os.unlink(src_file)


def test_local_storage_retention():
    with tempfile.TemporaryDirectory() as storage_dir:
        storage = LocalStorage(base_dir=storage_dir)

        # Create 5 backup files with different timestamps
        for i in range(5):
            p = Path(storage_dir) / f"backup_{i}.sql.gz"
            p.write_bytes(f"Content {i}".encode())
            time.sleep(0.01)

        assert len(storage.list_backups()) == 5

        # Prune to keep 2 newest
        pruned = storage.cleanup_retention(retention_count=2)
        assert pruned == 3
        remaining = storage.list_backups()
        assert len(remaining) == 2
