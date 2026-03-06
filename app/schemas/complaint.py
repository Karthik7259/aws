from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.complaint import ComplaintCategory, ComplaintPriority, ComplaintStatus


class ComplaintCreate(BaseModel):
    transcript: str = Field(min_length=5, max_length=5000)
    ward: str = Field(min_length=2, max_length=120)
    is_anonymous: bool = True
    phone_number: str | None = Field(default=None, max_length=10)
    location_lat: float | None = None
    location_lng: float | None = None
    category: ComplaintCategory = ComplaintCategory.other
    department_id: int | None = None
    department_name: str | None = Field(default=None, max_length=150)
    priority: ComplaintPriority = ComplaintPriority.medium

    @model_validator(mode="after")
    def validate_phone_for_non_anonymous(self) -> "ComplaintCreate":
        if not self.is_anonymous and not self.phone_number:
            raise ValueError("phone_number is required when is_anonymous is false")
        return self


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    transcript: str
    category: ComplaintCategory
    priority: ComplaintPriority
    status: ComplaintStatus
    ward: str
    is_anonymous: bool
    phone_number: str | None
    location_lat: float | None
    location_lng: float | None
    lat: float | None = None
    lng: float | None = None
    image_path: str | None = None
    image_original_name: str | None = None
    image_gps_lat: float | None = None
    image_gps_lng: float | None = None
    department_id: int | None = None
    risk_score: int | None = None
    current_escalation_level: int
    sla_deadline: datetime | None = None
    # Computed URL, populated by the router, not orm
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ComplaintSubmitResponse(BaseModel):
    success: bool
    data: ComplaintOut


class ComplaintListResponse(BaseModel):
    success: bool
    data: list[ComplaintOut]


class ComplaintDetailResponse(BaseModel):
    success: bool
    data: ComplaintOut


# Session schemas
class StartSessionResponse(BaseModel):
    success: bool
    session_id: str
    greeting: str


class MessageRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    location_lat: float | None = None
    location_lng: float | None = None


class MessageResponse(BaseModel):
    success: bool
    reply: str
    is_complete: bool
    ready_for_submit: bool = False
    ticket_id: str | None = None
    structured_data: dict[str, Any] | None = None


class SessionSubmitRequest(BaseModel):
    session_id: str
    overrides: dict[str, Any] | None = None


class SessionSubmitResponse(BaseModel):
    success: bool
    ticket_id: str
    structured_data: dict[str, Any]


class SessionDetailResponse(BaseModel):
    success: bool
    session_id: str
    messages: list[dict[str, Any]]
    extracted_data: dict[str, Any]
    is_complete: bool
    ticket_id: str | None = None


class SessionSummaryOut(BaseModel):
    session_id: str
    is_complete: bool
    ticket_id: str | None = None
    message_count: int
    created_at: datetime


class SessionListResponse(BaseModel):
    success: bool
    data: list[SessionSummaryOut]


# Feedback schemas
class FeedbackCreate(BaseModel):
    ticket_id: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    success: bool
    message: str


class ComplaintUpdate(BaseModel):
    transcript: str | None = Field(default=None, min_length=5, max_length=5000)
    ward: str | None = Field(default=None, min_length=2, max_length=120)
    category: ComplaintCategory | None = None
    department_id: int | None = None
    department_name: str | None = Field(default=None, max_length=150)
    priority: ComplaintPriority | None = None
    status: ComplaintStatus | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    phone_number: str | None = Field(default=None, max_length=10)


class ComplaintStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    status: ComplaintStatus
    department: str
    sla_deadline: str
    estimated_resolution: str
    created_at: datetime
    updated_at: datetime


class ComplaintStatusResponse(BaseModel):
    success: bool
    data: ComplaintStatusOut


class CitizenComplaintsResponse(BaseModel):
    success: bool
    data: list[ComplaintOut]


class DepartmentOut(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime


class DepartmentListResponse(BaseModel):
    success: bool
    data: list[DepartmentOut]


# Image upload response
class ImageUploadResponse(BaseModel):
    success: bool
    ticket_id: str
    image_url: str
    image_gps_lat: float | None = None
    image_gps_lng: float | None = None
    message: str = "Image uploaded successfully"