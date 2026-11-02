import io
import os
import re
import shutil
import subprocess
from pathlib import Path
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
    import pymysql
    import pymysql.cursors
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False


class MySQLEngine(BaseEngine):
    """MySQL / MariaDB backup and restore engine."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.port = self.config.port or DEFAULT_PORTS[DatabaseType.MYSQL]

    def _get_connection(self, cursorclass=None):
        if not HAS_PYMYSQL:
            raise ConnectionFailedError(
                "pymysql is required for MySQL connectivity.",
                suggestion="Install it with: pip install pymysql",
            )
        try:
            return pymysql.connect(
                host=self.config.host,
                port=self.port,
                user=self.config.username or "root",
                password=self.config.password or "",
                database=self.config.database,
                connect_timeout=10,
                charset="utf8mb4",
                cursorclass=cursorclass or pymysql.cursors.Cursor,
            )
        except pymysql.MySQLError as e:
            error_code, error_msg = (e.args if len(e.args) >= 2 else (0, str(e)))
            tip = "Verify host, port, username, password and database permissions."
            if error_code == 1045:
                tip = "Authentication failed. Check your username and password."
            elif error_code == 1049:
                tip = f"Database '{self.config.database}' does not exist on the server."
            elif error_code == 2003:
                tip = f"Cannot connect to MySQL server at {self.config.host}:{self.port}. Is the server running?"
            raise ConnectionFailedError(
                f"MySQL connection error: {error_msg}",
                details=f"Code: {error_code}",
                suggestion=tip,
            ) from e

    def test_connection(self) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION();")
                version = cursor.fetchone()[0]

                cursor.execute("SHOW TABLES;")
                tables = [row[0] for row in cursor.fetchall()]

                return {
                    "status": "connected",
                    "engine": "mysql",
                    "version": version,
                    "host": self.config.host,
                    "port": self.port,
                    "database": self.config.database,
                    "tables_count": len(tables),
                    "tables": tables,
                }
        finally:
            conn.close()

    def list_tables_or_collections(self) -> List[str]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES;")
                return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def backup(
        self,
        output_stream: BinaryIO,
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata] = None,
    ) -> List[str]:
        # Determine tables to backup
        all_tables = self.list_tables_or_collections()
        tables_to_backup = all_tables

        if options.tables:
            requested = set(options.tables)
            tables_to_backup = [t for t in all_tables if t in requested]
            if not tables_to_backup:
                raise BackupExecutionError(
                    f"None of requested tables {options.tables} exist in database '{self.config.database}'."
                )

        if options.exclude_tables:
            excluded = set(options.exclude_tables)
            tables_to_backup = [t for t in tables_to_backup if t not in excluded]

        # Check if mysqldump CLI is available
        mysqldump_bin = shutil.which("mysqldump")

        if mysqldump_bin:
            logger.info("Using native mysqldump utility for MySQL backup...")
            self._backup_with_mysqldump(mysqldump_bin, output_stream, tables_to_backup)
        else:
            logger.info("mysqldump not found in PATH; using high-performance streaming Python engine...")
            self._backup_with_python(output_stream, tables_to_backup, options, parent_metadata)

        return tables_to_backup

    def _backup_with_mysqldump(self, mysqldump_bin: str, output_stream: BinaryIO, tables: List[str]) -> None:
        cmd = [
            mysqldump_bin,
            f"--host={self.config.host}",
            f"--port={self.port}",
            f"--user={self.config.username or 'root'}",
            "--single-transaction",
            "--quick",
            "--routines",
            "--triggers",
            "--events",
            self.config.database,
        ] + tables

        env = os.environ.copy()
        if self.config.password:
            env["MYSQL_PWD"] = self.config.password

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
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
                raise BackupExecutionError(f"mysqldump failed with exit code {process.returncode}: {stderr}")
        except Exception as e:
            process.kill()
            raise BackupExecutionError(f"mysqldump streaming error: {e}") from e

    def _backup_with_python(
        self,
        output_stream: BinaryIO,
        tables: List[str],
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata],
    ) -> None:
        conn = self._get_connection()
        header = (
            f"-- MySQL Backup via Database Backup Utility\n"
            f"-- Host: {self.config.host}:{self.port} Database: {self.config.database}\n"
            f"-- Backup Type: {options.backup_type.value}\n\n"
            f"SET foreign_key_checks = 0;\n"
            f"SET NAMES utf8mb4;\n\n"
        )
        output_stream.write(header.encode("utf-8"))

        try:
            for table in tables:
                output_stream.write(f"\n-- TABLE: {table}\n".encode("utf-8"))
                output_stream.write(f"DROP TABLE IF EXISTS `{table}`;\n".encode("utf-8"))

                # Get schema
                with conn.cursor() as cur:
                    cur.execute(f"SHOW CREATE TABLE `{table}`;")
                    row = cur.fetchone()
                    if row and len(row) >= 2:
                        create_table_sql = row[1]
                        output_stream.write(f"{create_table_sql};\n\n".encode("utf-8"))

                # Stream rows using server-side cursor to avoid keeping entire dataset in RAM
                ss_conn = self._get_connection(cursorclass=pymysql.cursors.SSCursor)
                try:
                    with ss_conn.cursor() as ss_cur:
                        where_clause = ""
                        if options.backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL) and parent_metadata:
                            with conn.cursor() as cur2:
                                cur2.execute(f"DESCRIBE `{table}`;")
                                cols = [r[0] for r in cur2.fetchall()]
                                if "updated_at" in cols:
                                    where_clause = f" WHERE `updated_at` > '{parent_metadata.start_time}'"
                                elif "modified_at" in cols:
                                    where_clause = f" WHERE `modified_at` > '{parent_metadata.start_time}'"

                        ss_cur.execute(f"SELECT * FROM `{table}`{where_clause};")
                        col_names = [d[0] for d in ss_cur.description] if ss_cur.description else []
                        escaped_cols = ", ".join(f"`{c}`" for c in col_names)

                        batch = []
                        batch_size = 500

                        for row in ss_cur:
                            val_strs = []
                            for v in row:
                                if v is None:
                                    val_strs.append("NULL")
                                elif isinstance(v, (int, float)):
                                    val_strs.append(str(v))
                                elif isinstance(v, bytes):
                                    val_strs.append(f"0x{v.hex()}")
                                else:
                                    escaped = conn.escape_string(str(v))
                                    val_strs.append(f"'{escaped}'")
                            batch.append(f"({', '.join(val_strs)})")

                            if len(batch) >= batch_size:
                                stmt = f"INSERT INTO `{table}` ({escaped_cols}) VALUES\n" + ",\n".join(batch) + ";\n"
                                output_stream.write(stmt.encode("utf-8"))
                                batch = []

                        if batch:
                            stmt = f"INSERT INTO `{table}` ({escaped_cols}) VALUES\n" + ",\n".join(batch) + ";\n"
                            output_stream.write(stmt.encode("utf-8"))
                finally:
                    ss_conn.close()

            output_stream.write(b"\nSET foreign_key_checks = 1;\n")
        finally:
            conn.close()

    def restore(
        self,
        input_stream: BinaryIO,
        options: BackupOptions,
    ) -> Dict[str, Any]:
        mysql_bin = shutil.which("mysql")
        if mysql_bin and not options.tables:
            # Native fast restore
            return self._restore_with_mysql(mysql_bin, input_stream)
        else:
            return self._restore_with_python(input_stream, options)

    def _restore_with_mysql(self, mysql_bin: str, input_stream: BinaryIO) -> Dict[str, Any]:
        cmd = [
            mysql_bin,
            f"--host={self.config.host}",
            f"--port={self.port}",
            f"--user={self.config.username or 'root'}",
            self.config.database,
        ]
        env = os.environ.copy()
        if self.config.password:
            env["MYSQL_PWD"] = self.config.password

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
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
                raise RestoreExecutionError(f"mysql client restore failed: {stderr}")

            return {
                "status": "success",
                "engine": "mysql",
                "database": self.config.database,
                "method": "native_cli",
            }
        except Exception as e:
            process.kill()
            raise RestoreExecutionError(f"MySQL native restore error: {e}") from e

    def _restore_with_python(self, input_stream: BinaryIO, options: BackupOptions) -> Dict[str, Any]:
        conn = self._get_connection()
        requested_tables = set(options.tables) if options.tables else None
        restored_tables = set()
        executed_count = 0

        try:
            sql_data = input_stream.read().decode("utf-8", errors="replace")
            statements = [s.strip() for s in sql_data.split(";\n") if s.strip()]

            with conn.cursor() as cur:
                cur.execute("SET foreign_key_checks = 0;")
                cur.execute("SET NAMES utf8mb4;")

                for stmt in statements:
                    table_name = None
                    tbl_match = re.search(
                        r"(?:TABLE|INTO)\s+[`'\"]?([a-zA-Z0-9_]+)[`'\"]?",
                        stmt,
                        re.IGNORECASE,
                    )
                    if tbl_match:
                        table_name = tbl_match.group(1)

                    if requested_tables and table_name and table_name not in requested_tables:
                        continue

                    try:
                        cur.execute(stmt)
                        executed_count += 1
                        if table_name:
                            restored_tables.add(table_name)
                    except pymysql.MySQLError as e:
                        logger.debug(f"MySQL restore statement warning: {e}")

                cur.execute("SET foreign_key_checks = 1;")
                conn.commit()

            return {
                "status": "success",
                "engine": "mysql",
                "database": self.config.database,
                "statements_executed": executed_count,
                "tables_restored": list(restored_tables),
            }
        finally:
            conn.close()
