import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.schemas.copilot import CopilotRequest, CopilotResponse
from app.agents.crew import run_crew
from app.database import get_db

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


def process_complaint(ticket_id: str, db: Session):

    complaint = db.execute(
        text("""
            SELECT c.transcript, c.location_lat, c.location_lng, c.category, c.department_id, d.name
            FROM complaints c
            LEFT JOIN departments d ON d.id = c.department_id
            WHERE c.ticket_id=:ticket
        """),
        {"ticket": ticket_id}
    ).fetchone()

    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    transcript = complaint[0]
    complaint_category = str(complaint[3]) if complaint[3] is not None else "other"
    current_department_id = complaint[4]
    current_department_name = complaint[5]

    category_department_map = {
        "roads": "Public Works Department",
        "water": "Municipal Corporation",
        "electricity": "Electricity and Power",
        "sanitation": "Municipal Corporation",
        "street_lights": "Municipal Corporation",
        "safety": "Police Department",
        "parks": "Municipal Corporation",
        "other": "Social Welfare",
    }

    departments = db.execute(
        text("SELECT name FROM departments WHERE is_active=TRUE")
    ).fetchall()

    department_list = [row[0] for row in departments]

    context = f"""
Complaint:
{transcript}

Available Departments (choose exactly one):
{department_list}
"""

    result = run_crew(context)

    parsed = {}

    if hasattr(result, "raw") and result.raw:
        raw_output = result.raw.strip()

        if raw_output.startswith("```"):
            raw_output = raw_output.replace("```json", "")
            raw_output = raw_output.replace("```", "")
            raw_output = raw_output.strip()

        try:
            parsed = json.loads(raw_output)
        except Exception:
            parsed = {}

    default_response: Dict[str, Any] = {
        "final_department": "Manual Review",
        "final_priority": "low",
        "final_risk_score": 0,
        "supervisor_confidence": 60,
        "risk_category": "Routine Civic Issue",
        "incident_type": "General Civic Incident",
        "sla_hours": 72,
        "deadline_timestamp": (
            datetime.now(timezone.utc) + timedelta(hours=72)
        ).isoformat(),
        "escalation_level": "Routine Queue",
        "recommended_action": "Manual inspection required.",
        "disagreement_detected": False,
        "override_applied": False,
        "resolution_summary": "SLA assigned due to low priority.",
        "audit_summary": "",
        "historical_pattern_detected": False,
        "historical_complaint_count": 0,
        "historical_pattern_note": "",
        "reevaluation_triggered": False,
    }

    structured = {**default_response, **parsed}

    final_priority = str(structured.get("final_priority", "low")).lower()
    if final_priority == "critical":
        final_priority = "high"
    if final_priority not in {"high", "medium", "low"}:
        final_priority = "low"
    structured["final_priority"] = final_priority

    fallback_department = current_department_name or category_department_map.get(complaint_category, "Social Welfare")
    final_department = str(structured.get("final_department", "")).strip() or fallback_department

    dept = db.execute(
        text("""
            SELECT id FROM departments
            WHERE lower(name)=lower(:d)
        """),
        {"d": final_department}
    ).fetchone()

    if dept is None:
        dept = db.execute(
            text("""
                SELECT id FROM departments
                WHERE lower(name)=lower(:d)
            """),
            {"d": fallback_department}
        ).fetchone()

    dept_id = dept[0] if dept else current_department_id

    sla_hours = int(structured.get("sla_hours", 72))
    fallback_deadline = datetime.now(timezone.utc) + timedelta(hours=sla_hours)
    deadline_raw = structured.get("deadline_timestamp")

    deadline = fallback_deadline
    if isinstance(deadline_raw, str) and deadline_raw.strip():
        try:
            normalized = deadline_raw.replace("Z", "+00:00")
            parsed_deadline = datetime.fromisoformat(normalized)
            deadline = parsed_deadline if parsed_deadline.tzinfo else parsed_deadline.replace(tzinfo=timezone.utc)
        except Exception:
            deadline = fallback_deadline

    escalation_level = 2 if structured["final_priority"] == "high" else 1

    db.execute(
        text("""
            UPDATE complaints
            SET department_id=:department_id,
                priority=:priority,
                risk_score=:risk_score,
                current_escalation_level=:level,
                sla_deadline=:deadline
            WHERE ticket_id=:ticket_id
        """),
        {
            "department_id": dept_id,
            "priority": structured["final_priority"],
            "risk_score": structured.get("final_risk_score", 0),
            "level": escalation_level,
            "deadline": deadline,
            "ticket_id": ticket_id,
        }
    )

    db.commit()

    return structured


@router.post("/", response_model=CopilotResponse)
def copilot(payload: CopilotRequest, db: Session = Depends(get_db)):

    structured = process_complaint(payload.ticket_id, db)

    return CopilotResponse(success=True, response=structured)