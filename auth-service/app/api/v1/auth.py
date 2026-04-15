from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse
from app.core.config import settings
from app.core.email import send_password_reset_email
from app.core.observability import emit_audit_event
from app.core.rate_limit import limiter
from app.core.token_denylist import (
    denylist_access_token,
    denylist_refresh_token,
    is_access_token_denylisted,
    is_refresh_token_denylisted,
)
from app.db import get_db
from app.schemas.user import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    TokenRefresh, TokenVerifyRequest, TokenVerifyResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
    DeleteAccountRequest, MessageResponse,
    RoleEnum as SchemaRoleEnum,
)
from app.crud import UserCRUD
from app.models import RoleEnum as ModelRoleEnum
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    verify_token, create_password_reset_token, hash_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer()


def _refresh_cookie_max_age_seconds() -> int:
    return max(1, int(settings.REFRESH_TOKEN_EXPIRE_DAYS) * 24 * 60 * 60)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=_refresh_cookie_max_age_seconds(),
        httponly=settings.AUTH_REFRESH_COOKIE_HTTPONLY,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )


def _extract_refresh_token(token_data: TokenRefresh | None, request: Request) -> str:
    body_token = (token_data.refresh_token if token_data else None) or ""
    cookie_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME) or ""
    # Cookie takes precedence to support HttpOnly refresh flows.
    token = cookie_token.strip() or body_token.strip()
    return token


def _normalize_origin(value: str | None) -> str | None:
    parsed = urlparse(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _allowed_csrf_origins() -> set[str]:
    normalized = {_normalize_origin(origin) for origin in settings.backend_cors_origins}
    return {origin for origin in normalized if origin}


def _extract_request_origin(request: Request) -> str | None:
    origin_header = _normalize_origin(request.headers.get("origin"))
    if origin_header:
        return origin_header
    referer_header = request.headers.get("referer")
    return _normalize_origin(referer_header)


def _enforce_cookie_request_origin(request: Request, *, action: str) -> None:
    refresh_cookie = (request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME) or "").strip()
    if not refresh_cookie:
        return

    request_origin = _extract_request_origin(request)
    if not request_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin em falta para pedido autenticado por cookie",
        )

    if request_origin not in _allowed_csrf_origins():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Origin não permitido para {action}",
        )


async def _verify_active_access_token(token: str) -> dict | None:
    """Verify access token signature/type and denylist state."""
    payload = verify_token(token, token_type="access")
    if not payload:
        return None

    try:
        if await is_access_token_denylisted(token):
            return None
    except RuntimeError:
        # If Redis is unavailable, fail closed for protected endpoints.
        return None

    return payload


