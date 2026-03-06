from pydantic import BaseModel
from typing import Literal
from typing import Optional

from pydantic import BaseModel


class CopilotRequest(BaseModel):
    ticket_id: str


class StructuredComplaintResponse(BaseModel):
    final_department: str
    final_priority: Literal["low", "medium", "high", "critical"]
    final_risk_score: int
    supervisor_confidence: int
    risk_category: str
    incident_type: str
    sla_hours: int
    deadline_timestamp: str
    escalation_level: str
    recommended_action: str
    disagreement_detected: bool
    override_applied: bool
    resolution_summary: str
    audit_summary: str
    historical_pattern_detected: bool
    historical_complaint_count: int
    historical_pattern_note: str
    reevaluation_triggered: bool


class CopilotResponse(BaseModel):
    success: bool
    response: StructuredComplaintResponse