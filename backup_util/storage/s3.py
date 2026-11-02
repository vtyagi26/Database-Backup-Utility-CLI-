import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backup_util.exceptions import StorageError
from backup_util.models import BackupMetadata, StorageConfig
from backup_util.storage.base import BaseStorage

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class S3Storage(BaseStorage):
    """AWS S3 / S3-compatible cloud storage backend."""

    def __init__(self, config: StorageConfig):
        if not HAS_BOTO3:
            raise StorageError("boto3 is required for S3 storage. Install it via 'pip install boto3'")

        self.bucket = config.s3_bucket
        if not self.bucket:
            raise StorageError("S3 bucket name is required for S3 storage.")

        self.prefix = config.s3_prefix.strip("/")
        self.region = config.s3_region or "us-east-1"
        self.endpoint_url = config.s3_endpoint_url

        session = boto3.session.Session(
            aws_access_key_id=config.s3_access_key,
            aws_secret_access_key=config.s3_secret_key,
            region_name=self.region,
        )
        self.s3_client = session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            config=Config(signature_version="s3v4"),
        )

    def _get_key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def store(self, src_local_path: str, destination_name: str, metadata: Optional[BackupMetadata] = None) -> str:
        src = Path(src_local_path)
        if not src.exists():
            raise StorageError(f"Source file '{src_local_path}' does not exist.")

        key = self._get_key(destination_name)
        try:
            extra_args = {}
            if metadata:
                # Add custom s3 metadata (string values only)
                extra_args["Metadata"] = {
                    "backup-id": metadata.backup_id,
                    "db-type": metadata.db_type,
                    "checksum-sha256": metadata.checksum_sha256,
                }

            self.s3_client.upload_file(str(src), self.bucket, key, ExtraArgs=extra_args)

            # Store JSON metadata sidecar object
            if metadata:
                meta_key = f"{key}.meta.json"
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=meta_key,
                    Body=json.dumps(metadata.model_dump(), indent=2).encode("utf-8"),
                    ContentType="application/json",
                )

            return f"s3://{self.bucket}/{key}"
        except Exception as e:
            raise StorageError(f"Failed to upload backup to S3 bucket '{self.bucket}': {e}") from e

    def retrieve(self, location: str, dest_local_path: str) -> str:
        key = location
        if key.startswith("s3://"):
            parts = key[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket

        dest = Path(dest_local_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.s3_client.download_file(bucket, key, str(dest))
            return str(dest)
        except Exception as e:
            raise StorageError(f"Failed to download backup from S3 '{location}': {e}") from e

    def list_backups(self) -> List[Dict[str, Any]]:
        backups = []
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".meta.json"):
                        continue

                    backups.append({
                        "name": Path(key).name,
                        "location": f"s3://{self.bucket}/{key}",
                        "size_bytes": obj["Size"],
                        "modified_time": obj["LastModified"].isoformat(),
                    })
        except Exception as e:
            raise StorageError(f"Failed to list backups in S3 bucket '{self.bucket}': {e}") from e

        backups.sort(key=lambda x: x["modified_time"], reverse=True)
        return backups

    def delete(self, location: str) -> bool:
        key = location
        bucket = self.bucket
        if key.startswith("s3://"):
            parts = key[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""

        try:
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            # Try deleting meta sidecar too
            try:
                self.s3_client.delete_object(Bucket=bucket, Key=f"{key}.meta.json")
            except Exception:
                pass
            return True
        except Exception as e:
            raise StorageError(f"Failed to delete S3 object '{location}': {e}") from e

    def cleanup_retention(self, retention_count: Optional[int] = None, retention_days: Optional[int] = None) -> int:
        backups = self.list_backups()
        deleted_count = 0
        now = datetime.now()

        if retention_count is not None and retention_count > 0:
            if len(backups) > retention_count:
                for b in backups[retention_count:]:
                    if self.delete(b["location"]):
                        deleted_count += 1

        return deleted_count
