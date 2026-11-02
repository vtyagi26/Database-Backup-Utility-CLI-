from backup_util.constants import DatabaseType
from backup_util.engines.base import BaseEngine
from backup_util.engines.sqlite_engine import SQLiteEngine
from backup_util.engines.mysql_engine import MySQLEngine
from backup_util.engines.postgres_engine import PostgreSQLEngine
from backup_util.engines.mongo_engine import MongoDBEngine
from backup_util.exceptions import EngineNotFoundError
from backup_util.models import DatabaseConfig


def get_engine(config: DatabaseConfig) -> BaseEngine:
    """Factory to return the appropriate DBMS engine."""
    db_type = config.db_type
    if db_type == DatabaseType.SQLITE:
        return SQLiteEngine(config)
    elif db_type == DatabaseType.MYSQL:
        return MySQLEngine(config)
    elif db_type in (DatabaseType.POSTGRESQL, DatabaseType.POSTGRES):
        return PostgreSQLEngine(config)
    elif db_type == DatabaseType.MONGODB:
        return MongoDBEngine(config)
    else:
        raise EngineNotFoundError(f"Unsupported database type: {db_type}")


__all__ = [
    "BaseEngine",
    "SQLiteEngine",
    "MySQLEngine",
    "PostgreSQLEngine",
    "MongoDBEngine",
    "get_engine",
]
