from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from enum import Enum


class RoleEnum(str, Enum):
    """User role enumeration."""
    FAN = "fan"
    PROMOTER = "promoter"
    ADMIN = "admin"


class UserCreate(BaseModel):
    """Schema for user registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72, description="Password must be 8-72 characters (bcrypt limitation)")
    full_name: str = Field(..., min_length=1, max_length=255)
    role: RoleEnum = RoleEnum.FAN
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "strongpassword123",
                "full_name": "André Alexandre",
                "role": "fan"
            }
        }


class UserLogin(BaseModel):
    """Schema for user login request."""
    email: EmailStr
    password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "strongpassword123"
            }
        }


class UserResponse(BaseModel):
    """Schema for user response (public data)."""
    id: str
    email: str
    full_name: str
    is_active: bool
    role: RoleEnum
    created_at: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "full_name": "André Alexandre",
                "is_active": True,
                "role": "fan",
                "created_at": "2026-03-02T10:30:00Z"
            }
        }


class TokenResponse(BaseModel):
    """Schema for token response (login/refresh)."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }


class TokenRefresh(BaseModel):
    """Schema for token refresh request."""
    refresh_token: str


class TokenVerifyRequest(BaseModel):
    """Schema for token verification request (internal use)."""
    token: str


class TokenVerifyResponse(BaseModel):
    """Schema for token verification response."""
    valid: bool
    user_id: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot-password request."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for reset-password request."""
    token: str
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Password must be 8-72 characters (bcrypt limitation)",
    )


class DeleteAccountRequest(BaseModel):
    """Schema for account deletion confirmation."""
    password: str


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


class AuthCodeExchangeRequest(BaseModel):
    """Schema for authorization code exchange request."""
    code: str
    client_id: str


class DevEmailTestRequest(BaseModel):
    """Schema for development SMTP test endpoint."""
    email: EmailStr
