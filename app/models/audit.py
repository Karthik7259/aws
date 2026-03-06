from sqlalchemy import Column, Integer, Text, DateTime, String
from sqlalchemy.sql import func
from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    complaint_text = Column(Text)
    summary = Column(Text)
    priority = Column(String(20))
    assigned_department = Column(String(100))
    recommended_actions = Column(Text)

    final_department = Column(String(150))
    final_priority = Column(String(20))
    final_risk_score = Column(Integer)
    supervisor_confidence = Column(Integer)
    risk_category = Column(String(150))
    incident_type = Column(String(150))
    sla_hours = Column(Integer)
    deadline_timestamp = Column(String(40))
    escalation_level = Column(String(80))
    recommended_action = Column(Text)
    disagreement_detected = Column(Integer)
    override_applied = Column(Integer)
    resolution_summary = Column(Text)
    audit_summary = Column(Text)
    historical_pattern_detected = Column(Integer)
    historical_complaint_count = Column(Integer)
    historical_pattern_note = Column(Text)
    reevaluation_triggered = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())