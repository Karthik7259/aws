import uuid
import io

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.copilot import process_complaint

from app.database import get_db
from app.models.complaint import Complaint, ComplaintStatus, ConversationSession, CitizenFeedback, Department
from app.schemas.complaint import (
    CitizenComplaintsResponse,
    ComplaintCreate,
    ComplaintDetailResponse,
    ComplaintListResponse,
    ComplaintOut,
    ComplaintStatusOut,
    ComplaintStatusResponse,
    ComplaintSubmitResponse,
    ComplaintUpdate,
    DepartmentListResponse,
    DepartmentOut,
    ImageUploadResponse,
    MessageRequest,
    MessageResponse,
    SessionSubmitRequest,
    SessionSubmitResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionSummaryOut,
    StartSessionResponse,
    FeedbackCreate, 
    FeedbackResponse,
)
from app.services.storage import delete_complaint_image, get_image_url, save_complaint_image
from app.services.geocoding import reverse_geocode
from app.services.understanding_agent import (
    INITIAL_GREETING,
    ConversationState,
    ConversationStateManager,
    run_understanding_agent,
)
from app.services.understanding_agent.agent import (
    build_structured_data,
    is_complete as is_session_data_complete,
)

import json

router = APIRouter(prefix="/api/complaints", tags=["complaints"])

_DEPARTMENT_MAP: dict[str, str] = {
    "roads": "Public Works Department",
    "water": "Municipal Corporation",
    "electricity": "Electricity and Power",
    "sanitation": "Municipal Corporation",
    "street_lights": "Municipal Corporation",
    "safety": "Police Department",
    "parks": "Municipal Corporation",
    "other": "Social Welfare",
}

_SLA_HOURS: dict[str, int] = {
    "high": 24,
    "medium": 72,
    "low": 168,
}

# Allowed MIME types for complaint photos
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_department(category: str) -> str:
    return _DEPARTMENT_MAP.get(str(category), "Social Welfare")


def _resolve_department_id(
    db: Session,
    department_id: int | None = None,
    department_name: str | None = None,
    category: str | None = None,
) -> int | None:
    if department_id is not None:
        by_id = db.execute(
            select(Department).where(Department.id == department_id)
        ).scalar_one_or_none()
        if by_id is not None:
            return by_id.id

    if department_name:
        name = department_name.strip()
        if name:
            by_name = db.execute(
                select(Department).where(Department.name.ilike(name))
            ).scalar_one_or_none()
            if by_name is not None:
                return by_name.id

    fallback_name = _get_department(str(category or "other"))
    fallback = db.execute(
        select(Department).where(Department.name.ilike(fallback_name))
    ).scalar_one_or_none()
    return fallback.id if fallback is not None else None


def _get_department_name(db: Session, complaint: Complaint) -> str:
    if complaint.department_id is not None:
        department = db.execute(
            select(Department).where(Department.id == complaint.department_id)
        ).scalar_one_or_none()
        if department is not None:
            return department.name
    return _get_department(str(complaint.category))


def _get_sla_deadline(complaint: Complaint) -> str:
    hours = _SLA_HOURS.get(str(complaint.priority), 72)
    created = complaint.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    deadline = created + timedelta(hours=hours)
    return deadline.strftime("%B %d, %Y at %I:%M %p UTC")


def _estimated_resolution(complaint: Complaint) -> str:
    if complaint.status in (ComplaintStatus.resolved, ComplaintStatus.rejected):
        return str(complaint.status).capitalize()
    now = datetime.now(timezone.utc)
    hours = _SLA_HOURS.get(str(complaint.priority), 72)
    created = complaint.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    deadline = created + timedelta(hours=hours)
    remaining = deadline - now
    total_seconds = remaining.total_seconds()
    if total_seconds <= 0:
        return "Overdue"
    hours_left = total_seconds / 3600
    if hours_left < 1:
        return "Within the hour"
    if hours_left < 24:
        return f"Within {int(hours_left)} hour(s)"
    days_left = hours_left / 24
    return f"Within {int(days_left)} day(s)"


def _generate_ticket_id(session: Session) -> str:
    current_year = datetime.now().year
    year_prefix = f"GRV-{current_year}-"
    result = session.execute(
        select(func.count(Complaint.id)).where(Complaint.ticket_id.like(f"{year_prefix}%"))
    )
    next_number = (result.scalar_one() or 0) + 1
    return f"{year_prefix}{next_number:06d}"


