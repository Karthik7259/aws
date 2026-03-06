from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminSignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    department: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AdminAuthData(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    department: str
    is_super_admin: bool = False
    created_at: datetime


class AdminAuthResponse(BaseModel):
    success: bool
    access_token: str
    token_type: str = "bearer"
    data: AdminAuthData


class AdminSignupResponse(BaseModel):
    success: bool
    message: str
    email: EmailStr


class AdminOtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=4, max_length=8)


class AdminOtpResendRequest(BaseModel):
    email: EmailStr


class AdminOtpStatusResponse(BaseModel):
    success: bool
    message: str
    email_verified: bool
