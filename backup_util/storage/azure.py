import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backup_util.exceptions import StorageError
from backup_util.models import BackupMetadata, StorageConfig
from backup_util.storage.base import BaseStorage

try:
    from azure.storage.blob import BlobServiceClient
    HAS_AZURE = True
except ImportError:
    HAS_AZURE = False


class AzureStorage(BaseStorage):
    """Azure Blob Storage backend."""

    def __init__(self, config: StorageConfig):
        if not HAS_AZURE:
            raise StorageError(
                "azure-storage-blob is required for Azure storage. Install it via 'pip install azure-storage-blob'"
            )
        if not config.azure_connection_string:
            raise StorageError("azure_connection_string is required for Azure storage.")
        if not config.azure_container:
            raise StorageError("azure_container name is required for Azure storage.")

        self.container_name = config.azure_container
        self.blob_service = BlobServiceClient.from_connection_string(config.azure_connection_string)
        self.container_client = self.blob_service.get_container_client(self.container_name)

    def store(self, src_local_path: str, destination_name: str, metadata: Optional[BackupMetadata] = None) -> str:
        src = Path(src_local_path)
        if not src.exists():
            raise StorageError(f"Source file '{src_local_path}' does not exist.")

        try:
            blob_client = self.container_client.get_blob_client(destination_name)
            with open(src, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)

            if metadata:
                meta_blob = self.container_client.get_blob_client(f"{destination_name}.meta.json")
                meta_blob.upload_blob(
                    json.dumps(metadata.model_dump(), indent=2).encode("utf-8"),
                    overwrite=True,
                )

            return f"azure://{self.container_name}/{destination_name}"
        except Exception as e:
            raise StorageError(f"Failed to upload backup to Azure Blob '{destination_name}': {e}") from e

    def retrieve(self, location: str, dest_local_path: str) -> str:
        name = location.replace(f"azure://{self.container_name}/", "")
        dest = Path(dest_local_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            blob_client = self.container_client.get_blob_client(name)
            with open(dest, "wb") as f:
                download_stream = blob_client.download_blob()
                f.write(download_stream.readall())
            return str(dest)
        except Exception as e:
            raise StorageError(f"Failed to download backup from Azure Blob '{location}': {e}") from e

    def list_backups(self) -> List[Dict[str, Any]]:
        backups = []
        try:
            for blob in self.container_client.list_blobs():
                if blob.name.endswith(".meta.json"):
                    continue
                backups.append({
                    "name": Path(blob.name).name,
                    "location": f"azure://{self.container_name}/{blob.name}",
                    "size_bytes": blob.size,
                    "modified_time": blob.last_modified.isoformat() if blob.last_modified else "",
                })
        except Exception as e:
            raise StorageError(f"Failed to list Azure backups: {e}") from e

        backups.sort(key=lambda x: x["modified_time"], reverse=True)
        return backups

    def delete(self, location: str) -> bool:
        name = location.replace(f"azure://{self.container_name}/", "")
        try:
            blob_client = self.container_client.get_blob_client(name)
            blob_client.delete_blob()
            return True
        except Exception as e:
            raise StorageError(f"Failed to delete Azure blob '{location}': {e}") from e

    def cleanup_retention(self, retention_count: Optional[int] = None, retention_days: Optional[int] = None) -> int:
        backups = self.list_backups()
        deleted = 0
        if retention_count and len(backups) > retention_count:
            for b in backups[retention_count:]:
                if self.delete(b["location"]):
                    deleted += 1
        return deleted
