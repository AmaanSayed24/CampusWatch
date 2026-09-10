"""Scheduler: periodic sync + daily summary (§10, §25)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(
        self, sync_service: SyncService, check_interval_minutes: int, daily_summary_time: str
    ):
        self._sync_service = sync_service
        self._interval = check_interval_minutes
        hour, minute = (int(part) for part in daily_summary_time.split(":"))
        self._summary_hour, self._summary_minute = hour, minute
        self._scheduler = BlockingScheduler()

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_sync_job,
            trigger=IntervalTrigger(minutes=self._interval, start_date=datetime.now()),
            id="portal_sync",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._daily_summary_job,
            trigger=CronTrigger(hour=self._summary_hour, minute=self._summary_minute),
            id="daily_summary",
        )
        logger.info(
            "Scheduler started: sync every %d min, daily summary at %02d:%02d",
            self._interval, self._summary_hour, self._summary_minute,
        )
        try:
            self._run_sync_job()  # immediate first pass
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")

    def _run_sync_job(self) -> None:
        try:
            asyncio.run(self._sync_service.run_sync())
        except Exception:
            logger.exception("Scheduled sync failed; will retry on next interval")

    def _daily_summary_job(self) -> None:
        try:
            self._sync_service.send_daily_summary()
        except Exception:
            logger.exception("Daily summary failed")