async def _verify_active_refresh_token(token: str) -> dict | None:
    """Verify refresh token signature/type and denylist state."""
    payload = verify_token(token, token_type="refresh")
    if not payload:
        return None

    try:
        if await is_refresh_token_denylisted(token):
            return None
    except RuntimeError:
        # If Redis is unavailable, fail closed for refresh operations.
        return None

    return payload


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Register a new user.
    
    - **email**: User's email address (must be unique)
    - **password**: Password (minimum 8 characters)
    - **full_name**: User's full name
    - **role**: User role (fan or promoter), defaults to fan
    """
    normalized_email = user_data.email.strip().lower()
    requested_role = user_data.role
    if normalized_email.endswith("@prom.pt") and requested_role == SchemaRoleEnum.FAN:
        requested_role = SchemaRoleEnum.PROMOTER

    if requested_role.value == "promoter" and not normalized_email.endswith("@prom.pt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promoter accounts must use an email ending with @prom.pt",
        )

    # Check if user already exists
    existing_user = await UserCRUD.get_user_by_email(db, normalized_email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    try:
        payload = user_data.copy(update={
            "email": normalized_email,
            "role": requested_role,
        })
        user = await UserCRUD.create_user(db, payload)
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            role=user.role.value,
            created_at=user.created_at.isoformat()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    response: Response,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Authenticate user and return access and refresh tokens.
    
    - **email**: User's email address
    - **password**: User's password
    """
    normalized_email = credentials.email.strip().lower()
    user = await UserCRUD.get_user_by_email(db, normalized_email)

    # Backfill safety: old @prom.pt accounts registered as fan are promoted on login.
    if user and normalized_email.endswith("@prom.pt") and user.role != ModelRoleEnum.PROMOTER:
        promoted = await UserCRUD.update_user(db, user.id, role=ModelRoleEnum.PROMOTER)
        if promoted:
            user = promoted
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        emit_audit_event(request, action="login", outcome="failure", email=normalized_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_active:
        emit_audit_event(request, action="login", outcome="blocked_inactive", user_id=user.id, email=user.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create tokens with user_id and role embedded (JWT auto-contido)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        data={"sub": user.id}
    )
    _set_refresh_cookie(response, refresh_token)
    
    emit_audit_event(
        request,
        action="login",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    token_data: TokenRefresh | None = Body(default=None),
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Get a new access token using a refresh token.
    
    - **refresh_token**: Valid refresh token from login
    """
    _enforce_cookie_request_origin(request, action="refresh")
    refresh_token_input = _extract_refresh_token(token_data, request)
    payload = await _verify_active_refresh_token(refresh_token_input)
    
    if not payload:
        emit_audit_event(request, action="refresh", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    user_id = payload.get("sub")
    if not user_id:
        emit_audit_event(request, action="refresh", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user = await UserCRUD.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        emit_audit_event(request, action="refresh", outcome="failure", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new access token
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role.value}
    )
    
    try:
        await denylist_refresh_token(refresh_token_input)
    except RuntimeError:
        emit_audit_event(request, action="refresh", outcome="error", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token store unavailable"
        )

    # Rotate refresh token: old refresh token is revoked, new one is minted.
    refresh_token = create_refresh_token(data={"sub": user.id})
    _set_refresh_cookie(response, refresh_token)
    
    emit_audit_event(
        request,
        action="refresh",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Get current user profile.
    
    Requires Authorization header with Bearer token.
    """
    token = credentials.credentials
    payload = await _verify_active_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authorization code"
        )

    user = await UserCRUD.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        role=user.role.value,
        created_at=user.created_at.isoformat()
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> None:
    """
    Logout user (invalidate token).
    
    Note: In this implementation, we recommend using Redis as a token denylist
    for more robust logout functionality. This endpoint is a placeholder.
    """
    _enforce_cookie_request_origin(request, action="logout")
    token = credentials.credentials
    payload = await _verify_active_access_token(token)
    if not payload:
        emit_audit_event(request, action="logout", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await denylist_access_token(token)
    refresh_cookie_token = (request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME) or "").strip()
    if refresh_cookie_token:
        await denylist_refresh_token(refresh_cookie_token)
    _clear_refresh_cookie(response)
    emit_audit_event(
        request,
        action="logout",
        outcome="success",
        user_id=payload.get("sub"),
        email=payload.get("email"),
        role=payload.get("role"),
    )

    return None


@router.post("/verify", response_model=TokenVerifyResponse)
@limiter.limit(settings.RATE_LIMIT_VERIFY)
async def verify_token_endpoint(
    request: Request,
    token_request: TokenVerifyRequest,
    x_service_auth: str | None = Header(default=None, alias="X-Service-Auth"),
    db: AsyncSession = Depends(get_db)
) -> TokenVerifyResponse:
    """
    Verify if a token is valid (for internal service-to-service use).
    
    This endpoint is used by other services (Inventory, Payment) to quickly
    verify if a token is legitimate without parsing it themselves.
    
    Returns token validity and user information if valid.
    """
    if x_service_auth != settings.INTERNAL_SERVICE_KEY:
        emit_audit_event(request, action="verify", outcome="forbidden")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service credentials",
        )

    payload = await _verify_active_access_token(token_request.token)
    
    if not payload:
        emit_audit_event(request, action="verify", outcome="invalid_token")
        return TokenVerifyResponse(valid=False)
    
    user_id = payload.get("sub")
    user = await UserCRUD.get_user_by_id(db, user_id)
    
    if not user or not user.is_active:
        emit_audit_event(request, action="verify", outcome="invalid_user", user_id=user_id)
        return TokenVerifyResponse(valid=False)
    
    emit_audit_event(
        request,
        action="verify",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    return TokenVerifyResponse(
        valid=True,
        user_id=user.id,
        role=user.role.value,
        email=user.email
    )


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_FORGOT_PASSWORD)
async def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """
    Request a password reset token.

    For security reasons this endpoint always returns the same message,
    even when the email does not exist.
    """
    user = await UserCRUD.get_user_by_email(db, forgot_request.email)

    if user and user.is_active:
        reset_token = create_password_reset_token(user.email, user.id)
        delivered = await send_password_reset_email(user.email, reset_token)
        emit_audit_event(
            request,
            action="password_reset_requested",
            outcome="success" if delivered else "email_delivery_failed",
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )
    else:
        emit_audit_event(request, action="password_reset_requested", outcome="accepted")

    return MessageResponse(
        message="If the account exists, a password reset link was sent"
    )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_RESET_PASSWORD)
async def reset_password(
    request: Request,
    reset_request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Reset password using a valid password_reset token."""
    payload = verify_token(reset_request.token, token_type="password_reset")

    if not payload:
        emit_audit_event(request, action="password_reset", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token"
        )

    user_id = payload.get("sub")
    if not user_id:
        emit_audit_event(request, action="password_reset", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reset token"
        )

    user = await UserCRUD.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        emit_audit_event(request, action="password_reset", outcome="failure", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or inactive"
        )

    await UserCRUD.update_password(db, user.id, hash_password(reset_request.new_password))
    emit_audit_event(
        request,
        action="password_reset",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )

    return MessageResponse(message="Password updated successfully")


@router.delete("/me", response_model=MessageResponse)
async def delete_my_account(
    request: Request,
    body: DeleteAccountRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Delete current authenticated user account permanently."""
    token = credentials.credentials
    payload = await _verify_active_access_token(token)

    if not payload:
        emit_audit_event(request, action="delete_account", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    user = await UserCRUD.get_user_by_id(db, user_id)

    if not user:
        emit_audit_event(request, action="delete_account", outcome="failure", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not verify_password(body.password, user.hashed_password):
        emit_audit_event(request, action="delete_account", outcome="failure", user_id=user.id, email=user.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )

    await denylist_access_token(token)
    await UserCRUD.delete_user(db, user.id)
    emit_audit_event(
        request,
        action="delete_account",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    return MessageResponse(message="Account deleted successfully")


