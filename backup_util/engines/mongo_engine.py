import io
import json
import os
import shutil
import subprocess
from typing import Any, BinaryIO, Dict, List, Optional

from backup_util.constants import BackupType, CHUNK_SIZE, DEFAULT_PORTS, DatabaseType
from backup_util.engines.base import BaseEngine
from backup_util.exceptions import (
    BackupExecutionError,
    ConnectionFailedError,
    RestoreExecutionError,
)
from backup_util.logger import get_logger
from backup_util.models import BackupMetadata, BackupOptions, DatabaseConfig

logger = get_logger()

try:
    import pymongo
    from bson import json_util
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False


class MongoDBEngine(BaseEngine):
    """MongoDB backup and restore engine."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.port = self.config.port or DEFAULT_PORTS[DatabaseType.MONGODB]

    def _get_client(self) -> "pymongo.MongoClient":
        if not HAS_PYMONGO:
            raise ConnectionFailedError(
                "pymongo is required for MongoDB connectivity.",
                suggestion="Install it with: pip install pymongo",
            )
        try:
            if self.config.uri:
                return pymongo.MongoClient(self.config.uri, serverSelectionTimeoutMS=5000)

            auth_args = {}
            if self.config.username:
                auth_args["username"] = self.config.username
                auth_args["password"] = self.config.password
                auth_args["authSource"] = self.config.auth_source or "admin"

            return pymongo.MongoClient(
                host=self.config.host,
                port=self.port,
                serverSelectionTimeoutMS=5000,
                **auth_args,
            )
        except Exception as e:
            raise ConnectionFailedError(
                f"Failed to create MongoDB client: {e}",
                details=str(e),
                suggestion="Check MongoDB host, port, or URI string.",
            ) from e

    def test_connection(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            client.admin.command("ping")
            server_info = client.server_info()
            db = client[self.config.database]
            collections = db.list_collection_names()

            return {
                "status": "connected",
                "engine": "mongodb",
                "version": server_info.get("version", "unknown"),
                "host": self.config.host,
                "port": self.port,
                "database": self.config.database,
                "collections_count": len(collections),
                "collections": collections,
            }
        except Exception as e:
            raise ConnectionFailedError(
                f"MongoDB connection test failed: {e}",
                details=str(e),
                suggestion="Ensure MongoDB server is running and credentials/authSource are correct.",
            ) from e
        finally:
            client.close()

    def list_tables_or_collections(self) -> List[str]:
        client = self._get_client()
        try:
            db = client[self.config.database]
            return db.list_collection_names()
        finally:
            client.close()

    def backup(
        self,
        output_stream: BinaryIO,
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata] = None,
    ) -> List[str]:
        all_collections = self.list_tables_or_collections()
        cols_to_backup = all_collections

        # Filter out system collections
        cols_to_backup = [c for c in cols_to_backup if not c.startswith("system.")]

        if options.collections or options.tables:
            requested = set(options.collections or options.tables)
            cols_to_backup = [c for c in cols_to_backup if c in requested]
            if not cols_to_backup:
                raise BackupExecutionError(
                    f"None of requested collections {requested} exist in MongoDB database '{self.config.database}'."
                )

        if options.exclude_tables:
            excluded = set(options.exclude_tables)
            cols_to_backup = [c for c in cols_to_backup if c not in excluded]

        mongodump_bin = shutil.which("mongodump")
        if mongodump_bin and not (options.backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL)):
            logger.info("Using native mongodump utility for MongoDB backup...")
            self._backup_with_mongodump(mongodump_bin, output_stream, cols_to_backup)
        else:
            logger.info("Using streaming Python MongoDB engine...")
            self._backup_with_python(output_stream, cols_to_backup, options, parent_metadata)

        return cols_to_backup

    def _backup_with_mongodump(self, mongodump_bin: str, output_stream: BinaryIO, collections: List[str]) -> None:
        cmd = [
            mongodump_bin,
            f"--host={self.config.host}",
            f"--port={self.port}",
            f"--db={self.config.database}",
            "--archive",
        ]
        if self.config.username:
            cmd.extend([
                f"--username={self.config.username}",
                f"--password={self.config.password or ''}",
                f"--authenticationDatabase={self.config.auth_source or 'admin'}",
            ])

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            while True:
                chunk = process.stdout.read(CHUNK_SIZE)
                if not chunk:
                    break
                output_stream.write(chunk)

            process.wait()
            if process.returncode != 0:
                stderr = process.stderr.read().decode("utf-8", errors="replace")
                raise BackupExecutionError(f"mongodump failed with exit code {process.returncode}: {stderr}")
        except Exception as e:
            process.kill()
            raise BackupExecutionError(f"mongodump streaming error: {e}") from e

    def _backup_with_python(
        self,
        output_stream: BinaryIO,
        collections: List[str],
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata],
    ) -> None:
        client = self._get_client()
        db = client[self.config.database]

        try:
            # Header
            manifest = {
                "type": "mongodb_archive",
                "database": self.config.database,
                "backup_type": options.backup_type.value,
                "collections": collections,
            }
            output_stream.write(f"###METADATA###\n{json.dumps(manifest)}\n###END_METADATA###\n".encode("utf-8"))

            for coll_name in collections:
                coll = db[coll_name]
                # Dump index specifications
                indexes = list(coll.list_indexes())
                coll_header = {
                    "collection": coll_name,
                    "indexes": indexes,
                }
                output_stream.write(f"###COLLECTION:{coll_name}###\n".encode("utf-8"))
                output_stream.write(f"{json_util.dumps(coll_header)}\n".encode("utf-8"))

                query = {}
                if options.backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL) and parent_metadata:
                    # Delta query
                    query["$or"] = [
                        {"updatedAt": {"$gt": parent_metadata.start_time}},
                        {"modifiedAt": {"$gt": parent_metadata.start_time}},
                    ]

                # Stream docs
                cursor = coll.find(query)
                for doc in cursor:
                    doc_line = json_util.dumps(doc) + "\n"
                    output_stream.write(doc_line.encode("utf-8"))

                output_stream.write(f"###END_COLLECTION:{coll_name}###\n".encode("utf-8"))

        except Exception as e:
            raise BackupExecutionError(f"MongoDB Python streaming backup failed: {e}") from e
        finally:
            client.close()

    def restore(
        self,
        input_stream: BinaryIO,
        options: BackupOptions,
    ) -> Dict[str, Any]:
        mongorestore_bin = shutil.which("mongorestore")
        # Check archive format
        peek = input_stream.read(100)
        input_stream.seek(0)

        if b"###METADATA###" in peek:
            return self._restore_with_python(input_stream, options)
        elif mongorestore_bin:
            return self._restore_with_mongorestore(mongorestore_bin, input_stream)
        else:
            return self._restore_with_python(input_stream, options)

    def _restore_with_mongorestore(self, mongorestore_bin: str, input_stream: BinaryIO) -> Dict[str, Any]:
        cmd = [
            mongorestore_bin,
            f"--host={self.config.host}",
            f"--port={self.port}",
            f"--nsInclude={self.config.database}.*",
            "--archive",
        ]
        if self.config.username:
            cmd.extend([
                f"--username={self.config.username}",
                f"--password={self.config.password or ''}",
                f"--authenticationDatabase={self.config.auth_source or 'admin'}",
            ])

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            while True:
                chunk = input_stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                process.stdin.write(chunk)
            process.stdin.close()
            process.wait()

            if process.returncode != 0:
                stderr = process.stderr.read().decode("utf-8", errors="replace")
                raise RestoreExecutionError(f"mongorestore failed: {stderr}")

            return {
                "status": "success",
                "engine": "mongodb",
                "database": self.config.database,
                "method": "mongorestore",
            }
        except Exception as e:
            process.kill()
            raise RestoreExecutionError(f"MongoDB mongorestore error: {e}") from e

    def _restore_with_python(self, input_stream: BinaryIO, options: BackupOptions) -> Dict[str, Any]:
        client = self._get_client()
        db = client[self.config.database]
        requested_cols = set(options.collections or options.tables) if (options.collections or options.tables) else None

        restored_cols = set()
        docs_restored = 0

        try:
            content = input_stream.read().decode("utf-8", errors="replace")
            lines = content.splitlines()

            current_collection = None
            batch = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("###COLLECTION:"):
                    current_collection = line.replace("###COLLECTION:", "").replace("###", "")
                    continue
                elif line.startswith("###END_COLLECTION:"):
                    if current_collection and batch:
                        coll = db[current_collection]
                        coll.insert_many(batch)
                        docs_restored += len(batch)
                        batch = []
                    current_collection = None
                    continue
                elif line.startswith("###METADATA###") or line.startswith("###END_METADATA###"):
                    continue

                if not current_collection:
                    continue

                if requested_cols and current_collection not in requested_cols:
                    continue

                restored_cols.add(current_collection)
                try:
                    obj = json_util.loads(line)
                    # If it's the index specification header line
                    if isinstance(obj, dict) and "indexes" in obj and "collection" in obj:
                        coll = db[current_collection]
                        for idx in obj["indexes"]:
                            keys = idx.get("key")
                            name = idx.get("name")
                            if name != "_id_" and keys:
                                key_list = list(keys.items()) if isinstance(keys, dict) else keys
                                try:
                                    coll.create_index(key_list)
                                except Exception:
                                    pass
                        continue

                    batch.append(obj)
                    if len(batch) >= 500:
                        coll = db[current_collection]
                        coll.insert_many(batch)
                        docs_restored += len(batch)
                        batch = []
                except Exception as e:
                    logger.debug(f"MongoDB restore record parse warning: {e}")

            if current_collection and batch:
                coll = db[current_collection]
                coll.insert_many(batch)
                docs_restored += len(batch)

            return {
                "status": "success",
                "engine": "mongodb",
                "database": self.config.database,
                "collections_restored": list(restored_cols),
                "documents_restored": docs_restored,
            }
        except Exception as e:
            raise RestoreExecutionError(f"MongoDB Python restore failed: {e}") from e
        finally:
            client.close()
