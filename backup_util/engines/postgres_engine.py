import io
import os
import re
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
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class PostgreSQLEngine(BaseEngine):
    """PostgreSQL backup and restore engine."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.port = self.config.port or DEFAULT_PORTS[DatabaseType.POSTGRESQL]

    def _get_connection(self):
        if not HAS_PSYCOPG2:
            raise ConnectionFailedError(
                "psycopg2 is required for PostgreSQL connectivity.",
                suggestion="Install it with: pip install psycopg2-binary",
            )
        try:
            return psycopg2.connect(
                host=self.config.host,
                port=self.port,
                user=self.config.username or "postgres",
                password=self.config.password or "",
                dbname=self.config.database,
                connect_timeout=10,
            )
        except psycopg2.Error as e:
            msg = str(e).strip()
            tip = "Verify PostgreSQL host, port, username, password and database existence."
            if "authentication failed" in msg.lower():
                tip = "PostgreSQL authentication failed. Check username and password."
            elif "does not exist" in msg.lower():
                tip = f"Database '{self.config.database}' does not exist on PostgreSQL server."
            elif "could not connect" in msg.lower():
                tip = f"Cannot reach PostgreSQL server at {self.config.host}:{self.port}. Is the service running?"
            raise ConnectionFailedError(
                f"PostgreSQL connection error: {msg}",
                suggestion=tip,
            ) from e

    def test_connection(self) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0]

                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
                )
                tables = [row[0] for row in cur.fetchall()]

                return {
                    "status": "connected",
                    "engine": "postgres",
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
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
                )
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def backup(
        self,
        output_stream: BinaryIO,
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata] = None,
    ) -> List[str]:
        all_tables = self.list_tables_or_collections()
        tables_to_backup = all_tables

        if options.tables:
            requested = set(options.tables)
            tables_to_backup = [t for t in all_tables if t in requested]
            if not tables_to_backup:
                raise BackupExecutionError(
                    f"None of requested tables {options.tables} exist in PostgreSQL database '{self.config.database}'."
                )

        if options.exclude_tables:
            excluded = set(options.exclude_tables)
            tables_to_backup = [t for t in tables_to_backup if t not in excluded]

        pg_dump_bin = shutil.which("pg_dump")

        if pg_dump_bin:
            logger.info("Using native pg_dump utility for PostgreSQL backup...")
            self._backup_with_pg_dump(pg_dump_bin, output_stream, tables_to_backup)
        else:
            logger.info("pg_dump not found in PATH; using high-performance streaming Python engine...")
            self._backup_with_python(output_stream, tables_to_backup, options, parent_metadata)

        return tables_to_backup

    def _backup_with_pg_dump(self, pg_dump_bin: str, output_stream: BinaryIO, tables: List[str]) -> None:
        cmd = [
            pg_dump_bin,
            "-h", self.config.host,
            "-p", str(self.port),
            "-U", self.config.username or "postgres",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
        ]
        for t in tables:
            cmd.extend(["-t", f"public.{t}"])
        cmd.append(self.config.database)

        env = os.environ.copy()
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

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
                raise BackupExecutionError(f"pg_dump failed with exit code {process.returncode}: {stderr}")
        except Exception as e:
            process.kill()
            raise BackupExecutionError(f"pg_dump streaming error: {e}") from e

    def _backup_with_python(
        self,
        output_stream: BinaryIO,
        tables: List[str],
        options: BackupOptions,
        parent_metadata: Optional[BackupMetadata],
    ) -> None:
        conn = self._get_connection()
        header = (
            f"-- PostgreSQL Backup via Database Backup Utility\n"
            f"-- Database: {self.config.database}\n"
            f"-- Backup Type: {options.backup_type.value}\n\n"
        )
        output_stream.write(header.encode("utf-8"))

        try:
            for table in tables:
                output_stream.write(f"\n-- TABLE: {table}\n".encode("utf-8"))
                output_stream.write(f'DROP TABLE IF EXISTS "{table}" CASCADE;\n'.encode("utf-8"))

                # Extract column definitions
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT column_name, data_type, is_nullable, column_default "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s "
                        "ORDER BY ordinal_position;",
                        (table,),
                    )
                    cols_def = []
                    col_names = []
                    for col_name, data_type, is_nullable, col_default in cur.fetchall():
                        col_names.append(col_name)
                        def_str = f'"{col_name}" {data_type}'
                        if col_default:
                            def_str += f" DEFAULT {col_default}"
                        if is_nullable == "NO":
                            def_str += " NOT NULL"
                        cols_def.append(def_str)

                    create_stmt = f'CREATE TABLE "{table}" (\n  ' + ",\n  ".join(cols_def) + "\n);\n\n"
                    output_stream.write(create_stmt.encode("utf-8"))

                # Stream data using a named server-side cursor
                with conn.cursor(name=f"stream_{table}") as cur:
                    where_clause = ""
                    if options.backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL) and parent_metadata:
                        if "updated_at" in col_names:
                            where_clause = f" WHERE updated_at > '{parent_metadata.start_time}'"
                        elif "modified_at" in col_names:
                            where_clause = f" WHERE modified_at > '{parent_metadata.start_time}'"

                    cur.execute(f'SELECT * FROM "{table}"{where_clause};')
                    escaped_cols = ", ".join(f'"{c}"' for c in col_names)

                    while True:
                        rows = cur.fetchmany(500)
                        if not rows:
                            break
                        batch = []
                        for row in rows:
                            val_strs = []
                            for v in row:
                                if v is None:
                                    val_strs.append("NULL")
                                elif isinstance(v, (int, float)):
                                    val_strs.append(str(v))
                                elif isinstance(v, bool):
                                    val_strs.append("TRUE" if v else "FALSE")
                                else:
                                    escaped = str(v).replace("'", "''")
                                    val_strs.append(f"'{escaped}'")
                            batch.append(f"({', '.join(val_strs)})")

                        stmt = f'INSERT INTO "{table}" ({escaped_cols}) VALUES\n' + ",\n".join(batch) + ";\n"
                        output_stream.write(stmt.encode("utf-8"))
        finally:
            conn.close()

    def restore(
        self,
        input_stream: BinaryIO,
        options: BackupOptions,
    ) -> Dict[str, Any]:
        psql_bin = shutil.which("psql")
        if psql_bin and not options.tables:
            return self._restore_with_psql(psql_bin, input_stream)
        else:
            return self._restore_with_python(input_stream, options)

    def _restore_with_psql(self, psql_bin: str, input_stream: BinaryIO) -> Dict[str, Any]:
        cmd = [
            psql_bin,
            "-h", self.config.host,
            "-p", str(self.port),
            "-U", self.config.username or "postgres",
            "-d", self.config.database,
        ]
        env = os.environ.copy()
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

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
                raise RestoreExecutionError(f"psql restore failed: {stderr}")

            return {
                "status": "success",
                "engine": "postgres",
                "database": self.config.database,
                "method": "psql",
            }
        except Exception as e:
            process.kill()
            raise RestoreExecutionError(f"PostgreSQL native restore error: {e}") from e

    def _restore_with_python(self, input_stream: BinaryIO, options: BackupOptions) -> Dict[str, Any]:
        conn = self._get_connection()
        requested_tables = set(options.tables) if options.tables else None
        restored_tables = set()
        executed_count = 0

        try:
            sql_data = input_stream.read().decode("utf-8", errors="replace")
            statements = [s.strip() for s in sql_data.split(";\n") if s.strip()]

            with conn.cursor() as cur:
                for stmt in statements:
                    tbl_match = re.search(
                        r"(?:TABLE|INTO)\s+[\"']?([a-zA-Z0-9_]+)[\"']?",
                        stmt,
                        re.IGNORECASE,
                    )
                    table_name = tbl_match.group(1) if tbl_match else None

                    if requested_tables and table_name and table_name not in requested_tables:
                        continue

                    try:
                        cur.execute(stmt + ";")
                        executed_count += 1
                        if table_name:
                            restored_tables.add(table_name)
                    except psycopg2.Error as e:
                        logger.debug(f"PostgreSQL restore statement warning: {e}")
                        conn.rollback()
                        continue
                    conn.commit()

            return {
                "status": "success",
                "engine": "postgres",
                "database": self.config.database,
                "statements_executed": executed_count,
                "tables_restored": list(restored_tables),
            }
        finally:
            conn.close()
