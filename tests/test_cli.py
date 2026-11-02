import os
import sqlite3
import tempfile
import pytest
from click.testing import CliRunner

from backup_util.cli import main


@pytest.fixture
def sqlite_sample():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE items (id INT, name TEXT);")
    cur.execute("INSERT INTO items VALUES (1, 'Item A');")
    conn.commit()
    conn.close()
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "Database Backup Utility" in result.output


def test_cli_test_connection(sqlite_sample):
    runner = CliRunner()
    result = runner.invoke(main, [
        "test",
        "--type", "sqlite",
        "--database", sqlite_sample,
    ])
    assert result.exit_code == 0
    assert "Database Connection Successful" in result.output


def test_cli_backup_and_list_and_restore(sqlite_sample):
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as storage_dir:
        # Run backup
        result = runner.invoke(main, [
            "backup",
            "--type", "sqlite",
            "--database", sqlite_sample,
            "--storage", "local",
            "--local-path", storage_dir,
            "--compression", "gzip",
        ])
        assert result.exit_code == 0
        assert "Backup Completed Successfully" in result.output

        # List backups
        list_result = runner.invoke(main, [
            "list",
            "--storage", "local",
            "--local-path", storage_dir,
            "--type", "sqlite",
            "--database", sqlite_sample,
        ])
        assert list_result.exit_code == 0
        assert "Stored Backups" in list_result.output

        # Restore into a new sqlite file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            target_db = tf.name

        try:
            # Get the generated backup file path from storage_dir
            files = [os.path.join(storage_dir, f) for f in os.listdir(storage_dir) if f.endswith(".sql.gz")]
            assert len(files) == 1
            backup_file = files[0]

            restore_result = runner.invoke(main, [
                "restore",
                "--type", "sqlite",
                "--database", target_db,
                "--yes",
                backup_file,
            ])
            assert restore_result.exit_code == 0
            assert "Restore Completed Successfully" in restore_result.output

            # Check that table items exists in restored database
            conn = sqlite3.connect(target_db)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM items;")
            assert cur.fetchone()[0] == 1
            conn.close()

        finally:
            if os.path.exists(target_db):
                os.unlink(target_db)


def test_cli_config_init_and_list():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as temp_dir:
        conf_path = os.path.join(temp_dir, "test_config.yaml")

        init_res = runner.invoke(main, ["config", "init", "-o", conf_path])
        assert init_res.exit_code == 0
        assert os.path.exists(conf_path)

        list_res = runner.invoke(main, ["config", "list", "-c", conf_path])
        assert list_res.exit_code == 0
        assert "Configuration Profiles" in list_res.output
        assert "local_sqlite" in list_res.output


def test_cli_schedule_cron_and_task():
    runner = CliRunner()
    cron_res = runner.invoke(main, ["schedule", "generate-cron", "-p", "production_mysql"])
    assert cron_res.exit_code == 0
    assert "Crontab Entry" in cron_res.output
    assert "db-backup backup -p production_mysql" in cron_res.output

    task_res = runner.invoke(main, ["schedule", "generate-task", "-p", "production_mysql"])
    assert task_res.exit_code == 0
    assert "schtasks /create" in task_res.output
