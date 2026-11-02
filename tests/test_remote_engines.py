import io
import pytest

from backup_util.constants import DatabaseType
from backup_util.engines.mongo_engine import MongoDBEngine
from backup_util.engines.mysql_engine import MySQLEngine
from backup_util.engines.postgres_engine import PostgreSQLEngine
from backup_util.exceptions import ConnectionFailedError
from backup_util.models import DatabaseConfig


def test_mysql_engine_connection_failure():
    # Connecting to non-existent port should raise ConnectionFailedError with actionable suggestion
    conf = DatabaseConfig(
        db_type=DatabaseType.MYSQL,
        host="127.0.0.1",
        port=59999,  # Non-listening port
        username="test_user",
        password="bad_password",
        database="non_existent_db",
    )
    engine = MySQLEngine(conf)

    with pytest.raises(ConnectionFailedError) as exc_info:
        engine.test_connection()

    err = exc_info.value
    assert "MySQL connection error" in str(err)
    assert err.suggestion is not None


def test_postgres_engine_connection_failure():
    conf = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        host="127.0.0.1",
        port=59998,
        username="postgres",
        password="bad_password",
        database="non_existent_db",
    )
    engine = PostgreSQLEngine(conf)

    with pytest.raises(ConnectionFailedError) as exc_info:
        engine.test_connection()

    err = exc_info.value
    assert "PostgreSQL connection error" in str(err)
    assert err.suggestion is not None


def test_mongo_engine_connection_failure():
    conf = DatabaseConfig(
        db_type=DatabaseType.MONGODB,
        host="127.0.0.1",
        port=59997,
        database="non_existent_db",
    )
    engine = MongoDBEngine(conf)

    with pytest.raises(ConnectionFailedError) as exc_info:
        engine.test_connection()

    err = exc_info.value
    assert "MongoDB connection test failed" in str(err)
    assert err.suggestion is not None
