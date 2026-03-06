from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.complaint import DepartmentAdmin


def is_unverified_admin_stale(admin: DepartmentAdmin, *, ttl_hours: int) -> bool:
    if admin.email_verified:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    return admin.created_at < cutoff


def purge_stale_unverified_admins(db: Session, *, ttl_hours: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    result = db.execute(
        delete(DepartmentAdmin).where(
            DepartmentAdmin.email_verified.is_(False),
            DepartmentAdmin.created_at < cutoff,
        )
    )
    db.commit()
    return result.rowcount or 0
