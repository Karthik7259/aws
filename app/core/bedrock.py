import boto3
from langchain_aws import ChatBedrock

def get_bedrock_llm():
    client = boto3.client(
        service_name="bedrock-runtime",
        region_name="ap-south-1"
    )

    llm = ChatBedrock(
    client=client,
    model_id="anthropic.claude-3-sonnet-20240229-v1:0"
)

    return llm