from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser

from app.models.complaint import ComplaintCategory, ComplaintPriority
from app.services.llm_provider import get_llm_provider

from .config import settings
from .models import (
    ConversationState,
    ExtractionError,
    InvalidInputError,
    Message,
    ReplyResult,
    UnderstandingExtraction,
    UnderstandingResult,
)
from .prompts import (
    COMPLETION_INSTRUCTION_DONE,
    COMPLETION_INSTRUCTION_PENDING,
    EXTRACTION_PROMPT,
    REPLY_PROMPT,
)

logger = logging.getLogger(__name__)

FIELD_FRIENDLY_NAMES = {
    "transcript": "complaint description",
    "category": "category",
    "ward": "location/ward",
    "is_anonymous": "anonymity preference",
    "phone_number": "phone number",
}

_REQUIRED_FIELDS = ("transcript", "category")



class ConversationStateManager:

    def __init__(self, state):
        self._state = state

    @property
    def state(self):
        return self._state

    def add_user_message(self, content):
        msg = Message(role="user", content=content)
        self._state.messages.append(msg)
        self._state.turn_count += 1
        self._state.last_updated = datetime.now(timezone.utc)
        return self._state

    def add_assistant_message(self, content):
        msg = Message(role="assistant", content=content)
        self._state.messages.append(msg)
        self._state.last_updated = datetime.now(timezone.utc)
        return self._state

    def merge_extraction(self, extraction):
        updates = extraction.model_dump(exclude_none=True)
        self._state.extracted_data.update(updates)

        if (
            self._state.extracted_data.get("phone_number")
            and self._state.extracted_data.get("is_anonymous") is None
        ):
            self._state.extracted_data["is_anonymous"] = False

        self._state.last_updated = datetime.now(timezone.utc)
        return self._state

    def apply_defaults(self):
        data = self._state.extracted_data

        if data.get("priority") is None:
            data["priority"] = ComplaintPriority.medium

        self._state.last_updated = datetime.now(timezone.utc)
        return self._state

    def should_force_complete(self):
        return self._state.turn_count >= settings.MAX_USER_TURNS


def _build_chat_history(messages):
    history = []
    for msg in messages:
        if msg.role == "assistant":
            history.append(AIMessage(content=msg.content))
        else:
            history.append(HumanMessage(content=msg.content))
    return history


def extract(message, messages):
    if not message or not message.strip():
        raise InvalidInputError("User message must not be empty or whitespace.")

    window = messages[-settings.CONTEXT_WINDOW_SIZE:]
    chat_history = _build_chat_history(window)

    try:
        parser = PydanticOutputParser(pydantic_object=UnderstandingExtraction)
        llm = get_llm_provider().get_chat_model()
        chain = EXTRACTION_PROMPT | llm
        response = chain.invoke({
            "chat_history": chat_history,
            "message": message,
            "format_instructions": parser.get_format_instructions(),
        })

        try:
            result = parser.parse(response.content)
        except Exception:
            logger.warning("LLM extraction failed to parse JSON; using empty extraction.")
            return UnderstandingExtraction()

        if result is None:
            logger.warning("Structured output returned None; using empty extraction.")
            return UnderstandingExtraction()
        return result

    except Exception as exc:
        logger.exception("LLM extraction failed.")
        return UnderstandingExtraction()


def is_complete(extracted_data):
    has_required = all(
        extracted_data.get(f) is not None and extracted_data.get(f) != ""
        for f in _REQUIRED_FIELDS
    )
    if not has_required:
        return False

    if extracted_data.get("is_anonymous") is None:
        return False

    if (
        extracted_data.get("is_anonymous") is False
        and not extracted_data.get("phone_number")
    ):
        return False

    return True


def missing_fields(extracted_data):
    missing = []
    for field in _REQUIRED_FIELDS:
        value = extracted_data.get(field)
        if value is None or value == "":
            missing.append(field)

    if extracted_data.get("is_anonymous") is None:
        missing.append("is_anonymous")

    if (
        extracted_data.get("is_anonymous") is False
        and not extracted_data.get("phone_number")
    ):
        missing.append("phone_number")

    return missing


