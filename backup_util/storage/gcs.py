import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backup_util.exceptions import StorageError
from backup_util.models import BackupMetadata, StorageConfig
from backup_util.storage.base import BaseStorage

try:
    from google.cloud import storage as gcs_lib
    HAS_GCS = True
except ImportError:
    HAS_GCS = False


class GCSStorage(BaseStorage):
    """Google Cloud Storage backend."""

    def __init__(self, config: StorageConfig):
        if not HAS_GCS:
            raise StorageError(
                "google-cloud-storage is required for GCS. Install it via 'pip install google-cloud-storage'"
            )
        self.bucket_name = config.gcs_bucket
        if not self.bucket_name:
            raise StorageError("GCS bucket name is required for GCS storage.")

        if config.gcs_credentials_file:
            self.client = gcs_lib.Client.from_service_account_json(
                config.gcs_credentials_file, project=config.gcs_project
            )
        else:
            self.client = gcs_lib.Client(project=config.gcs_project)

        self.bucket = self.client.bucket(self.bucket_name)

    def store(self, src_local_path: str, destination_name: str, metadata: Optional[BackupMetadata] = None) -> str:
        src = Path(src_local_path)
        if not src.exists():
            raise StorageError(f"Source file '{src_local_path}' does not exist.")

        try:
            blob = self.bucket.blob(destination_name)
            blob.upload_from_filename(str(src))

            if metadata:
                meta_blob = self.bucket.blob(f"{destination_name}.meta.json")
                meta_blob.upload_from_string(
                    json.dumps(metadata.model_dump(), indent=2),
                    content_type="application/json",
                )

            return f"gs://{self.bucket_name}/{destination_name}"
        except Exception as e:
            raise StorageError(f"Failed to upload backup to GCS '{destination_name}': {e}") from e

    def retrieve(self, location: str, dest_local_path: str) -> str:
        name = location.replace(f"gs://{self.bucket_name}/", "")
        dest = Path(dest_local_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            blob = self.bucket.blob(name)
            blob.download_to_filename(str(dest))
            return str(dest)
        except Exception as e:
            raise StorageError(f"Failed to download backup from GCS '{location}': {e}") from e

    def list_backups(self) -> List[Dict[str, Any]]:
        backups = []
        try:
            for blob in self.client.list_blobs(self.bucket_name):
                if blob.name.endswith(".meta.json"):
                    continue
                backups.append({
                    "name": Path(blob.name).name,
                    "location": f"gs://{self.bucket_name}/{blob.name}",
                    "size_bytes": blob.size,
                    "modified_time": blob.updated.isoformat() if blob.updated else "",
                })
        except Exception as e:
            raise StorageError(f"Failed to list GCS backups: {e}") from e

        backups.sort(key=lambda x: x["modified_time"], reverse=True)
        return backups

    def delete(self, location: str) -> bool:
        name = location.replace(f"gs://{self.bucket_name}/", "")
        try:
            blob = self.bucket.blob(name)
            blob.delete()
            return True
        except Exception as e:
            raise StorageError(f"Failed to delete GCS blob '{location}': {e}") from e

    def cleanup_retention(self, retention_count: Optional[int] = None, retention_days: Optional[int] = None) -> int:
        backups = self.list_backups()
        deleted = 0
        if retention_count and len(backups) > retention_count:
            for b in backups[retention_count:]:
                if self.delete(b["location"]):
                    deleted += 1
        return deleted
