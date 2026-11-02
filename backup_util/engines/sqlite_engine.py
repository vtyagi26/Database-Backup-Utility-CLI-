import io
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

from backup_util.constants import BackupType, CHUNK_SIZE
from backup_util.engines.base import BaseEngine
from backup_util.exceptions import (
    BackupExecutionError,
    ConnectionFailedError,
    RestoreExecutionError,
)
from backup_util.logger import get_logger
from backup_util.models import BackupMetadata, BackupOptions, DatabaseConfig

logger = get_logger()


class SQLiteEngine(BaseEngine):
    """SQLite backup and restore engine."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.db_path = Path(self.config.database).resolve()

    def _get_connection(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise ConnectionFailedError(
                f"Failed to connect to SQLite database at '{self.db_path}'",
                details=str(e),
                suggestion="Verify that the file path exists and has appropriate read/write permissions.",
            ) from e

    def test_connection(self) -> Dict[str, Any]:
        if not self.db_path.exists():
            raise ConnectionFailedError(
                f"SQLite database file not found at '{self.db_path}'",
                suggestion="Check the file path in your configuration or command arguments.",
            )

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            integrity_result = cursor.fetchone()[0]

            cursor.execute("SELECT sqlite_version();")
            version = cursor.fetchone()[0]

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row[0] for row in cursor.fetchall()]

            file_size = self.db_path.stat().st_size
            conn.close()

            if integrity_result.lower() != "ok":
                raise ConnectionFailedError(
                    f"SQLite database integrity check failed: {integrity_result}"
                )

            return {
                "status": "connected",
                "engine": "sqlite",
                "version": version,
                "file_path": str(self.db_path),
                "file_size_bytes": file_size,
                "tables_count": len(tables),
                "tables": tables,
                "integrity": integrity_result,
            }
        except ConnectionFailedError:
            raise
        except Exception as e:
            raise ConnectionFailedError(
                f"SQLite connection test failed: {e}",
                details=str(e),
            ) from e

    def list_tables_or_collections(self) -> List[str]:
        if not self.db_path.exists():
            return []
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def backup(
        self,
        output_stream: BinaryIO,
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata] = None,
    ) -> List[str]:
        if not self.db_path.exists():
            raise BackupExecutionError(f"SQLite database file '{self.db_path}' does not exist.")

        conn = self._get_connection()
        tables_to_backup = self.list_tables_or_collections()

        if options.tables:
            requested = set(options.tables)
            tables_to_backup = [t for t in tables_to_backup if t in requested]
            if not tables_to_backup:
                raise BackupExecutionError(
                    f"None of the requested tables {options.tables} were found in the database."
                )

        if options.exclude_tables:
            excluded = set(options.exclude_tables)
            tables_to_backup = [t for t in tables_to_backup if t not in excluded]

        try:
            # We produce a structured SQL script format with header and table delimiters
            header = (
                f"-- SQLite Backup\n"
                f"-- Database: {self.db_path.name}\n"
                f"-- Backup Type: {options.backup_type.value}\n"
                f"-- Tables: {', '.join(tables_to_backup)}\n\n"
                f"PRAGMA foreign_keys=OFF;\n"
                f"BEGIN TRANSACTION;\n\n"
            )
            output_stream.write(header.encode("utf-8"))

            cursor = conn.cursor()

            for table in tables_to_backup:
                output_stream.write(f"\n-- TABLE: {table}\n".encode("utf-8"))
                # Get table DDL
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?;",
                    (table,),
                )
                ddl_row = cursor.fetchone()
                if ddl_row and ddl_row[0]:
                    output_stream.write(f"{ddl_row[0]};\n".encode("utf-8"))

                # Get indexes
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = ? AND sql IS NOT NULL;",
                    (table,),
                )
                for idx_row in cursor.fetchall():
                    output_stream.write(f"{idx_row[0]};\n".encode("utf-8"))

                # Check if incremental/differential with timestamp or rowid cutoff
                where_clause = ""
                params = ()
                if options.backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL) and parent_metadata:
                    last_backup_time = parent_metadata.start_time
                    # Try to see if table has updated_at or modified_at column
                    cursor.execute(f"PRAGMA table_info({table});")
                    columns = [row[1] for row in cursor.fetchall()]
                    if "updated_at" in columns:
                        where_clause = " WHERE updated_at > ?"
                        params = (last_backup_time,)
                    elif "modified_at" in columns:
                        where_clause = " WHERE modified_at > ?"
                        params = (last_backup_time,)

                # Dump rows in chunks
                query = f"SELECT * FROM \"{table}\"{where_clause};"
                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                col_names = ", ".join(f'"{c}"' for c in columns)

                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    for row in rows:
                        values = []
                        for val in row:
                            if val is None:
                                values.append("NULL")
                            elif isinstance(val, (int, float)):
                                values.append(str(val))
                            elif isinstance(val, bytes):
                                values.append(f"X'{val.hex()}'")
                            else:
                                escaped = str(val).replace("'", "''")
                                values.append(f"'{escaped}'")
                        val_str = ", ".join(values)
                        line = f"INSERT INTO \"{table}\" ({col_names}) VALUES ({val_str});\n"
                        output_stream.write(line.encode("utf-8"))

            output_stream.write(b"\nCOMMIT;\nPRAGMA foreign_keys=ON;\n")
            return tables_to_backup

        except Exception as e:
            raise BackupExecutionError(f"Failed to create SQLite backup: {e}") from e
        finally:
            conn.close()

    def restore(
        self,
        input_stream: BinaryIO,
        options: BackupOptions,
    ) -> Dict[str, Any]:
        """Restores database from an SQL dump stream, supporting selective table restore."""
        # Ensure target directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        sql_content = input_stream.read().decode("utf-8", errors="replace")

        # Check if selective restore requested
        requested_tables = set(options.tables) if options.tables else None

        conn = self._get_connection()
        cursor = conn.cursor()
        tables_restored = set()
        executed_statements = 0

        try:
            cursor.execute("PRAGMA foreign_keys=OFF;")
            cursor.execute("BEGIN TRANSACTION;")

            # Split statements cleanly
            statements = [s.strip() for s in sql_content.split(";") if s.strip()]

            current_table = None
            for stmt in statements:
                # Check for table header hint
                table_match = re.search(r"-- TABLE:\s*([^\s\n\r]+)", stmt)
                if table_match:
                    current_table = table_match.group(1).strip()

                # If no header comment in stmt, check CREATE TABLE or INSERT INTO
                if not current_table:
                    tbl_match = re.search(
                        r"(?:CREATE\s+TABLE|INSERT\s+INTO)\s+[\"']?([a-zA-Z0-9_]+)[\"']?",
                        stmt,
                        re.IGNORECASE,
                    )
                    if tbl_match:
                        current_table = tbl_match.group(1)

                # Filter by selective tables if requested
                if requested_tables and current_table and current_table not in requested_tables:
                    continue

                if stmt.upper().startswith("BEGIN") or stmt.upper().startswith("COMMIT"):
                    continue

                try:
                    cursor.execute(stmt + ";")
                    executed_statements += 1
                    if current_table:
                        tables_restored.add(current_table)
                except sqlite3.Error as e:
                    # Ignore harmless drops or already exists if not strict
                    logger.debug(f"SQLite restore statement warning: {e} in stmt: {stmt[:60]}")

            conn.commit()
            cursor.execute("PRAGMA foreign_keys=ON;")

            return {
                "status": "success",
                "engine": "sqlite",
                "database": str(self.db_path),
                "statements_executed": executed_statements,
                "tables_restored": list(tables_restored),
            }
        except Exception as e:
            conn.rollback()
            raise RestoreExecutionError(f"Failed to restore SQLite database: {e}") from e
        finally:
            conn.close()
