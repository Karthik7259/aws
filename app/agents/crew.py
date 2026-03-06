from crewai import Crew
from app.agents.agents import (
    classification_officer_agent,
    risk_assessment_officer_agent,
    senior_supervisor_agent,
)
from app.agents.tasks import create_tasks

def run_crew(complaint_text: str, supplemental_context: str | None = None):
    if supplemental_context:
        effective_text = (
            f"{complaint_text}\n\nAdditional Governance Context:\n"
            f"{supplemental_context.strip()}"
        )
    else:
        effective_text = complaint_text

    tasks = create_tasks(effective_text)

    crew = Crew(
        agents=[
            classification_officer_agent,
            risk_assessment_officer_agent,
            senior_supervisor_agent,
        ],
        tasks=tasks,
        verbose=True
    )

    result = crew.kickoff()
    return result