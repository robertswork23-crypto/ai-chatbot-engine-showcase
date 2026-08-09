"""Free/Pro tier limits and usage counting.

No separate counter table — usage is computed by counting real persisted
Message rows for the current calendar month, so it can never drift from
what actually happened.
"""
from datetime import datetime
from typing import Tuple

from sqlalchemy.orm import Session

from .db import Message, User

PLAN_LIMITS = {
    "free": 50,
    "pro": 1000,
}


def messages_this_month(db: Session, user_id: int) -> int:
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    return (
        db.query(Message)
        .filter(Message.user_id == user_id, Message.role == "user", Message.created_at >= month_start)
        .count()
    )


def check_within_limit(db: Session, user: User) -> Tuple[bool, int, int]:
    """Returns (is_within_limit, used_this_month, limit_for_plan)."""
    limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
    used = messages_this_month(db, user.id)
    return used < limit, used, limit
