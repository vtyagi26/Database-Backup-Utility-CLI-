import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backup_util.compression.compressor import Compressor
from backup_util.constants import BackupStatus, BackupType, CompressionType, DatabaseType
from backup_util.crypto.encryptor import BackupEncryptor
from backup_util.engines import get_engine
from backup_util.exceptions import (
    BackupExecutionError,
    IntegrityError,
    RestoreExecutionError,
)
from backup_util.logger import get_logger
from backup_util.models import (
    BackupMetadata,
    BackupOptions,
    DatabaseConfig,
    NotificationConfig,
    ProfileConfig,
    StorageConfig,
)
from backup_util.notification import NotificationDispatcher
from backup_util.storage import get_storage

logger = get_logger()


class BackupManager:
    """Coordinates backup, restore, compression, encryption, storage, and notifications."""

    def __init__(
        self,
        db_config: DatabaseConfig,
        storage_config: StorageConfig,
        options: BackupOptions,
        notification_config: Optional[NotificationConfig] = None,
    ):
        self.db_config = db_config
        self.storage_config = storage_config
        self.options = options
        self.notification_config = notification_config or NotificationConfig()

        self.engine = get_engine(self.db_config)
        self.storage = get_storage(self.storage_config)
        self.notifier = NotificationDispatcher(self.notification_config)

    @classmethod
    def from_profile(cls, profile: ProfileConfig) -> "BackupManager":
        return cls(
            db_config=profile.database,
            storage_config=profile.storage,
            options=profile.options,
            notification_config=profile.notification,
        )

    def test_connection(self) -> Dict[str, Any]:
        """Validates database credentials and connectivity."""
        logger.info(f"Testing connection to {self.db_config.db_type.upper()} ({self.db_config.database})...")
        info = self.engine.test_connection()
        logger.info(f"Connection test successful: {info.get('version', '')}")
        return info

    def run_backup(
        self,
        pre_validate: bool = True,
        parent_metadata: Optional[BackupMetadata] = None,
    ) -> BackupMetadata:
        """Executes a full, incremental, or differential backup operation."""
        start_time_dt = datetime.now()
        start_time_iso = start_time_dt.isoformat()
        t0 = time.time()

        clean_db_name = Path(self.db_config.database).stem if self.db_config.db_type == DatabaseType.SQLITE else self.db_config.database
        backup_id = f"{clean_db_name}_{self.options.backup_type.value}_{start_time_dt.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        logger.info(f"Starting backup operation [ID: {backup_id}] for {self.db_config.db_type.upper()} database '{clean_db_name}'...")

        metadata = BackupMetadata(
            backup_id=backup_id,
            db_type=self.db_config.db_type.value,
            database_name=clean_db_name,
            backup_type=self.options.backup_type,
            parent_backup_id=parent_metadata.backup_id if parent_metadata else None,
            filename="",
            start_time=start_time_iso,
            status=BackupStatus.RUNNING,
            compression_algorithm=self.options.compression,
            is_encrypted=self.options.encrypt,
        )

        temp_dir = tempfile.mkdtemp(prefix="db_backup_")

        try:
            if pre_validate:
                self.test_connection()

            # 1. Dump database to intermediate staging file
            raw_ext = ".archive" if self.db_config.db_type == DatabaseType.MONGODB else ".sql"
            raw_path = os.path.join(temp_dir, f"raw_{backup_id}{raw_ext}")

            logger.info("Dumping database schema and data...")
            with open(raw_path, "wb") as raw_file:
                backed_up_tables = self.engine.backup(raw_file, self.options, parent_metadata)
            metadata.tables_backed_up = backed_up_tables

            # 2. Compress the dump
            comp_ext = Compressor.get_extension(self.options.compression)
            compressed_path = os.path.join(temp_dir, f"{backup_id}{raw_ext}{comp_ext}")

            logger.info(f"Compressing backup using {self.options.compression.upper()} (level {self.options.compression_level})...")
            uncomp_size, comp_size, checksum = Compressor.compress_file(
                raw_path,
                compressed_path,
                algorithm=self.options.compression,
                level=self.options.compression_level,
            )

            metadata.uncompressed_size_bytes = uncomp_size
            metadata.compressed_size_bytes = comp_size
            metadata.checksum_sha256 = checksum

            final_file_to_store = compressed_path
            final_filename = f"{backup_id}{raw_ext}{comp_ext}"

            # 3. Optional AES-256 Encryption
            if self.options.encrypt:
                if not self.options.encryption_key:
                    raise BackupExecutionError("Encryption enabled but no encryption_key provided.")
                logger.info("Encrypting backup file with AES-256...")
                enc_path = os.path.join(temp_dir, f"{final_filename}.enc")
                BackupEncryptor.encrypt_file(compressed_path, enc_path, self.options.encryption_key)
                final_file_to_store = enc_path
                final_filename = f"{final_filename}.enc"
                metadata.compressed_size_bytes = os.path.getsize(enc_path)

            metadata.filename = final_filename

            # 4. Store in storage backend (local / S3 / GCS / Azure)
            logger.info(f"Storing backup to {self.storage_config.storage_type.upper()} storage...")
            stored_location = self.storage.store(final_file_to_store, final_filename, metadata)
            metadata.storage_locations.append(stored_location)

            # 5. Cleanup retention
            if self.options.retention_count or self.options.retention_days:
                pruned = self.storage.cleanup_retention(
                    retention_count=self.options.retention_count,
                    retention_days=self.options.retention_days,
                )
                if pruned > 0:
                    logger.info(f"Retention policy pruned {pruned} older backup(s).")

            # Finalize status
            duration = time.time() - t0
            metadata.status = BackupStatus.COMPLETED
            metadata.end_time = datetime.now().isoformat()
            metadata.duration_seconds = duration

            logger.info(
                f"[bold green]Backup completed successfully![/bold green] "
                f"ID: {backup_id} | Size: {comp_size:,} bytes | Time: {duration:.2f}s | Location: {stored_location}"
            )

            # Dispatch notification
            self.notifier.dispatch(metadata)

            return metadata

        except Exception as e:
            duration = time.time() - t0
            metadata.status = BackupStatus.FAILED
            metadata.end_time = datetime.now().isoformat()
            metadata.duration_seconds = duration
            metadata.error_message = str(e)

            logger.error(f"[bold red]Backup failed after {duration:.2f}s: {e}[/bold red]")
            self.notifier.dispatch(metadata, error=e)
            raise

        finally:
            # Clean up temporary staging directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    def run_restore(
        self,
        backup_ref: str,
        encryption_key: Optional[str] = None,
        selective_tables: Optional[List[str]] = None,
        selective_collections: Optional[List[str]] = None,
        verify_checksum: bool = True,
    ) -> Dict[str, Any]:
        """Restores a database from a backup file (local or remote)."""
        logger.info(f"Starting restore operation from '{backup_ref}'...")
        temp_dir = tempfile.mkdtemp(prefix="db_restore_")

        try:
            # 1. Retrieve the file to staging area
            local_staged = os.path.join(temp_dir, Path(backup_ref).name)
            self.storage.retrieve(backup_ref, local_staged)

            current_file = local_staged

            # 2. Decrypt if needed
            if current_file.endswith(".enc"):
                key = encryption_key or self.options.encryption_key
                if not key:
                    raise RestoreExecutionError("Backup is encrypted (.enc) but no encryption key was provided.")
                logger.info("Decrypting backup file...")
                decrypted_path = current_file[:-4]
                BackupEncryptor.decrypt_file(current_file, decrypted_path, key)
                current_file = decrypted_path

            # 3. Detect compression and decompress
            comp_type = Compressor.detect_compression(current_file)
            uncompressed_path = os.path.join(temp_dir, "uncompressed_payload")

            logger.info(f"Decompressing backup ({comp_type.value})...")
            uncomp_bytes, computed_hash = Compressor.decompress_file(
                current_file, uncompressed_path, algorithm=comp_type
            )

            # 4. Restore options
            restore_opts = self.options.model_copy()
            if selective_tables:
                restore_opts.tables = selective_tables
            if selective_collections:
                restore_opts.collections = selective_collections

            logger.info(f"Restoring payload into {self.db_config.db_type.upper()} ({self.db_config.database})...")
            with open(uncompressed_path, "rb") as stream:
                result = self.engine.restore(stream, restore_opts)

            result["uncompressed_size_bytes"] = uncomp_bytes
            result["checksum_sha256"] = computed_hash
            logger.info(f"[bold green]Restore completed successfully![/bold green] Details: {result}")
            return result

        except Exception as e:
            logger.error(f"[bold red]Restore operation failed: {e}[/bold red]")
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all backups in the storage backend."""
        return self.storage.list_backups()

    def prune_backups(self, count: Optional[int] = None, days: Optional[int] = None) -> int:
        """Manually trigger retention pruning."""
        return self.storage.cleanup_retention(retention_count=count, retention_days=days)
