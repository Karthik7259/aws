import os
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai.llms.providers.bedrock.completion import BedrockCompletion

load_dotenv()

_original_get_inference_config = BedrockCompletion._get_inference_config

def _patched_get_inference_config(self):
    config = _original_get_inference_config(self)
    config.pop("stopSequences", None)  
    return config

BedrockCompletion._get_inference_config = _patched_get_inference_config

bedrock_llm = LLM(
    model=f"bedrock/{os.environ['BEDROCK_MODEL_ID']}",
    aws_region_name=os.environ["BEDROCK_REGION"],
    temperature=0.3,
    max_tokens=512,
    additional_drop_params=["stop", "stop_sequences"],
)

classification_officer_agent = Agent(
    role="Classification Officer Agent",
    goal="Classify complaint issue and assign the most appropriate department using only provided complaint facts.",
    backstory="Public grievance classification specialist focused on taxonomy accuracy and routing governance.",
    llm=bedrock_llm,
    verbose=True
)

risk_assessment_officer_agent = Agent(
    role="Risk Assessment Officer Agent",
    goal="Compute complaint risk score and priority using defined scoring model and validate classification alignment.",
    backstory="Municipal risk analyst for safety, infrastructure, and service continuity incidents.",
    llm=bedrock_llm,
    verbose=True
)

senior_supervisor_agent = Agent(
    role="Senior Supervisor Agent",
    goal="Produce final authoritative governance decision by validating, reconciling, and overriding earlier outputs when justified.",
    backstory="Senior grievance governance authority responsible for accountability, SLA, and escalation decisions.",
    llm=bedrock_llm,
    verbose=True
)