from typing import Protocol

from langchain_aws import ChatBedrockConverse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.database import settings


class LLMProvider(Protocol):
    def get_chat_model(self) -> BaseChatModel:
        pass


class OpenAIProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def get_chat_model(self) -> BaseChatModel:
        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            temperature=0,
        )


class BedrockProvider:
    def __init__(self, model_id: str, region_name: str) -> None:
        self.model_id = model_id
        self.region_name = region_name

    def get_chat_model(self) -> BaseChatModel:
        return ChatBedrockConverse(
            model=self.model_id,
            region_name=self.region_name,
            temperature=0,
        )


def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider.strip().lower()

    if provider == "bedrock":
        return BedrockProvider(
            model_id=settings.bedrock_model_id,
            region_name=settings.bedrock_region,
        )

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'")

    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
