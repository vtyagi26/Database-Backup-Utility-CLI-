from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backup_util.constants import (
    BackupStatus,
    BackupType,
    CompressionType,
    DatabaseType,
    StorageType,
)


class DatabaseConfig(BaseModel):
    db_type: DatabaseType
    host: str = "localhost"
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: str
    auth_source: Optional[str] = "admin"
    uri: Optional[str] = None
    extra_options: Dict[str, Any] = Field(default_factory=dict)

    def get_masked_repr(self) -> Dict[str, Any]:
        """Return dict with credentials masked for safe logging/display."""
        data = self.model_dump()
        if data.get("password"):
            data["password"] = "********"
        if data.get("uri") and "@" in data["uri"]:
            parts = data["uri"].split("@")
            prefix = parts[0].split("://")
            scheme = prefix[0]
            data["uri"] = f"{scheme}://***:***@{parts[1]}"
        return data


class StorageConfig(BaseModel):
    storage_type: StorageType = StorageType.LOCAL
    local_path: str = "./backups"
    
    # AWS S3 / MinIO
    s3_bucket: Optional[str] = None
    s3_prefix: str = "db-backups"
    s3_region: str = "us-east-1"
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None

    # Google Cloud Storage
    gcs_bucket: Optional[str] = None
    gcs_project: Optional[str] = None
    gcs_credentials_file: Optional[str] = None

    # Azure Blob Storage
    azure_container: Optional[str] = None
    azure_connection_string: Optional[str] = None


class NotificationConfig(BaseModel):
    slack_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    generic_webhook_url: Optional[str] = None
    notify_on_success: bool = True
    notify_on_failure: bool = True


class BackupOptions(BaseModel):
    backup_type: BackupType = BackupType.FULL
    compression: CompressionType = CompressionType.GZIP
    compression_level: int = 6
    encrypt: bool = False
    encryption_key: Optional[str] = None
    tables: Optional[List[str]] = None
    collections: Optional[List[str]] = None
    exclude_tables: Optional[List[str]] = None
    retention_count: Optional[int] = None
    retention_days: Optional[int] = None


class BackupMetadata(BaseModel):
    backup_id: str
    db_type: str
    database_name: str
    backup_type: BackupType = BackupType.FULL
    parent_backup_id: Optional[str] = None
    base_backup_id: Optional[str] = None
    filename: str
    uncompressed_size_bytes: int = 0
    compressed_size_bytes: int = 0
    checksum_sha256: str = ""
    start_time: str
    end_time: str = ""
    duration_seconds: float = 0.0
    status: BackupStatus = BackupStatus.PENDING
    tables_backed_up: List[str] = Field(default_factory=list)
    compression_algorithm: CompressionType = CompressionType.GZIP
    is_encrypted: bool = False
    storage_locations: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    metadata_extra: Dict[str, Any] = Field(default_factory=dict)


class ProfileConfig(BaseModel):
    name: str
    database: DatabaseConfig
    storage: StorageConfig = Field(default_factory=StorageConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    options: BackupOptions = Field(default_factory=BackupOptions)
