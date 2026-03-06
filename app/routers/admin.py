import logging
from typing import Any
from datetime import datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.complaint import CitizenFeedback, Complaint, ComplaintStatus, Department, DepartmentAdmin
from app.schemas.complaint import ComplaintDetailResponse, ComplaintListResponse, ComplaintOut
from app.services.auth import decode_access_token
from app.services.otp_mailer import OtpDeliveryError, send_admin_access_granted_email
from app.services.storage import get_image_url

router = APIRouter(prefix="/api/admin", tags=["admin"])
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

CATEGORY_TO_DEPARTMENT: dict[str, str] = {
    "roads": "Public Works Department",
    "water": "Municipal Corporation",
    "electricity": "Electricity and Power",
    "sanitation": "Municipal Corporation",
    "street_lights": "Municipal Corporation",
    "safety": "Police Department",
    "parks": "Municipal Corporation",
    "other": "Social Welfare",
}


class AdminComplaintStatusUpdateRequest(BaseModel):
    status: ComplaintStatus


class AdminComplaintTableResponse(BaseModel):
    success: bool
    data: list[dict[str, Any]]


class DepartmentAdminOut(BaseModel):
    id: int
    full_name: str
    email: str
    department: str
    email_verified: bool
    is_active: bool
    created_at: datetime


class DepartmentAdminListResponse(BaseModel):
    success: bool
    data: list[DepartmentAdminOut]


class DepartmentAdminActionResponse(BaseModel):
    success: bool
    message: str
    data: DepartmentAdminOut


class DepartmentAdminDeleteResponse(BaseModel):
    success: bool
    message: str
    deleted_id: int


class SuperAdminFeedbackOut(BaseModel):
    id: int
    ticket_id: str
    rating: int
    comment: str | None
    category: str
    status: str
    ward: str
    department: str
    created_at: datetime


class SuperAdminFeedbackListResponse(BaseModel):
    success: bool
    data: list[SuperAdminFeedbackOut]


def _complaint_to_out(complaint: Complaint) -> ComplaintOut:
    out = ComplaintOut.model_validate(complaint)
    out.lat = complaint.location_lat
    out.lng = complaint.location_lng
    out.image_url = get_image_url(complaint.image_path) if complaint.image_path else None
    return out


def _department_admin_to_out(admin: DepartmentAdmin, department_name: str) -> DepartmentAdminOut:
    return DepartmentAdminOut(
        id=admin.id,
        full_name=admin.full_name,
        email=admin.email,
        department=department_name,
        email_verified=admin.email_verified,
        is_active=admin.is_active,
        created_at=admin.created_at,
    )


def get_current_admin_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    department = claims.get("department")
    if not isinstance(department, str) or not department.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing department claim",
        )

    return claims