def _extract_exif_gps(file_bytes: bytes) -> tuple[float, float] | None:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img = Image.open(io.BytesIO(file_bytes))
        exif_data = img._getexif()  # type: ignore[attr-defined]
        if not exif_data:
            return None

        gps_info: dict = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_value

        if not gps_info:
            return None

        def _dms_to_dd(dms: tuple, ref: str) -> float:
            degrees, minutes, seconds = dms
            # IFDRational or plain float/int
            dd = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
            if ref in ("S", "W"):
                dd = -dd
            return dd

        lat = _dms_to_dd(gps_info["GPSLatitude"], gps_info["GPSLatitudeRef"])
        lng = _dms_to_dd(gps_info["GPSLongitude"], gps_info["GPSLongitudeRef"])
        return lat, lng
    except Exception:
        return None


def _complaint_to_out(complaint: Complaint) -> ComplaintOut:
    """Convert ORM Complaint → ComplaintOut, resolving the image URL."""
    out = ComplaintOut.model_validate(complaint)
    out.lat = complaint.location_lat
    out.lng = complaint.location_lng
    out.image_url = get_image_url(complaint.image_path) if complaint.image_path else None
    return out


def _ward_from_coords(lat: float, lng: float) -> str:
    geo = reverse_geocode(lat, lng)
    return geo.ward_guess() if geo else "Unspecified"


@router.post("/start", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
def start_session(db: Session = Depends(get_db)) -> StartSessionResponse:
    """Create a new conversation session seeded with the initial greeting."""
    initial_state = ConversationState()
    mgr = ConversationStateManager(initial_state)
    mgr.add_assistant_message(INITIAL_GREETING)

    messages_json, extracted_json = initial_state.to_legacy()

    session = ConversationSession(
        session_id=str(uuid.uuid4()),
        messages=messages_json,
        extracted_data=extracted_json,
        is_complete=False,
    )
    db.add(session)
    db.commit()
    return StartSessionResponse(
        success=True,
        session_id=session.session_id,
        greeting=INITIAL_GREETING,
    )


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(db: Session = Depends(get_db)) -> SessionListResponse:
    sessions = db.execute(
        select(ConversationSession).order_by(ConversationSession.created_at.desc())
    ).scalars().all()

    data = []
    for s in sessions:
        messages = json.loads(s.messages) if s.messages else []
        data.append(SessionSummaryOut(
            session_id=s.session_id,
            is_complete=s.is_complete,
            ticket_id=s.ticket_id,
            message_count=len(messages),
            created_at=s.created_at,
        ))

    return SessionListResponse(success=True, data=data)


@router.get("/session/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionDetailResponse:
    conversation = db.execute(
        select(ConversationSession).where(ConversationSession.session_id == session_id)
    ).scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Session '{session_id}' not found")

    messages = json.loads(conversation.messages) if conversation.messages else []
    extracted_data = json.loads(conversation.extracted_data) if conversation.extracted_data else {}

    return SessionDetailResponse(
        success=True,
        session_id=conversation.session_id,
        messages=messages,
        extracted_data=extracted_data,
        is_complete=conversation.is_complete,
        ticket_id=conversation.ticket_id,
    )


@router.post("/message", response_model=MessageResponse)
def send_message(payload: MessageRequest, db: Session = Depends(get_db)) -> MessageResponse:
    conversation = db.execute(
        select(ConversationSession).where(ConversationSession.session_id == payload.session_id)
    ).scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Session '{payload.session_id}' not found")

    state = ConversationState.from_legacy(
        messages_json=conversation.messages,
        extracted_data_json=conversation.extracted_data,
    )

    if payload.location_lat is not None and payload.location_lng is not None:
        # Pre-fill ward so the agent never asks for it
        if not state.extracted_data.get("ward"):
            ward = _ward_from_coords(payload.location_lat, payload.location_lng)
            state.extracted_data["ward"] = ward
        state.extracted_data["location_lat"] = payload.location_lat
        state.extracted_data["location_lng"] = payload.location_lng

    result, updated_state = run_understanding_agent(
        message=payload.message,
        state=state,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
    )

    updated_messages_json, updated_extracted_json = updated_state.to_legacy()

    # Merge coordinates into extracted data
    if payload.location_lat is not None and payload.location_lng is not None:
        merged = json.loads(updated_extracted_json)
        merged["location_lat"] = payload.location_lat
        merged["location_lng"] = payload.location_lng
        updated_extracted_json = json.dumps(merged)

        if result.is_complete and result.structured_data is not None:
            result.structured_data["location_lat"] = payload.location_lat
            result.structured_data["location_lng"] = payload.location_lng

    conversation.messages = updated_messages_json
    conversation.extracted_data = updated_extracted_json
    ready_for_submit = result.is_complete and conversation.ticket_id is None
    conversation.is_complete = bool(conversation.ticket_id)

    db.add(conversation)
    db.commit()

    return MessageResponse(
        success=True,
        reply=result.reply,
        is_complete=bool(conversation.ticket_id),
        ready_for_submit=ready_for_submit,
        ticket_id=conversation.ticket_id,
        structured_data=result.structured_data,
    )


@router.post("/submit-session", response_model=SessionSubmitResponse)
def submit_session_complaint(
    payload: SessionSubmitRequest,
    db: Session = Depends(get_db),
) -> SessionSubmitResponse:
    conversation = db.execute(
        select(ConversationSession).where(ConversationSession.session_id == payload.session_id)
    ).scalar_one_or_none()

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{payload.session_id}' not found",
        )

    if conversation.ticket_id is not None:
        structured_data = build_structured_data(
            json.loads(conversation.extracted_data) if conversation.extracted_data else {},
            complete=True,
        ) or {}
        return SessionSubmitResponse(
            success=True,
            ticket_id=conversation.ticket_id,
            structured_data=structured_data,
        )

    extracted_data = json.loads(conversation.extracted_data) if conversation.extracted_data else {}
    
    if payload.overrides:
        extracted_data.update(payload.overrides)
        
    if not is_session_data_complete(extracted_data):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Complaint details are incomplete. Please continue the conversation before submitting.",
        )

    structured_data = build_structured_data(extracted_data, complete=True) or {}

    if (not structured_data.get("ward") or structured_data["ward"] == "Unspecified") and structured_data.get("location_lat"):
        structured_data["ward"] = _ward_from_coords(
            structured_data["location_lat"],
            structured_data["location_lng"],
        )

    complaint_payload = ComplaintCreate.model_validate(structured_data)
    complaint = Complaint(
        ticket_id=_generate_ticket_id(db),
        transcript=complaint_payload.transcript,
        category=complaint_payload.category,
        priority=complaint_payload.priority,
        status=ComplaintStatus.submitted,
        ward=complaint_payload.ward,
        location_lat=complaint_payload.location_lat,
        location_lng=complaint_payload.location_lng,
        is_anonymous=complaint_payload.is_anonymous,
        phone_number=None if complaint_payload.is_anonymous else complaint_payload.phone_number,
        department_id=_resolve_department_id(
            db,
            department_id=complaint_payload.department_id,
            department_name=complaint_payload.department_name,
            category=str(complaint_payload.category),
        ),
    )
    db.add(complaint)
    db.flush()

    conversation.ticket_id = complaint.ticket_id
    conversation.is_complete = True
    db.add(conversation)
    db.commit()

    try:
        process_complaint(complaint.ticket_id, db)
    except Exception as e:
        print("Agent processing failed:", e)

    return SessionSubmitResponse(
        success=True,
        ticket_id=complaint.ticket_id,
        structured_data=structured_data,
    )

