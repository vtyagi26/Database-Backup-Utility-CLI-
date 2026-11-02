import os
import sqlite3
import tempfile
import pytest

from backup_util.constants import BackupStatus, BackupType, CompressionType, DatabaseType, StorageType
from backup_util.manager import BackupManager
from backup_util.models import BackupOptions, DatabaseConfig, NotificationConfig, StorageConfig


@pytest.fixture
def populated_sqlite_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE products (id INT, title TEXT, price REAL);")
    cur.execute("INSERT INTO products VALUES (1, 'Widget', 19.99);")
    cur.execute("INSERT INTO products VALUES (2, 'Gadget', 49.99);")
    conn.commit()
    conn.close()

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)


def test_manager_end_to_end_backup_and_restore(populated_sqlite_db):
    with tempfile.TemporaryDirectory() as storage_dir:
        db_conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=populated_sqlite_db)
        storage_conf = StorageConfig(storage_type=StorageType.LOCAL, local_path=storage_dir)
        options = BackupOptions(
            backup_type=BackupType.FULL,
            compression=CompressionType.GZIP,
            compression_level=6,
        )

        manager = BackupManager(
            db_config=db_conf,
            storage_config=storage_conf,
            options=options,
        )

        # 1. Test connection
        conn_info = manager.test_connection()
        assert conn_info["status"] == "connected"

        # 2. Run backup
        meta = manager.run_backup()
        assert meta.status == BackupStatus.COMPLETED
        assert meta.compressed_size_bytes > 0
        assert meta.checksum_sha256 != ""
        assert len(meta.storage_locations) == 1

        stored_file = meta.storage_locations[0]
        assert os.path.exists(stored_file)

        # 3. List backups
        backups = manager.list_backups()
        assert len(backups) == 1
        assert backups[0]["name"] == meta.filename

        # 4. Restore to a new sqlite file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            target_restore_db = tf.name

        try:
            restore_mgr = BackupManager(
                db_config=DatabaseConfig(db_type=DatabaseType.SQLITE, database=target_restore_db),
                storage_config=storage_conf,
                options=options,
            )

            res = restore_mgr.run_restore(backup_ref=stored_file)
            assert res["status"] == "success"

            # Verify contents
            conn = sqlite3.connect(target_restore_db)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM products;")
            assert cur.fetchone()[0] == 2
            conn.close()
        finally:
            if os.path.exists(target_restore_db):
                os.unlink(target_restore_db)


def test_manager_encrypted_backup_and_restore(populated_sqlite_db):
    with tempfile.TemporaryDirectory() as storage_dir:
        db_conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=populated_sqlite_db)
        storage_conf = StorageConfig(storage_type=StorageType.LOCAL, local_path=storage_dir)
        passphrase = "SecretMasterPassword!#123"
        options = BackupOptions(
            backup_type=BackupType.FULL,
            compression=CompressionType.GZIP,
            encrypt=True,
            encryption_key=passphrase,
        )

        manager = BackupManager(
            db_config=db_conf,
            storage_config=storage_conf,
            options=options,
        )

        # Run encrypted backup
        meta = manager.run_backup()
        assert meta.is_encrypted is True
        assert meta.filename.endswith(".enc")
        stored_file = meta.storage_locations[0]

        # Restore with password
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            target_restore_db = tf.name

        try:
            restore_mgr = BackupManager(
                db_config=DatabaseConfig(db_type=DatabaseType.SQLITE, database=target_restore_db),
                storage_config=storage_conf,
                options=options,
            )
            res = restore_mgr.run_restore(backup_ref=stored_file, encryption_key=passphrase)
            assert res["status"] == "success"

            conn = sqlite3.connect(target_restore_db)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM products;")
            assert cur.fetchone()[0] == 2
            conn.close()
        finally:
            if os.path.exists(target_restore_db):
                os.unlink(target_restore_db)
