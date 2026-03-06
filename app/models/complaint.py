from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ComplaintCategory(StrEnum):
    roads = "roads"
    water = "water"
    electricity = "electricity"
    sanitation = "sanitation"
    street_lights = "street_lights"
    safety = "safety"
    parks = "parks"
    other = "other"


class ComplaintPriority(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ComplaintStatus(StrEnum):
    submitted = "submitted"
    assigned = "assigned"
    in_progress = "in_progress"
    resolved = "resolved"
    rejected = "rejected"
    escalated = "escalated"


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(15), unique=True, index=True, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[ComplaintCategory] = mapped_column(
        Enum(ComplaintCategory, native_enum=False),
        nullable=False,
        default=ComplaintCategory.other,
    )
    priority: Mapped[ComplaintPriority] = mapped_column(
        Enum(ComplaintPriority, native_enum=False),
        nullable=False,
        default=ComplaintPriority.medium,
    )
    status: Mapped[ComplaintStatus] = mapped_column(
        Enum(ComplaintStatus, native_enum=False),
        nullable=False,
        default=ComplaintStatus.submitted,
    )
    ward: Mapped[str] = mapped_column(String(120), nullable=False)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Image attachment 
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_gps_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    # New fields
    department_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("departments.id"),
        nullable=True,
    )
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    messages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON string
    extracted_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON string
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ticket_id: Mapped[str | None] = mapped_column(String(15), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class CitizenFeedback(Base):
    __tablename__ = "citizen_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(15), index=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class DepartmentAdmin(Base):
    __tablename__ = "department_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    department_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_otp_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class EscalationLog(Base):
    __tablename__ = "escalation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    complaint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )