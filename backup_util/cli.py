import os
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backup_util import __version__
from backup_util.config import ConfigManager
from backup_util.constants import (
    DEFAULT_CONFIG_PATH,
    BackupType,
    CompressionType,
    DatabaseType,
    StorageType,
)
from backup_util.exceptions import BackupUtilityError, ConnectionFailedError
from backup_util.logger import setup_logger
from backup_util.manager import BackupManager
from backup_util.models import (
    BackupOptions,
    DatabaseConfig,
    NotificationConfig,
    ProfileConfig,
    StorageConfig,
)
from backup_util.scheduler import BackupScheduler

console = Console()
error_console = Console(stderr=True)


def build_manager(
    config_file: str,
    profile_name: Optional[str],
    db_type: Optional[str],
    host: Optional[str],
    port: Optional[int],
    username: Optional[str],
    password: Optional[str],
    database: Optional[str],
    uri: Optional[str],
    storage_type: Optional[str],
    local_path: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: Optional[str],
    s3_region: Optional[str],
    s3_endpoint: Optional[str],
    backup_type: Optional[str],
    compression: Optional[str],
    compression_level: Optional[int],
    encrypt: bool,
    encryption_key: Optional[str],
    tables: Optional[tuple],
    collections: Optional[tuple],
    slack_webhook: Optional[str],
    retention_count: Optional[int],
    retention_days: Optional[int],
) -> BackupManager:
    """Builds a BackupManager by merging profile settings with explicit CLI overrides."""
    cm = None
    profile = None

    if Path(config_file).exists():
        try:
            cm = ConfigManager(config_file)
            if profile_name or cm.default_profile or cm.profiles:
                try:
                    profile = cm.get_profile(profile_name)
                except Exception:
                    if profile_name:
                        raise
        except Exception as e:
            if profile_name:
                raise

    # Base configs from profile or defaults
    if profile:
        db_conf = profile.database.model_copy()
        storage_conf = profile.storage.model_copy()
        notif_conf = profile.notification.model_copy()
        opts = profile.options.model_copy()
    else:
        if not db_type or not database:
            raise click.UsageError(
                "Must provide either a valid --profile from config or both --type and --database / --db."
            )
        db_conf = DatabaseConfig(
            db_type=DatabaseType.normalize(db_type),
            database=database,
        )
        storage_conf = StorageConfig()
        notif_conf = NotificationConfig()
        opts = BackupOptions()

    # CLI Overrides
    if db_type:
        db_conf.db_type = DatabaseType.normalize(db_type)
    if host:
        db_conf.host = host
    if port:
        db_conf.port = port
    if username:
        db_conf.username = username
    if password:
        db_conf.password = password
    if database:
        db_conf.database = database
    if uri:
        db_conf.uri = uri

    if storage_type:
        storage_conf.storage_type = StorageType(storage_type.lower())
    if local_path:
        storage_conf.local_path = local_path
    if s3_bucket:
        storage_conf.s3_bucket = s3_bucket
    if s3_prefix:
        storage_conf.s3_prefix = s3_prefix
    if s3_region:
        storage_conf.s3_region = s3_region
    if s3_endpoint:
        storage_conf.s3_endpoint_url = s3_endpoint

    if backup_type:
        opts.backup_type = BackupType(backup_type.lower())
    if compression:
        opts.compression = CompressionType(compression.lower())
    if compression_level is not None:
        opts.compression_level = compression_level
    if encrypt:
        opts.encrypt = True
    if encryption_key:
        opts.encryption_key = encryption_key
    if tables:
        opts.tables = list(tables)
    if collections:
        opts.collections = list(collections)
    if retention_count is not None:
        opts.retention_count = retention_count
    if retention_days is not None:
        opts.retention_days = retention_days

    if slack_webhook:
        notif_conf.slack_webhook_url = slack_webhook

    return BackupManager(
        db_config=db_conf,
        storage_config=storage_conf,
        options=opts,
        notification_config=notif_conf,
    )


def common_options(f):
    """Decorator to attach common DB and storage parameters to CLI commands."""
    options = [
        click.option("-c", "--config", "config_file", default=DEFAULT_CONFIG_PATH, help="Path to config YAML file.", show_default=True),
        click.option("-p", "--profile", "profile_name", help="Profile name defined in config file."),
        click.option("-t", "--type", "db_type", type=click.Choice(["mysql", "postgres", "mongodb", "sqlite"], case_sensitive=False), help="Database management system type."),
        click.option("-h", "--host", default=None, help="Database server hostname or IP address."),
        click.option("-P", "--port", type=int, default=None, help="Database server port."),
        click.option("-u", "--username", "-U", default=None, help="Database username."),
        click.option("-w", "--password", "-W", default=None, help="Database password (or pass via env vars)."),
        click.option("-d", "--database", "--db", default=None, help="Database name (or SQLite file path)."),
        click.option("--uri", default=None, help="Full database connection URI (e.g. mongodb://... or postgresql://...)."),
        click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logging."),
        click.option("--log-file", default="backups/backup_activity.log", help="Path to file for activity logging."),
    ]
    for opt in reversed(options):
        f = opt(f)
    return f


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(version=__version__, prog_name="Database Backup Utility")
def main():
    """
    [bold cyan]Database Backup Utility[/bold cyan]
    
    A high-performance CLI utility for backing up, compressing, storing,
    scheduling, and restoring MySQL, PostgreSQL, MongoDB, and SQLite databases.
    """
    pass


@main.command("test")
@common_options
def test_cmd(config_file, profile_name, db_type, host, port, username, password, database, uri, verbose, log_file):
    """Validate database connectivity and credentials."""
    setup_logger(log_file=log_file, verbose=verbose)
    try:
        mgr = build_manager(
            config_file=config_file,
            profile_name=profile_name,
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            uri=uri,
            storage_type=None,
            local_path=None,
            s3_bucket=None,
            s3_prefix=None,
            s3_region=None,
            s3_endpoint=None,
            backup_type=None,
            compression=None,
            compression_level=None,
            encrypt=False,
            encryption_key=None,
            tables=None,
            collections=None,
            slack_webhook=None,
            retention_count=None,
            retention_days=None,
        )
        info = mgr.test_connection()

        table = Table(title="[bold green]Database Connection Successful[/bold green]", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        for k, v in info.items():
            if k in ("tables", "collections"):
                table.add_row(k, f"{len(v)} item(s): {', '.join(v[:8])}{'...' if len(v) > 8 else ''}")
            else:
                table.add_row(k, str(v))

        console.print(table)
    except Exception as e:
        error_console.print(Panel(f"[bold red]Connection Test Failed:[/bold red]\n{e}", title="Error", border_style="red"))
        sys.exit(1)


@main.command("backup")
@common_options
@click.option("--backup-type", type=click.Choice(["full", "incremental", "differential"], case_sensitive=False), default="full", help="Backup strategy type.", show_default=True)
@click.option("--compression", type=click.Choice(["gzip", "bzip2", "zstd", "xz", "zip", "none"], case_sensitive=False), default="gzip", help="Compression algorithm.", show_default=True)
@click.option("--compression-level", type=click.IntRange(1, 9), default=6, help="Compression level (1-9).", show_default=True)
@click.option("--storage", "storage_type", type=click.Choice(["local", "s3", "gcs", "azure"], case_sensitive=False), default="local", help="Destination storage target.", show_default=True)
@click.option("--local-path", default="./backups", help="Local directory path for storage.", show_default=True)
@click.option("--s3-bucket", default=None, help="AWS S3 bucket name.")
@click.option("--s3-prefix", default="db-backups", help="S3 key prefix.")
@click.option("--s3-region", default="us-east-1", help="AWS S3 region.")
@click.option("--s3-endpoint", default=None, help="Custom S3 endpoint URL (for MinIO, Wasabi, R2).")
@click.option("--encrypt", is_flag=True, help="Encrypt backup payload using AES-256.")
@click.option("--encryption-key", default=None, help="Passphrase/key for AES-256 encryption.")
@click.option("--table", "tables", multiple=True, help="Specific table to include (can specify multiple).")
@click.option("--collection", "collections", multiple=True, help="Specific collection to include (MongoDB).")
@click.option("--slack-webhook", default=None, help="Slack Incoming Webhook URL for notifications.")
@click.option("--retention-count", type=int, default=None, help="Keep at most N most recent backups.")
@click.option("--retention-days", type=int, default=None, help="Keep backups newer than N days.")
def backup_cmd(
    config_file, profile_name, db_type, host, port, username, password, database, uri, verbose, log_file,
    backup_type, compression, compression_level, storage_type, local_path, s3_bucket, s3_prefix, s3_region,
    s3_endpoint, encrypt, encryption_key, tables, collections, slack_webhook, retention_count, retention_days,
):
    """Execute a database backup operation."""
    setup_logger(log_file=log_file, verbose=verbose)
    try:
        mgr = build_manager(
            config_file=config_file,
            profile_name=profile_name,
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            uri=uri,
            storage_type=storage_type,
            local_path=local_path,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            s3_region=s3_region,
            s3_endpoint=s3_endpoint,
            backup_type=backup_type,
            compression=compression,
            compression_level=compression_level,
            encrypt=encrypt,
            encryption_key=encryption_key,
            tables=tables,
            collections=collections,
            slack_webhook=slack_webhook,
            retention_count=retention_count,
            retention_days=retention_days,
        )

        with console.status("[bold green]Executing backup operation...", spinner="dots"):
            meta = mgr.run_backup()

        table = Table(title="[bold green]Backup Completed Successfully[/bold green]", show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Backup ID", meta.backup_id)
        table.add_row("Database", f"{meta.db_type.upper()} ({meta.database_name})")
        table.add_row("Backup Type", meta.backup_type.value.upper())
        table.add_row("Duration", f"{meta.duration_seconds:.2f}s")
        table.add_row("Uncompressed Size", f"{meta.uncompressed_size_bytes:,} bytes")
        table.add_row("Compressed Size", f"{meta.compressed_size_bytes:,} bytes")
        ratio = (meta.compressed_size_bytes / meta.uncompressed_size_bytes * 100) if meta.uncompressed_size_bytes > 0 else 100
        table.add_row("Compression Ratio", f"{ratio:.1f}% ({meta.compression_algorithm.value})")
        table.add_row("SHA-256 Checksum", meta.checksum_sha256[:20] + "...")
        table.add_row("Encrypted", "Yes (AES-256)" if meta.is_encrypted else "No")
        table.add_row("Destination", "\n".join(meta.storage_locations))

        console.print(table)

    except Exception as e:
        error_console.print(Panel(f"[bold red]Backup Failed:[/bold red]\n{e}", title="Error", border_style="red"))
        sys.exit(1)


@main.command("restore")
@common_options
@click.argument("backup_file")
@click.option("--encryption-key", default=None, help="Passphrase to decrypt backup if encrypted.")
@click.option("--table", "tables", multiple=True, help="Selective restore: specific table(s) to restore.")
@click.option("--collection", "collections", multiple=True, help="Selective restore: specific collection(s) to restore.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def restore_cmd(
    config_file, profile_name, db_type, host, port, username, password, database, uri, verbose, log_file,
    backup_file, encryption_key, tables, collections, yes
):
    """Restore database from a local or remote backup file."""
    setup_logger(log_file=log_file, verbose=verbose)
    try:
        mgr = build_manager(
            config_file=config_file,
            profile_name=profile_name,
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            uri=uri,
            storage_type=None,
            local_path=None,
            s3_bucket=None,
            s3_prefix=None,
            s3_region=None,
            s3_endpoint=None,
            backup_type=None,
            compression=None,
            compression_level=None,
            encrypt=False,
            encryption_key=encryption_key,
            tables=tables,
            collections=collections,
            slack_webhook=None,
            retention_count=None,
            retention_days=None,
        )

        target_desc = f"{mgr.db_config.db_type.upper()} ({mgr.db_config.database})"
        if not yes:
            click.confirm(
                f"[bold yellow]WARNING: Restoring will overwrite existing data in {target_desc}. Continue?[/bold yellow]",
                abort=True,
            )

        with console.status(f"[bold green]Restoring backup into {target_desc}...", spinner="dots"):
            result = mgr.run_restore(
                backup_ref=backup_file,
                encryption_key=encryption_key,
                selective_tables=list(tables) if tables else None,
                selective_collections=list(collections) if collections else None,
            )

        table = Table(title="[bold green]Restore Completed Successfully[/bold green]", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="cyan")
        table.add_column("Detail", style="green")

        for k, v in result.items():
            table.add_row(k, str(v))

        console.print(table)

    except Exception as e:
        error_console.print(Panel(f"[bold red]Restore Failed:[/bold red]\n{e}", title="Error", border_style="red"))
        sys.exit(1)


@main.command("list")
@common_options
@click.option("--storage", "storage_type", type=click.Choice(["local", "s3", "gcs", "azure"], case_sensitive=False), default=None, help="Storage backend to list from.")
@click.option("--local-path", default=None, help="Local directory path.")
@click.option("--s3-bucket", default=None, help="S3 bucket name.")
@click.option("--s3-prefix", default=None, help="S3 prefix.")
def list_cmd(config_file, profile_name, db_type, host, port, username, password, database, uri, verbose, log_file, storage_type, local_path, s3_bucket, s3_prefix):
    """List available backups stored in local or cloud storage."""
    setup_logger(log_file=log_file, verbose=verbose)
    try:
        mgr = build_manager(
            config_file=config_file,
            profile_name=profile_name,
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            uri=uri,
            storage_type=storage_type,
            local_path=local_path,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            s3_region=None,
            s3_endpoint=None,
            backup_type=None,
            compression=None,
            compression_level=None,
            encrypt=False,
            encryption_key=None,
            tables=None,
            collections=None,
            slack_webhook=None,
            retention_count=None,
            retention_days=None,
        )
        backups = mgr.list_backups()

        if not backups:
            console.print("[yellow]No backups found in the specified storage target.[/yellow]")
            return

        table = Table(title=f"Stored Backups ({len(backups)} found)", show_header=True, header_style="bold magenta")
        table.add_column("Name", style="cyan")
        table.add_column("Size", style="green")
        table.add_column("Modified Time", style="yellow")
        table.add_column("Type", style="blue")
        table.add_column("Location", style="dim")

        for b in backups:
            meta = b.get("metadata", {})
            b_type = meta.get("backup_type", "-")
            size_mb = f"{b['size_bytes'] / (1024*1024):.2f} MB" if b['size_bytes'] > 1024*1024 else f"{b['size_bytes'] / 1024:.1f} KB"
            table.add_row(
                b["name"],
                size_mb,
                b["modified_time"][:19].replace("T", " "),
                b_type.upper(),
                b["location"],
            )

        console.print(table)

    except Exception as e:
        error_console.print(Panel(f"[bold red]Failed to list backups:[/bold red]\n{e}", title="Error", border_style="red"))
        sys.exit(1)


@main.command("prune")
@common_options
@click.option("--retention-count", type=int, default=None, help="Keep at most N latest backups.")
@click.option("--retention-days", type=int, default=None, help="Keep backups within N days.")
def prune_cmd(config_file, profile_name, db_type, host, port, username, password, database, uri, verbose, log_file, retention_count, retention_days):
    """Prune older backups based on retention policy."""
    setup_logger(log_file=log_file, verbose=verbose)
    if not retention_count and not retention_days:
        raise click.UsageError("Specify at least --retention-count or --retention-days.")

    try:
        mgr = build_manager(
            config_file=config_file,
            profile_name=profile_name,
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            uri=uri,
            storage_type=None,
            local_path=None,
            s3_bucket=None,
            s3_prefix=None,
            s3_region=None,
            s3_endpoint=None,
            backup_type=None,
            compression=None,
            compression_level=None,
            encrypt=False,
            encryption_key=None,
            tables=None,
            collections=None,
            slack_webhook=None,
            retention_count=retention_count,
            retention_days=retention_days,
        )
        pruned = mgr.prune_backups(count=retention_count, days=retention_days)
        console.print(f"[bold green]Successfully pruned {pruned} older backup(s).[/bold green]")
    except Exception as e:
        error_console.print(Panel(f"[bold red]Prune failed:[/bold red]\n{e}", title="Error", border_style="red"))
        sys.exit(1)


@main.group("schedule")
def schedule_group():
    """Manage automatic backup scheduling and cron tasks."""
    pass


@schedule_group.command("run")
@common_options
@click.option("--minutes", type=int, default=None, help="Run backup every N minutes.")
@click.option("--hours", type=int, default=None, help="Run backup every N hours.")
@click.option("--daily-at", default=None, help="Run backup daily at HH:MM (e.g. 02:30).")
@click.option("--hourly", is_flag=True, help="Run backup every hour.")
@click.option("--run-now", is_flag=True, help="Run a backup immediately on start before schedule.")
def schedule_run(config_file, profile_name, db_type, host, port, username, password, database, uri, verbose, log_file, minutes, hours, daily_at, hourly, run_now):
    """Run recurring backup scheduler daemon."""
    setup_logger(log_file=log_file, verbose=verbose)
    try:
        mgr = build_manager(
            config_file=config_file,
            profile_name=profile_name,
            db_type=db_type,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            uri=uri,
            storage_type=None,
            local_path=None,
            s3_bucket=None,
            s3_prefix=None,
            s3_region=None,
            s3_endpoint=None,
            backup_type=None,
            compression=None,
            compression_level=None,
            encrypt=False,
            encryption_key=None,
            tables=None,
            collections=None,
            slack_webhook=None,
            retention_count=None,
            retention_days=None,
        )

        def task():
            mgr.run_backup(pre_validate=False)

        job_desc = f"{mgr.db_config.db_type.upper()} ({mgr.db_config.database})"
        scheduler = BackupScheduler(backup_task=task, job_name=f"Backup for {job_desc}")
        scheduler.schedule_interval(minutes=minutes, hours=hours, daily_at=daily_at, hourly=hourly)
        scheduler.run_forever(run_immediately=run_now)

    except Exception as e:
        error_console.print(Panel(f"[bold red]Scheduler failed:[/bold red]\n{e}", title="Error", border_style="red"))
        sys.exit(1)


@schedule_group.command("generate-cron")
@click.option("-p", "--profile", required=True, help="Profile name to schedule.")
@click.option("--cron-expr", default="0 2 * * *", help="Cron schedule expression (default: 2:00 AM daily).", show_default=True)
def schedule_cron(profile, cron_expr):
    """Generate crontab syntax for Linux/macOS."""
    cmd = f"db-backup backup -p {profile}"
    cron_str = BackupScheduler.generate_cron_string(cmd, cron_expr)
    console.print(Panel(cron_str, title="Crontab Entry", border_style="green"))


@schedule_group.command("generate-task")
@click.option("-p", "--profile", required=True, help="Profile name to schedule.")
@click.option("--time", "start_time", default="02:00", help="Execution time HH:MM (default: 02:00).", show_default=True)
def schedule_task(profile, start_time):
    """Generate Windows Task Scheduler command."""
    cmd = f"db-backup.exe backup -p {profile}"
    task_str = BackupScheduler.generate_windows_task_command(f"DBBackup_{profile}", cmd, start_time)
    console.print(Panel(task_str, title="Windows Command Prompt (Run as Administrator)", border_style="green"))


@main.group("config")
def config_group():
    """Manage configuration profiles."""
    pass


@config_group.command("init")
@click.option("-o", "--output", default=DEFAULT_CONFIG_PATH, help="Output configuration file path.", show_default=True)
def config_init(output):
    """Generate a template configuration YAML file."""
    if Path(output).exists():
        if not click.confirm(f"File '{output}' already exists. Overwrite?"):
            return
    ConfigManager.create_default_template(output)
    console.print(f"[bold green]Created sample configuration template at '{output}'[/bold green]")


@config_group.command("list")
@click.option("-c", "--config", default=DEFAULT_CONFIG_PATH, help="Path to config file.", show_default=True)
def config_list(config):
    """List profiles defined in configuration file."""
    cm = ConfigManager(config)
    table = Table(title=f"Configuration Profiles in '{config}'", show_header=True, header_style="bold magenta")
    table.add_column("Profile", style="cyan")
    table.add_column("DB Type", style="green")
    table.add_column("Database / Host", style="yellow")
    table.add_column("Storage", style="blue")
    table.add_column("Default", style="bold magenta")

    for name, p in cm.profiles.items():
        is_default = "Yes" if name == cm.default_profile else "No"
        target_str = p.database.database
        if p.database.host:
            target_str = f"{p.database.host}:{p.database.port or ''}/{p.database.database}"
        table.add_row(
            name,
            p.database.db_type.value.upper(),
            target_str,
            p.storage.storage_type.value.upper(),
            is_default,
        )

    console.print(table)


if __name__ == "__main__":
    main()
