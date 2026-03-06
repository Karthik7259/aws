from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text


def run_sla_escalation_check(db: Session):

    now = datetime.now(timezone.utc)

    complaints = db.execute(
        text("""
            SELECT id, current_escalation_level, sla_deadline
            FROM complaints
            WHERE status != 'resolved'
        """)
    ).fetchall()

    for cid, level, deadline in complaints:

        if not deadline:
            continue

        if now >= deadline and level == 1:
            new_level = 2
        elif now >= deadline + timedelta(hours=24) and level == 2:
            new_level = 3
        else:
            continue

        db.execute(
            text("""
                UPDATE complaints
                SET current_escalation_level=:lvl,
                    status='escalated'
                WHERE id=:cid
            """),
            {"lvl": new_level, "cid": cid}
        )

        db.execute(
            text("""
                INSERT INTO escalation_logs
                (complaint_id, old_level, new_level)
                VALUES (:cid, :old, :new)
            """),
            {"cid": cid, "old": level, "new": new_level}
        )

    db.commit()