import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db, settings
from app.models.complaint import Department, DepartmentAdmin
from app.schemas.admin_auth import (
    AdminAuthData,
    AdminAuthResponse,
    AdminLoginRequest,
    AdminOtpResendRequest,
    AdminOtpStatusResponse,
    AdminOtpVerifyRequest,
    AdminSignupResponse,
    AdminSignupRequest,
)
from app.services.auth import (
    create_access_token,
    generate_numeric_otp,
    hash_password,
    is_otp_expired,
    otp_expires_at,
    verify_password,
)
from app.services.admin_cleanup import is_unverified_admin_stale
from app.services.otp_mailer import OtpDeliveryError, send_otp_email


router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])
logger = logging.getLogger(__name__)

ALLOWED_DEPARTMENTS = {
    "education",
    "electricity and power",
    "health and family welfare",
    "municipal corporation",
    "police department",
    "public works department",
    "social welfare",
}


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _is_super_admin(email: str) -> bool:
    configured = {
        item.strip().lower()
        for item in settings.super_admin_emails.split(",")
        if item.strip()
    }
    return email.lower() in configured


@router.post("/signup", response_model=AdminSignupResponse, status_code=status.HTTP_201_CREATED)
def signup_admin(payload: AdminSignupRequest, db: Session = Depends(get_db)) -> AdminSignupResponse:
    requested_department = _normalize(payload.department)
    if requested_department not in ALLOWED_DEPARTMENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Department is not allowed for admin signup",
        )

    existing_admin = db.execute(
        select(DepartmentAdmin).where(func.lower(DepartmentAdmin.email) == payload.email.lower())
    ).scalar_one_or_none()
    if existing_admin is not None:
        if is_unverified_admin_stale(existing_admin, ttl_hours=settings.admin_unverified_ttl_hours):
            db.delete(existing_admin)
            db.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Admin with this email already exists",
            )

    department = db.execute(
        select(Department).where(func.lower(Department.name) == requested_department)
    ).scalar_one_or_none()

    if department is None:
        department = Department(name=payload.department.strip(), is_active=True)
        db.add(department)
        db.flush()

    email_otp = generate_numeric_otp()
    expires_at = otp_expires_at()

    admin = DepartmentAdmin(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        department_id=department.id,
        password_hash=hash_password(payload.password),
        email_verified=False,
        email_otp_hash=hash_password(email_otp),
        otp_expires_at=expires_at,
        is_active=False,
    )
    db.add(admin)
    db.flush()

    try:
        send_otp_email(email=admin.email, otp=email_otp)
    except OtpDeliveryError as exc:
        db.rollback()
        logger.exception("Failed to send signup OTP to %s", admin.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to send OTP email: {exc}",
        ) from exc

    db.commit()
    db.refresh(admin)

    return AdminSignupResponse(
        success=True,
        message="Signup created. Verify OTP sent to email.",
        email=admin.email,
    )


@router.post("/verify/email", response_model=AdminOtpStatusResponse)
def verify_email_otp(payload: AdminOtpVerifyRequest, db: Session = Depends(get_db)) -> AdminOtpStatusResponse:
    admin = db.execute(
        select(DepartmentAdmin).where(func.lower(DepartmentAdmin.email) == payload.email.lower())
    ).scalar_one_or_none()

    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found")

    if admin.email_verified:
        return AdminOtpStatusResponse(
            success=True,
            message="Email already verified. Your profile is under review; access will be granted after approval.",
            email_verified=True,
        )

    if is_otp_expired(admin.otp_expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired. Please resend OTP")

    if admin.email_otp_hash is None or not verify_password(payload.otp, admin.email_otp_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email OTP")

    admin.email_verified = True
    # Keep account inactive until manual profile review is completed.
    admin.is_active = False
    db.add(admin)
    db.commit()
    db.refresh(admin)

    return AdminOtpStatusResponse(
        success=True,
        message="OTP verified successfully. We will review your profile and provide access soon.",
        email_verified=admin.email_verified,
    )


@router.post("/otp/resend", response_model=AdminOtpStatusResponse)
def resend_otps(payload: AdminOtpResendRequest, db: Session = Depends(get_db)) -> AdminOtpStatusResponse:
    admin = db.execute(
        select(DepartmentAdmin).where(func.lower(DepartmentAdmin.email) == payload.email.lower())
    ).scalar_one_or_none()

    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found")

    email_otp = generate_numeric_otp()
    admin.email_otp_hash = hash_password(email_otp)
    admin.otp_expires_at = otp_expires_at()
    db.add(admin)

    try:
        send_otp_email(email=admin.email, otp=email_otp)
    except OtpDeliveryError as exc:
        db.rollback()
        logger.exception("Failed to resend OTP to %s", admin.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to send OTP email: {exc}",
        ) from exc

    db.commit()

    return AdminOtpStatusResponse(
        success=True,
        message="OTP resent to email",
        email_verified=admin.email_verified,
    )


@router.post("/login", response_model=AdminAuthResponse)
def login_admin(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> AdminAuthResponse:
    admin = db.execute(
        select(DepartmentAdmin).where(func.lower(DepartmentAdmin.email) == payload.email.lower())
    ).scalar_one_or_none()

    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not admin.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete email OTP verification before login",
        )

    is_super_admin = _is_super_admin(admin.email)

    if not admin.is_active and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your profile is under review. Access will be granted after approval.",
        )

    department = db.execute(
        select(Department).where(Department.id == admin.department_id)
    ).scalar_one_or_none()

    department_name = department.name if department is not None else "Unknown"
    token = create_access_token(
        subject=str(admin.id),
        extra_claims={
            "email": admin.email,
            "department_id": admin.department_id,
            "department": department_name,
            "is_super_admin": is_super_admin,
        },
    )

    return AdminAuthResponse(
        success=True,
        access_token=token,
        data=AdminAuthData(
            id=admin.id,
            full_name=admin.full_name,
            email=admin.email,
            department=department_name,
            is_super_admin=is_super_admin,
            created_at=admin.created_at,
        ),
    )


@router.post("/super-login", response_model=AdminAuthResponse)
def login_super_admin(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> AdminAuthResponse:
    admin = db.execute(
        select(DepartmentAdmin).where(func.lower(DepartmentAdmin.email) == payload.email.lower())
    ).scalar_one_or_none()

    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not admin.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete email OTP verification before login",
        )

    is_super_admin = _is_super_admin(admin.email)
    if not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )

    department = db.execute(
        select(Department).where(Department.id == admin.department_id)
    ).scalar_one_or_none()

    department_name = department.name if department is not None else "Unknown"
    token = create_access_token(
        subject=str(admin.id),
        extra_claims={
            "email": admin.email,
            "department_id": admin.department_id,
            "department": department_name,
            "is_super_admin": True,
        },
    )

    return AdminAuthResponse(
        success=True,
        access_token=token,
        data=AdminAuthData(
            id=admin.id,
            full_name=admin.full_name,
            email=admin.email,
            department=department_name,
            is_super_admin=True,
            created_at=admin.created_at,
        ),
    )
