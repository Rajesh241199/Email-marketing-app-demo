from datetime import datetime, timezone, timedelta
from sqlalchemy import DateTime, func, event
from sqlalchemy.orm import Mapped, mapped_column

_IST = timezone(timedelta(hours=5, minutes=30))


def _now() -> datetime:
    return datetime.now(_IST)


class IDMixin:
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(TimestampMixin, "before_update", propagate=True)
def _set_updated_at(mapper, connection, target):
    target.updated_at = _now()


CreatedAtMixin = TimestampMixin
