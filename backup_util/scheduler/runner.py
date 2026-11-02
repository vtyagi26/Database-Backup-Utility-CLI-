import os
import signal
import sys
import time
from datetime import datetime
from typing import Callable, Optional

import schedule
from rich.console import Console

from backup_util.logger import get_logger

logger = get_logger()
console = Console()


class BackupScheduler:
    """Manages scheduled backup execution via recurring intervals or OS cron generators."""

    def __init__(self, backup_task: Callable[[], None], job_name: str = "Database Backup Job"):
        self.backup_task = backup_task
        self.job_name = job_name
        self._running = False

    def schedule_interval(
        self,
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        daily_at: Optional[str] = None,
        hourly: bool = False,
    ) -> None:
        """Configures the recurring schedule."""
        schedule.clear()

        if minutes:
            logger.info(f"Scheduling '{self.job_name}' every {minutes} minute(s).")
            schedule.every(minutes).minutes.do(self._run_job)
        elif hours:
            logger.info(f"Scheduling '{self.job_name}' every {hours} hour(s).")
            schedule.every(hours).hours.do(self._run_job)
        elif daily_at:
            logger.info(f"Scheduling '{self.job_name}' daily at {daily_at}.")
            schedule.every().day.at(daily_at).do(self._run_job)
        elif hourly:
            logger.info(f"Scheduling '{self.job_name}' every hour.")
            schedule.every().hour.do(self._run_job)
        else:
            # Default: every 24 hours
            logger.info(f"Scheduling '{self.job_name}' daily.")
            schedule.every().day.do(self._run_job)

    def _run_job(self) -> None:
        logger.info(f"[Scheduled Job Triggered] Starting '{self.job_name}' at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            self.backup_task()
        except Exception as e:
            logger.error(f"Scheduled backup failed: {e}")

    def run_forever(self, run_immediately: bool = False) -> None:
        """Starts the scheduler loop until interrupted."""
        self._running = True

        def handle_exit(signum, frame):
            console.print("\n[yellow]Shutdown signal received. Stopping backup scheduler...[/yellow]")
            self._running = False

        try:
            signal.signal(signal.SIGINT, handle_exit)
            signal.signal(signal.SIGTERM, handle_exit)
        except Exception:
            pass

        if run_immediately:
            logger.info("Executing initial immediate backup before schedule loop...")
            self._run_job()

        console.print(f"[bold cyan]Scheduler running for '{self.job_name}'. Press Ctrl+C to exit.[/bold cyan]")

        while self._running:
            schedule.run_pending()
            time.sleep(1)

        logger.info("Scheduler stopped cleanly.")

    @classmethod
    def generate_cron_string(cls, cli_command: str, schedule_expr: str = "0 2 * * *") -> str:
        """Generates a crontab entry for Linux/macOS."""
        return f"# Database Backup Utility Cron Job\n{schedule_expr} {cli_command} >> /var/log/db_backup_cron.log 2>&1\n"

    @classmethod
    def generate_windows_task_command(cls, task_name: str, cli_command: str, start_time: str = "02:00") -> str:
        """Generates a Windows schtasks command."""
        return (
            f'schtasks /create /tn "{task_name}" /tr "{cli_command}" '
            f'/sc daily /st {start_time} /ru SYSTEM'
        )
