"""Deadline engine: urgency calculation (design doc §13 of states / §30-A)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum


class Urgency(str, Enum):
    OVERDUE = "OVERDUE"
    DUE_TODAY = "DUE_TODAY"
    DUE_WITHIN_24H = "DUE_WITHIN_24H"
    DUE_WITHIN_3_DAYS = "DUE_WITHIN_3_DAYS"
    DUE_WITHIN_7_DAYS = "DUE_WITHIN_7_DAYS"
    FUTURE = "FUTURE"
    NO_DEADLINE = "NO_DEADLINE"


def compute_urgency(deadline: datetime | None, now: datetime | None = None) -> Urgency:
    if deadline is None:
        return Urgency.NO_DEADLINE

    if now is None:
        now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()

    remaining = deadline - now

    if remaining < timedelta(0):
        return Urgency.OVERDUE
    if deadline.date() == now.date():
        return Urgency.DUE_TODAY
    if remaining <= timedelta(hours=24):
        return Urgency.DUE_WITHIN_24H
    if remaining <= timedelta(days=3):
        return Urgency.DUE_WITHIN_3_DAYS
    if remaining <= timedelta(days=7):
        return Urgency.DUE_WITHIN_7_DAYS
    return Urgency.FUTURE


def time_remaining(deadline: datetime | None, now: datetime | None = None) -> timedelta | None:
    if deadline is None:
        return None
    if now is None:
        now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
    return deadline - now


def format_remaining(remaining: timedelta) -> str:
    total_seconds = int(remaining.total_seconds())
    if total_seconds < 0:
        return "overdue"
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days > 0:
        return f"{days} day{'s' if days != 1 else ''}"
    if hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"