def _missing_fields_display(missing):
    return [FIELD_FRIENDLY_NAMES.get(f, f) for f in missing]


def force_complete(extracted_data):
    data = dict(extracted_data)
    if not data.get("transcript"):
        data["transcript"] = "Civic complaint (details unavailable)"
    if not data.get("category"):
        data["category"] = ComplaintCategory.other
    if not data.get("ward"):
        data["ward"] = "Unspecified"
    if data.get("is_anonymous") is None:
        data["is_anonymous"] = True
    if not data.get("priority"):
        data["priority"] = ComplaintPriority.medium
    return data


def build_structured_data(extracted_data, complete):
    if not complete:
        return None
    return {
        "transcript": extracted_data.get("transcript", ""),
        "ward": extracted_data.get("ward", ""),
        "is_anonymous": bool(extracted_data.get("is_anonymous", True)),
        "phone_number": extracted_data.get("phone_number"),
        "location_lat": extracted_data.get("location_lat"),
        "location_lng": extracted_data.get("location_lng"),
        "category": extracted_data.get("category", ComplaintCategory.other),
        "priority": extracted_data.get("priority", ComplaintPriority.medium),
    }



def generate_reply(messages, extracted_data, complete):
    missing_raw = missing_fields(extracted_data)
    missing_display = _missing_fields_display(missing_raw)

    completion_instruction = (
        COMPLETION_INSTRUCTION_DONE if complete else COMPLETION_INSTRUCTION_PENDING
    )

    chat_history = _build_chat_history(messages)

    try:
        llm = get_llm_provider().get_chat_model()
        chain = REPLY_PROMPT | llm
        response = chain.invoke({
            "extracted_json": json.dumps(extracted_data, ensure_ascii=False),
            "missing_fields": ", ".join(missing_display) if missing_display else "none",
            "completion_instruction": completion_instruction,
            "chat_history": chat_history,
        })
        return ReplyResult(content=response.content.strip(), was_fallback=False)

    except Exception:
        logger.exception("Reply generation failed; using fallback.")
        if complete:
            fallback = "Thank you. I have all the details needed. Your complaint is being filed now."
        elif missing_display:
            fallback = f"Could you please provide: {', '.join(missing_display)}?"
        else:
            fallback = "Could you tell me more about your complaint?"
        return ReplyResult(content=fallback, was_fallback=True)



def run_understanding_agent(message, state=None, location_lat=None, location_lng=None):
    if not message or not message.strip():
        raise InvalidInputError("User message must not be empty or whitespace.")

    if state is None:
        state = ConversationState()

    # Inject GPS coords into extracted_data immediately so the agent
    # never needs to ask for location or ward
    if location_lat is not None and location_lng is not None:
        state.extracted_data["location_lat"] = location_lat
        state.extracted_data["location_lng"] = location_lng

    mgr = ConversationStateManager(state)
    mgr.add_user_message(message)
    
    if not message or not message.strip():
        raise InvalidInputError("User message must not be empty or whitespace.")

    if state is None:
        state = ConversationState()

    mgr = ConversationStateManager(state)
    mgr.add_user_message(message)

    extraction = extract(message, state.messages)
    mgr.merge_extraction(extraction)
    mgr.apply_defaults()

    if mgr.should_force_complete():
        state.extracted_data = force_complete(state.extracted_data)

    complete = is_complete(state.extracted_data)
    structured_data = build_structured_data(state.extracted_data, complete)
    reply_result = generate_reply(state.messages, state.extracted_data, complete)

    mgr.add_assistant_message(reply_result.content)

    result = UnderstandingResult(
        reply=reply_result.content,
        extracted_data=state.extracted_data,
        is_complete=complete,
        structured_data=structured_data,
    )

    return result, state