def get_current_super_admin_claims(
    claims: dict[str, Any] = Depends(get_current_admin_claims),
) -> dict[str, Any]:
    if not bool(claims.get("is_super_admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return claims


@router.get("/complaints/me", response_model=ComplaintListResponse)
def get_my_department_complaints(
    claims: dict[str, Any] = Depends(get_current_admin_claims),
    db: Session = Depends(get_db),
) -> ComplaintListResponse:
    department_name = claims["department"]

    department = db.execute(
        select(Department).where(Department.name.ilike(department_name))
    ).scalar_one_or_none()

    if department is None:
        return ComplaintListResponse(success=True, data=[])

    complaints = db.execute(
        select(Complaint)
        .where(Complaint.department_id == department.id)
        .order_by(Complaint.created_at.desc())
    ).scalars().all()

    return ComplaintListResponse(success=True, data=[_complaint_to_out(item) for item in complaints])


@router.get("/complaints/all", response_model=ComplaintListResponse)
def get_all_complaints(
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> ComplaintListResponse:
    _ = claims
    complaints = db.execute(
        select(Complaint).order_by(Complaint.created_at.desc())
    ).scalars().all()
    return ComplaintListResponse(success=True, data=[_complaint_to_out(item) for item in complaints])


@router.get("/complaints/table", response_model=AdminComplaintTableResponse)
def get_complaints_table(
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> AdminComplaintTableResponse:
    _ = claims
    rows = db.execute(
        text(
            """
            SELECT
                id,
                ticket_id,
                transcript,
                category,
                priority,
                status,
                ward,
                location_lat,
                location_lng,
                phone_number,
                is_anonymous,
                created_at,
                updated_at,
                image_path,
                image_original_name,
                image_gps_lat,
                image_gps_lng,
                department_id,
                risk_score,
                current_escalation_level,
                sla_deadline
            FROM complaints
            ORDER BY created_at DESC
            """
        )
    ).mappings().all()

    return AdminComplaintTableResponse(success=True, data=[dict(row) for row in rows])


@router.patch("/complaints/{ticket_id}/status", response_model=ComplaintDetailResponse)
def update_my_department_complaint_status(
    ticket_id: str,
    payload: AdminComplaintStatusUpdateRequest,
    claims: dict[str, Any] = Depends(get_current_admin_claims),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()

    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint '{ticket_id}' not found",
        )

    admin_department_name = claims["department"]
    admin_department = db.execute(
        select(Department).where(Department.name.ilike(admin_department_name))
    ).scalar_one_or_none()

    if admin_department is None or complaint.department_id != admin_department.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update complaints from your department",
        )

    complaint.status = payload.status
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    return ComplaintDetailResponse(success=True, data=_complaint_to_out(complaint))


@router.patch("/complaints/{ticket_id}/reopen", response_model=ComplaintDetailResponse)
def reopen_complaint_as_super_admin(
    ticket_id: str,
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    _ = claims
    complaint = db.execute(
        select(Complaint).where(Complaint.ticket_id == ticket_id)
    ).scalar_one_or_none()

    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint '{ticket_id}' not found",
        )

    if complaint.status not in {ComplaintStatus.resolved, ComplaintStatus.rejected}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only resolved or rejected complaints can be reopened",
        )

    complaint.status = ComplaintStatus.in_progress
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    return ComplaintDetailResponse(success=True, data=_complaint_to_out(complaint))


@router.get("/department-admins", response_model=DepartmentAdminListResponse)
def get_department_admins(
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> DepartmentAdminListResponse:
    _ = claims
    rows = db.execute(
        select(DepartmentAdmin, Department.name)
        .join(Department, DepartmentAdmin.department_id == Department.id)
        .order_by(DepartmentAdmin.created_at.desc())
    ).all()

    data = [_department_admin_to_out(admin=row[0], department_name=row[1]) for row in rows]
    return DepartmentAdminListResponse(success=True, data=data)


@router.patch("/department-admins/{admin_id}/approve", response_model=DepartmentAdminActionResponse)
def approve_department_admin_access(
    admin_id: int,
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> DepartmentAdminActionResponse:
    _ = claims
    admin = db.execute(
        select(DepartmentAdmin).where(DepartmentAdmin.id == admin_id)
    ).scalar_one_or_none()

    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department admin not found",
        )

    if not admin.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve access before email OTP verification",
        )

    admin.is_active = True
    db.add(admin)
    db.commit()
    db.refresh(admin)

    department = db.execute(
        select(Department).where(Department.id == admin.department_id)
    ).scalar_one_or_none()
    department_name = department.name if department is not None else "Unknown"
    message = "Department admin approved successfully"

    try:
        send_admin_access_granted_email(
            email=admin.email,
            full_name=admin.full_name,
            department=department_name,
        )
        message = "Department admin approved successfully and access email sent"
    except OtpDeliveryError as exc:
        logger.exception("Approval email failed for department admin %s", admin.email)
        message = f"Department admin approved, but email delivery failed: {exc}"

    return DepartmentAdminActionResponse(
        success=True,
        message=message,
        data=_department_admin_to_out(admin=admin, department_name=department_name),
    )


@router.delete("/department-admins/{admin_id}", response_model=DepartmentAdminDeleteResponse)
def delete_department_admin(
    admin_id: int,
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> DepartmentAdminDeleteResponse:
    _ = claims
    admin = db.execute(
        select(DepartmentAdmin).where(DepartmentAdmin.id == admin_id)
    ).scalar_one_or_none()

    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department admin not found",
        )

    db.delete(admin)
    db.commit()

    return DepartmentAdminDeleteResponse(
        success=True,
        message="Department admin deleted successfully",
        deleted_id=admin_id,
    )


@router.get("/feedback", response_model=SuperAdminFeedbackListResponse)
def get_super_admin_feedback(
    claims: dict[str, Any] = Depends(get_current_super_admin_claims),
    db: Session = Depends(get_db),
) -> SuperAdminFeedbackListResponse:
    _ = claims
    rows = db.execute(
        select(CitizenFeedback, Complaint, Department.name)
        .join(Complaint, Complaint.ticket_id == CitizenFeedback.ticket_id)
        .outerjoin(Department, Department.id == Complaint.department_id)
        .order_by(CitizenFeedback.created_at.desc())
    ).all()

    data = [
        SuperAdminFeedbackOut(
            id=feedback.id,
            ticket_id=feedback.ticket_id,
            rating=feedback.rating,
            comment=feedback.comment,
            category=str(complaint.category),
            status=str(complaint.status),
            ward=complaint.ward,
            department=department_name or "Unassigned",
            created_at=feedback.created_at,
        )
        for feedback, complaint, department_name in rows
    ]

    return SuperAdminFeedbackListResponse(success=True, data=data)
