import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backup_util.exceptions import StorageError
from backup_util.models import BackupMetadata
from backup_util.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: str = "./backups"):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, src_local_path: str, destination_name: str, metadata: Optional[BackupMetadata] = None) -> str:
        src = Path(src_local_path)
        if not src.exists():
            raise StorageError(f"Source file '{src_local_path}' does not exist.")

        dest = self.base_dir / destination_name
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            # If src and dest are the same file, avoid copying
            if src.resolve() != dest.resolve():
                shutil.copy2(str(src), str(dest))

            # Store metadata alongside the backup file if provided
            if metadata:
                meta_path = dest.with_suffix(dest.suffix + ".meta.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(metadata.model_dump(), f, indent=2)

            return str(dest)
        except Exception as e:
            raise StorageError(f"Failed to store backup locally at '{dest}': {e}") from e

    def retrieve(self, location: str, dest_local_path: str) -> str:
        src = Path(location)
        if not src.is_absolute():
            src = self.base_dir / location

        if not src.exists():
            raise StorageError(f"Local backup file '{src}' not found.")

        dest = Path(dest_local_path).resolve()
        if src.resolve() == dest.resolve():
            return str(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(src), str(dest))
            return str(dest)
        except Exception as e:
            raise StorageError(f"Failed to retrieve local backup from '{src}': {e}") from e

    def list_backups(self) -> List[Dict[str, Any]]:
        backups = []
        if not self.base_dir.exists():
            return backups

        for item in self.base_dir.glob("*"):
            if item.is_file() and not item.name.endswith(".meta.json") and not item.name.endswith(".log"):
                meta_path = item.with_suffix(item.suffix + ".meta.json")
                meta = {}
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                    except Exception:
                        pass

                stat = item.stat()
                backups.append({
                    "name": item.name,
                    "location": str(item),
                    "size_bytes": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "metadata": meta,
                })

        # Sort newest first
        backups.sort(key=lambda x: x["modified_time"], reverse=True)
        return backups

    def delete(self, location: str) -> bool:
        target = Path(location)
        if not target.is_absolute():
            target = self.base_dir / location

        deleted = False
        if target.exists():
            target.unlink()
            deleted = True

        meta_path = target.with_suffix(target.suffix + ".meta.json")
        if meta_path.exists():
            meta_path.unlink()

        return deleted

    def cleanup_retention(self, retention_count: Optional[int] = None, retention_days: Optional[int] = None) -> int:
        backups = self.list_backups()
        deleted_count = 0
        now = time.time()

        # Delete by age
        if retention_days is not None and retention_days > 0:
            cutoff = now - (retention_days * 86400)
            for b in list(backups):
                path = Path(b["location"])
                if path.exists() and path.stat().st_mtime < cutoff:
                    if self.delete(b["location"]):
                        deleted_count += 1
                        backups.remove(b)

        # Delete by count
        if retention_count is not None and retention_count > 0:
            if len(backups) > retention_count:
                for b in backups[retention_count:]:
                    if self.delete(b["location"]):
                        deleted_count += 1

        return deleted_count
