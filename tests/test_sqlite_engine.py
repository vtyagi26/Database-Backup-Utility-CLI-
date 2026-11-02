import io
import os
import sqlite3
import tempfile
import pytest

from backup_util.constants import BackupType, CompressionType, DatabaseType
from backup_util.engines.sqlite_engine import SQLiteEngine
from backup_util.models import BackupOptions, DatabaseConfig


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            updated_at TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            updated_at TEXT
        );
    """)
    cur.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', '2026-11-01T10:00:00');")
    cur.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@example.com', '2026-11-01T10:00:00');")
    cur.execute("INSERT INTO orders VALUES (101, 1, 99.95, '2026-11-01T10:00:00');")
    conn.commit()
    conn.close()

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)


def test_sqlite_engine_test_connection(test_db):
    conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=test_db)
    engine = SQLiteEngine(conf)

    info = engine.test_connection()
    assert info["status"] == "connected"
    assert info["tables_count"] == 2
    assert "users" in info["tables"]
    assert "orders" in info["tables"]
    assert info["integrity"] == "ok"


def test_sqlite_full_backup_and_restore(test_db):
    conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=test_db)
    engine = SQLiteEngine(conf)

    # 1. Take full backup into buffer
    buffer = io.BytesIO()
    opts = BackupOptions(backup_type=BackupType.FULL)
    tables = engine.backup(buffer, opts)
    assert set(tables) == {"users", "orders"}

    dump_content = buffer.getvalue()
    assert b"CREATE TABLE users" in dump_content
    assert b"Alice" in dump_content

    # 2. Restore into a brand new database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        target_db_path = f.name
    try:
        target_conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=target_db_path)
        target_engine = SQLiteEngine(target_conf)

        restore_stream = io.BytesIO(dump_content)
        res = target_engine.restore(restore_stream, opts)
        assert res["status"] == "success"

        # Verify data in restored database
        t_conn = sqlite3.connect(target_db_path)
        t_cur = t_conn.cursor()
        t_cur.execute("SELECT count(*) FROM users;")
        assert t_cur.fetchone()[0] == 2
        t_cur.execute("SELECT count(*) FROM orders;")
        assert t_cur.fetchone()[0] == 1
        t_conn.close()

    finally:
        if os.path.exists(target_db_path):
            os.unlink(target_db_path)


def test_sqlite_selective_backup_and_restore(test_db):
    conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=test_db)
    engine = SQLiteEngine(conf)

    # Selective backup: only 'users'
    buffer = io.BytesIO()
    opts = BackupOptions(backup_type=BackupType.FULL, tables=["users"])
    tables = engine.backup(buffer, opts)
    assert tables == ["users"]

    dump_content = buffer.getvalue()
    assert b"users" in dump_content
    assert b"orders" not in dump_content

    # Restore selective into new db
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        target_db_path = f.name
    try:
        target_conf = DatabaseConfig(db_type=DatabaseType.SQLITE, database=target_db_path)
        target_engine = SQLiteEngine(target_conf)

        restore_stream = io.BytesIO(dump_content)
        res = target_engine.restore(restore_stream, opts)
        assert res["status"] == "success"

        t_conn = sqlite3.connect(target_db_path)
        t_cur = t_conn.cursor()
        t_cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        restored_tables = [r[0] for r in t_cur.fetchall()]
        assert "users" in restored_tables
        assert "orders" not in restored_tables
        t_conn.close()
    finally:
        if os.path.exists(target_db_path):
            os.unlink(target_db_path)
