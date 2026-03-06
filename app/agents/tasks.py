from crewai import Task
from app.agents.agents import (
        classification_officer_agent,
        risk_assessment_officer_agent,
        senior_supervisor_agent,
)

def create_tasks(complaint_text: str):

        classification_task = Task(
        description=f"""
                Phase 1 - Classification Officer analysis.

                Complaint Text:
                {complaint_text}

                Responsibilities:
                - Identify complaint category.
                - Assign most appropriate department.
                - Provide confidence score and key indicators from complaint text only.

                Hard constraints:
                - Do not assign priority.
                - Do not calculate risk score.
                - Do not escalate complaint.
                - Do not invent facts, locations, or repetition history.
                - Use only provided complaint content.
                - Output strict JSON only, no markdown, no extra text.

                Output schema:
                {{
                    "category": "",
                    "assigned_department": "",
                    "confidence_score": 0,
                    "key_indicators": [],
                    "collaboration_note": ""
                }}
                """,
                expected_output="A valid JSON object matching the exact classification schema.",
                agent=classification_officer_agent,
        )

        risk_task = Task(
                description=f"""
                Phase 1 - Risk Assessment Officer analysis.

                Complaint Text:
                {complaint_text}

                Responsibilities:
                - Evaluate severity and public impact.
                - Calculate risk score (0-100) using only the specified model.
                - Assign priority level from risk score mapping.

                Risk model:
                +40 immediate danger to life
                +30 large public impact
                +20 infrastructure collapse risk
                +15 health hazard
                +10 service disruption
                +20 repeated complaint indicator (only if explicit in complaint)

                Priority mapping:
                0-25 Low
                26-50 Medium
                51-75 High
                76-100 Critical

                Hard constraints:
                - Do not reassign department.
                - Do not escalate complaint.
                - Do not invent facts, locations, or repetition history.
                - Use only provided complaint content.
                - Output strict JSON only, no markdown, no extra text.

                Output schema:
                {{
                    "risk_score": 0,
                    "priority": "",
                    "risk_factors": [],
                    "classification_alignment": true,
                    "collaboration_note": ""
                }}
                """,
                expected_output="A valid JSON object matching the exact risk schema.",
                agent=risk_assessment_officer_agent,
        )

        risk_review_classification_task = Task(
                description="""
                Phase 2 - Risk Assessment Officer cross-review of Classification output.

                Review the Classification Officer output from context.

                Requirements:
                - Detect if category and assigned department are aligned with complaint evidence.
                - Flag inconsistencies in collaboration_note.
                - Keep risk_score and priority unchanged unless prior output lacked complaint-grounded factors.
                - Do not reassign department.
                - Do not escalate complaint.
                - Output strict JSON only, no markdown, no extra text.

                Output schema:
                {
                    "risk_score": 0,
                    "priority": "",
                    "risk_factors": [],
                    "classification_alignment": true,
                    "collaboration_note": ""
                }
                """,
                expected_output="A valid JSON risk object updated after cross-review.",
                agent=risk_assessment_officer_agent,
                context=[classification_task, risk_task],
        )

        classification_review_risk_task = Task(
                description="""
                Phase 2 - Classification Officer cross-review of Risk output.

                Review the Risk Assessment Officer output from context.

                Requirements:
                - Confirm whether detected risk factors are supported by complaint text.
                - Note any unsupported assumptions in collaboration_note.
                - Keep classification fields within classification responsibility only.
                - Do not assign priority.
                - Do not calculate or change risk score.
                - Do not escalate complaint.
                - Output strict JSON only, no markdown, no extra text.

                Output schema:
                {
                    "category": "",
                    "assigned_department": "",
                    "confidence_score": 0,
                    "key_indicators": [],
                    "collaboration_note": ""
                }
                """,
                expected_output="A valid JSON classification object updated after cross-review.",
                agent=classification_officer_agent,
                context=[classification_task, risk_review_classification_task],
        )

        supervisor_task = Task(
                description="""
                Phase 3 - Senior Supervisor final governance decision.

                Inputs from context:
                - Classification output (including cross-review)
                - Risk output (including cross-review)

                Supervisor responsibilities:
                - Validate classification accuracy.
                - Validate risk scoring logic and mapping.
                - Detect contradictions and risk underestimation.
                - Resolve disagreements and apply override when justified.
                - Determine final department, final priority, final risk score.
                - Determine supervisor confidence (0-100).
                - Determine risk category and incident type for analytics.
                - Determine SLA hours.
                - Determine deadline timestamp in UTC ISO-8601 format.
                - Determine escalation level.
                - Determine recommended operational action.
                - Produce resolution summary and audit summary.

                SLA rules:
                - Low: 72
                - Medium: 48
                - High: 24
                - Critical: 4-12 (choose complaint-grounded value)

                Escalation rules:
                - Critical: Zone Commissioner
                - High: Department Head
                - Medium: Standard Queue
                - Low: Routine Queue

                Hard constraints:
                - No hallucinated facts.
                - No fabricated location or repetition history.
                - Only use complaint text and agent outputs.
                - Output strict JSON only, no markdown, no extra text.
                - deadline_timestamp must be valid UTC ISO-8601 format (example: 2026-03-02T15:30:00Z).
                - Use wording "SLA assigned" (not "SLA met") in resolution_summary.

                Final output schema:
                {
                    "final_department": "",
                    "final_priority": "",
                    "final_risk_score": 0,
                    "supervisor_confidence": 0,
                    "risk_category": "",
                    "incident_type": "",
                    "sla_hours": 0,
                    "deadline_timestamp": "",
                    "escalation_level": "",
                    "recommended_action": "",
                    "disagreement_detected": false,
                    "override_applied": false,
                    "resolution_summary": "",
                    "audit_summary": ""
                }
                """,
                expected_output="A valid JSON object matching the exact senior supervisor final schema.",
                agent=senior_supervisor_agent,
                context=[classification_review_risk_task, risk_review_classification_task],
        )

        return [
                classification_task,
                risk_task,
                risk_review_classification_task,
                classification_review_risk_task,
                supervisor_task,
        ]