@router.post("/{ticket_id}/upload-image", response_model=ImageUploadResponse)
async def upload_complaint_image(
    ticket_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImageUploadResponse:
    """
    Attach a photo to an existing complaint.
    - Validates file type and size.
    - Extracts GPS EXIF from the image if present.
    - Stores the file via the storage abstraction (local → S3).
    - Replaces any previously uploaded image for this ticket.
    """
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()

    if complaint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Complaint '{ticket_id}' not found")

    # Validate content type
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{file.content_type}'. "
                   f"Allowed: {', '.join(_ALLOWED_IMAGE_TYPES)}",
        )

    file_bytes = await file.read()

    if len(file_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum size of {_MAX_IMAGE_BYTES // (1024*1024)} MB",
        )

    # Delete old image if any
    if complaint.image_path:
        delete_complaint_image(complaint.image_path)

    # Extract EXIF GPS
    exif_gps = _extract_exif_gps(file_bytes)

    # Persist
    original_name = file.filename or "photo.jpg"
    storage_key = save_complaint_image(file_bytes, original_name, ticket_id)

    complaint.image_path = storage_key
    complaint.image_original_name = original_name
    if exif_gps:
        complaint.image_gps_lat, complaint.image_gps_lng = exif_gps

    db.commit()
    db.refresh(complaint)

    image_url = get_image_url(storage_key) or ""

    return ImageUploadResponse(
        success=True,
        ticket_id=ticket_id,
        image_url=image_url,
        image_gps_lat=complaint.image_gps_lat,
        image_gps_lng=complaint.image_gps_lng,
        message="Image uploaded and geotagged successfully" if exif_gps else "Image uploaded successfully",
    )

@router.post("/create", response_model=ComplaintSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_complaint(payload: ComplaintCreate, db: Session = Depends(get_db)) -> ComplaintSubmitResponse:
    # Auto-fill ward from coords if blank
    ward = payload.ward
    if (not ward or ward == "Unspecified") and payload.location_lat is not None:
        ward = _ward_from_coords(payload.location_lat, payload.location_lng)  # type: ignore[arg-type]

    complaint = Complaint(
        ticket_id=_generate_ticket_id(db),
        transcript=payload.transcript,
        category=payload.category,
        priority=payload.priority,
        status=ComplaintStatus.submitted,
        ward=ward,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        is_anonymous=payload.is_anonymous,
        phone_number=None if payload.is_anonymous else payload.phone_number,
        department_id=_resolve_department_id(
            db,
            department_id=payload.department_id,
            department_name=payload.department_name,
            category=str(payload.category),
        ),
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    try:
        process_complaint(complaint.ticket_id, db)
    except Exception as e:
        print("Agent processing failed:", e)

    return ComplaintSubmitResponse(success=True, data=_complaint_to_out(complaint))


@router.get("", response_model=ComplaintListResponse)
def list_complaints(db: Session = Depends(get_db)) -> ComplaintListResponse:
    complaints = db.execute(
        select(Complaint).order_by(Complaint.created_at.desc())
    ).scalars().all()
    return ComplaintListResponse(success=True, data=[_complaint_to_out(c) for c in complaints])


@router.get("/departments", response_model=DepartmentListResponse)
def list_departments(db: Session = Depends(get_db)) -> DepartmentListResponse:
    departments = db.execute(
        select(Department)
        .where(Department.is_active.is_(True))
        .order_by(Department.name.asc())
    ).scalars().all()
    data = [
        DepartmentOut(
            id=d.id,
            name=d.name,
            is_active=d.is_active,
            created_at=d.created_at,
        )
        for d in departments
    ]
    return DepartmentListResponse(success=True, data=data)


@router.get("/citizen/{phone}", response_model=CitizenComplaintsResponse)
def get_complaints_by_phone(phone: str, db: Session = Depends(get_db)) -> CitizenComplaintsResponse:
    complaints = db.execute(
        select(Complaint)
        .where(Complaint.phone_number == phone)
        .order_by(Complaint.created_at.desc())
    ).scalars().all()
    return CitizenComplaintsResponse(success=True, data=[_complaint_to_out(c) for c in complaints])

@router.post("/{ticket_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    ticket_id: str,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    # Complaint must exist
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint '{ticket_id}' not found",
        )

    # Only allow feedback on resolved complaints
    if complaint.status != ComplaintStatus.resolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback can only be submitted for resolved complaints",
        )

    # Prevent duplicate feedback for the same ticket
    existing = db.execute(
        select(CitizenFeedback).where(CitizenFeedback.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback has already been submitted for this complaint",
        )

    feedback = CitizenFeedback(
        ticket_id=ticket_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()

    return FeedbackResponse(success=True, message="Thank you for your feedback!")

@router.get("/{ticket_id}", response_model=ComplaintDetailResponse)
def get_complaint_by_ticket_id(ticket_id: str, db: Session = Depends(get_db)) -> ComplaintDetailResponse:
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Complaint '{ticket_id}' not found")
    return ComplaintDetailResponse(success=True, data=_complaint_to_out(complaint))


@router.patch("/update/{ticket_id}", response_model=ComplaintDetailResponse)
def edit_complaint(
    ticket_id: str,
    payload: ComplaintUpdate,
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Complaint '{ticket_id}' not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="No fields were provided for update")

    if "department_name" in update_data or "department_id" in update_data:
        complaint.department_id = _resolve_department_id(
            db,
            department_id=update_data.get("department_id"),
            department_name=update_data.get("department_name"),
            category=str(update_data.get("category", complaint.category)),
        )
        update_data.pop("department_name", None)
        update_data.pop("department_id", None)

    for field, value in update_data.items():
        setattr(complaint, field, value)

    db.commit()
    db.refresh(complaint)
    return ComplaintDetailResponse(success=True, data=_complaint_to_out(complaint))


@router.get("/{ticket_id}/status", response_model=ComplaintStatusResponse)
def get_complaint_status(ticket_id: str, db: Session = Depends(get_db)) -> ComplaintStatusResponse:
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Complaint '{ticket_id}' not found")

    out = ComplaintStatusOut(
        ticket_id=complaint.ticket_id,
        status=complaint.status,
        department=_get_department_name(db, complaint),
        sla_deadline=_get_sla_deadline(complaint),
        estimated_resolution=_estimated_resolution(complaint),
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
    )
    return ComplaintStatusResponse(success=True, data=out)