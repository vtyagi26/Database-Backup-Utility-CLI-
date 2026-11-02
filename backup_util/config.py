import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from backup_util.constants import (
    DEFAULT_CONFIG_PATH,
    BackupType,
    CompressionType,
    DatabaseType,
    StorageType,
)
from backup_util.exceptions import ConfigurationError
from backup_util.models import (
    BackupOptions,
    DatabaseConfig,
    NotificationConfig,
    ProfileConfig,
    StorageConfig,
)


class ConfigManager:
    """Manages YAML configuration files and named backup profiles."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        self.profiles: Dict[str, ProfileConfig] = {}
        self.default_profile: Optional[str] = None
        if self.config_path.exists():
            self.load()

    def load(self) -> None:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}

            self.default_profile = raw_data.get("default_profile")
            profiles_dict = raw_data.get("profiles", {})

            for name, p_data in profiles_dict.items():
                db_data = p_data.get("database", {})
                if "type" in db_data:
                    db_data["db_type"] = DatabaseType.normalize(db_data.pop("type"))
                elif "db_type" in db_data:
                    db_data["db_type"] = DatabaseType.normalize(db_data["db_type"])

                database = DatabaseConfig(**db_data)

                # Storage
                storage_data = p_data.get("storage", {})
                if "type" in storage_data:
                    storage_data["storage_type"] = StorageType(storage_data.pop("type"))
                storage = StorageConfig(**storage_data)

                # Notification
                notification = NotificationConfig(**p_data.get("notification", {}))

                # Options
                opts_data = p_data.get("options", {})
                if "backup_type" in opts_data:
                    opts_data["backup_type"] = BackupType(opts_data["backup_type"])
                if "compression" in opts_data:
                    opts_data["compression"] = CompressionType(opts_data["compression"])
                options = BackupOptions(**opts_data)

                self.profiles[name] = ProfileConfig(
                    name=name,
                    database=database,
                    storage=storage,
                    notification=notification,
                    options=options,
                )
        except Exception as e:
            raise ConfigurationError(f"Failed to parse config file '{self.config_path}': {e}") from e

    def save(self) -> None:
        raw_data = {
            "default_profile": self.default_profile,
            "profiles": {},
        }
        for name, prof in self.profiles.items():
            raw_data["profiles"][name] = {
                "database": prof.database.model_dump(),
                "storage": prof.storage.model_dump(),
                "notification": prof.notification.model_dump(),
                "options": prof.options.model_dump(),
            }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw_data, f, default_flow_style=False, sort_keys=False)

    def get_profile(self, name: Optional[str] = None) -> ProfileConfig:
        target_name = name or self.default_profile
        if not target_name:
            if len(self.profiles) == 1:
                return next(iter(self.profiles.values()))
            raise ConfigurationError("No profile specified and no default profile configured.")

        if target_name not in self.profiles:
            available = ", ".join(self.profiles.keys()) if self.profiles else "None"
            raise ConfigurationError(
                f"Profile '{target_name}' not found in '{self.config_path}'. Available profiles: {available}"
            )

        return self.profiles[target_name]

    @classmethod
    def create_default_template(cls, output_path: str = DEFAULT_CONFIG_PATH) -> None:
        """Generates a comprehensive sample YAML configuration file."""
        sample_config = {
            "default_profile": "local_sqlite",
            "profiles": {
                "local_sqlite": {
                    "database": {
                        "type": "sqlite",
                        "database": "./data/sample.db",
                    },
                    "storage": {
                        "type": "local",
                        "local_path": "./backups",
                    },
                    "options": {
                        "backup_type": "full",
                        "compression": "gzip",
                        "compression_level": 6,
                    },
                    "notification": {
                        "slack_webhook_url": None,
                    },
                },
                "production_mysql": {
                    "database": {
                        "type": "mysql",
                        "host": "localhost",
                        "port": 3306,
                        "username": "root",
                        "password": "${MYSQL_PASSWORD}",
                        "database": "production_db",
                    },
                    "storage": {
                        "type": "s3",
                        "s3_bucket": "my-company-db-backups",
                        "s3_prefix": "mysql-prod",
                        "s3_region": "us-east-1",
                    },
                    "options": {
                        "backup_type": "full",
                        "compression": "zstd",
                        "compression_level": 3,
                        "retention_count": 14,
                    },
                    "notification": {
                        "slack_webhook_url": "https://hooks.slack.com/services/...",
                        "notify_on_success": True,
                        "notify_on_failure": True,
                    },
                },
                "analytics_postgres": {
                    "database": {
                        "type": "postgres",
                        "host": "localhost",
                        "port": 5432,
                        "username": "postgres",
                        "password": "${PGPASSWORD}",
                        "database": "analytics",
                    },
                    "storage": {
                        "type": "local",
                        "local_path": "./backups/postgres",
                    },
                    "options": {
                        "backup_type": "full",
                        "compression": "gzip",
                    },
                },
                "app_mongo": {
                    "database": {
                        "type": "mongodb",
                        "host": "localhost",
                        "port": 27017,
                        "database": "app_db",
                    },
                    "storage": {
                        "type": "local",
                        "local_path": "./backups/mongodb",
                    },
                    "options": {
                        "backup_type": "full",
                        "compression": "gzip",
                    },
                },
            },
        }

        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(sample_config, f, default_flow_style=False, sort_keys=False)
