from enum import Enum


class DatabaseType(str, Enum):
    MYSQL = "mysql"
    POSTGRESQL = "postgres"
    POSTGRES = "postgresql"
    MONGODB = "mongodb"
    SQLITE = "sqlite"

    @classmethod
    def normalize(cls, value: str) -> "DatabaseType":
        val = value.lower().strip()
        if val in ("postgres", "postgresql", "pg"):
            return cls.POSTGRESQL
        if val in ("mysql", "mariadb"):
            return cls.MYSQL
        if val in ("mongo", "mongodb"):
            return cls.MONGODB
        if val in ("sqlite", "sqlite3"):
            return cls.SQLITE
        raise ValueError(
            f"Unsupported database type '{value}'. Supported types: mysql, postgres, mongodb, sqlite"
        )


class BackupType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"


class CompressionType(str, Enum):
    NONE = "none"
    GZIP = "gzip"
    BZIP2 = "bzip2"
    ZSTD = "zstd"
    XZ = "xz"
    ZIP = "zip"


class StorageType(str, Enum):
    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"
    AZURE = "azure"


class BackupStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


DEFAULT_PORTS = {
    DatabaseType.MYSQL: 3306,
    DatabaseType.POSTGRESQL: 5432,
    DatabaseType.POSTGRES: 5432,
    DatabaseType.MONGODB: 27017,
    DatabaseType.SQLITE: None,
}

CHUNK_SIZE = 1024 * 64  # 64 KB buffer for streaming I/O
DEFAULT_BACKUP_DIR = "./backups"
DEFAULT_CONFIG_PATH = "./backup_config.yaml"
