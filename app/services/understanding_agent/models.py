from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.complaint import ComplaintCategory, ComplaintPriority



class ExtractionError(Exception):
    pass

class ReplyGenerationError(Exception):
    pass

class InvalidInputError(ValueError):
    pass

class StateCorruptionError(Exception):
    pass




class UnderstandingExtraction(BaseModel):
    transcript: str | None = Field(default=None)
    is_anonymous: bool | None = Field(default=None)
    phone_number: str | None = Field(default=None)
    category: ComplaintCategory | None = Field(default=None)
    ward: str | None = Field(default=None)
    priority: ComplaintPriority | None = Field(default=None)
    location_lat: float | None = Field(default=None)
    location_lng: float | None = Field(default=None)


class Message(BaseModel):
    role: str = Field(...)
    content: str = Field(..., min_length=1)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v):
        if v not in ("user", "assistant"):
            raise ValueError(f"role must be 'user' or 'assistant', got '{v}'")
        return v


class ConversationState(BaseModel):
    messages: list[Message] = Field(default_factory=list)
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    turn_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self):
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw):
        try:
            return cls.model_validate_json(raw)
        except Exception as exc:
            raise StateCorruptionError(f"Failed to parse ConversationState: {exc}") from exc

    @classmethod
    def from_legacy(cls, messages_json, extracted_data_json):
        """Build state from legacy JSON-string format stored in DB."""
        try:
            raw_messages = json.loads(messages_json) if messages_json else []
            extracted = json.loads(extracted_data_json) if extracted_data_json else {}
        except json.JSONDecodeError as exc:
            raise StateCorruptionError(f"Failed to parse legacy JSON: {exc}") from exc

        messages = [
            Message(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", datetime.now(timezone.utc).isoformat()),
            )
            for m in raw_messages
            if isinstance(m, dict)
        ]
        user_turns = sum(1 for m in messages if m.role == "user")
        return cls(messages=messages, extracted_data=extracted, turn_count=user_turns)

    def to_legacy(self):
        messages_dicts = [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in self.messages
        ]
        return (
            json.dumps(messages_dicts, ensure_ascii=False),
            json.dumps(self.extracted_data, ensure_ascii=False),
        )



class UnderstandingResult(BaseModel):
    reply: str
    extracted_data: dict[str, Any]
    is_complete: bool
    structured_data: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ReplyResult:
    content: str
    was_fallback: bool
