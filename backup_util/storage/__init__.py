from backup_util.constants import StorageType
from backup_util.exceptions import ConfigurationError
from backup_util.models import StorageConfig
from backup_util.storage.base import BaseStorage
from backup_util.storage.local import LocalStorage
from backup_util.storage.s3 import S3Storage
from backup_util.storage.gcs import GCSStorage
from backup_util.storage.azure import AzureStorage


def get_storage(config: StorageConfig) -> BaseStorage:
    """Factory to instantiate the appropriate storage backend based on configuration."""
    if config.storage_type == StorageType.LOCAL:
        return LocalStorage(base_dir=config.local_path)
    elif config.storage_type == StorageType.S3:
        return S3Storage(config)
    elif config.storage_type == StorageType.GCS:
        return GCSStorage(config)
    elif config.storage_type == StorageType.AZURE:
        return AzureStorage(config)
    else:
        raise ConfigurationError(f"Unsupported storage type: {config.storage_type}")


__all__ = ["BaseStorage", "LocalStorage", "S3Storage", "GCSStorage", "AzureStorage", "get_storage"]
