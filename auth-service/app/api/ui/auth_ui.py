from urllib.parse import urlencode, urlparse
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_password_reset_email
from app.core.observability import emit_audit_event
from app.core.rate_limit import limiter
from app.core.redis_client import get_redis
from app.core.security import (
    create_access_token,
    create_authorization_code,
    create_password_reset_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.core.token_denylist import denylist_access_token, is_access_token_denylisted
from app.crud import UserCRUD
from app.db import get_db
from app.schemas.user import UserCreate

router = APIRouter(prefix="/ui", tags=["auth-ui"])
templates = Jinja2Templates(directory="app/templates")


def _is_allowed_redirect_uri_for_client(client_id: str, redirect_uri: str) -> bool:
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"}:
        return False

    allowed_uris = settings.auth_clients.get(client_id, [])
    return redirect_uri in allowed_uris


def _build_redirect(redirect_uri: str, params: dict[str, str]) -> str:
    query = urlencode(params)
    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{query}"


def _ensure_client_redirect_allowed(client_id: str, redirect_uri: str) -> None:
    if client_id not in settings.auth_clients:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown client_id")
    if not _is_allowed_redirect_uri_for_client(client_id, redirect_uri):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect_uri")


async def _create_stored_auth_code(user_id: str, email: str, role: str, client_id: str) -> str:
    """Create auth code and store one-time key in Redis."""
    redis_client = get_redis()
    jti = str(uuid4())
    code = create_authorization_code(
        {
            "sub": user_id,
            "email": email,
            "role": role,
            "client_id": client_id,
            "jti": jti,
        }
    )
    await redis_client.setex(
        f"auth_code:{jti}",
        settings.AUTH_CODE_EXPIRE_SECONDS,
        client_id,
    )
    return code


def _csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _set_sso_cookie(response: RedirectResponse, access_token: str) -> None:
    response.set_cookie(
        key=settings.SSO_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.SSO_COOKIE_SECURE,
        samesite=settings.SSO_COOKIE_SAMESITE,
        domain=settings.SSO_COOKIE_DOMAIN,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/login")
async def login_page(
    request: Request,
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
):
    """Render login page and support auto-redirect for active SSO session."""
    _ensure_client_redirect_allowed(client_id, redirect_uri)

    sso_token = request.cookies.get(settings.SSO_COOKIE_NAME)
    if sso_token:
        try:
            if await is_access_token_denylisted(sso_token):
                payload = None
            else:
                payload = verify_token(sso_token, token_type="access")
        except RuntimeError:
            payload = verify_token(sso_token, token_type="access")
        if payload:
            user_id = payload.get("sub")
            email = payload.get("email")
            role = payload.get("role")
            if user_id and email and role:
                code = await _create_stored_auth_code(
                    user_id=user_id,
                    email=email,
                    role=role,
                    client_id=client_id,
                )
                params = {"code": code}
                if state:
                    params["state"] = state
                return RedirectResponse(_build_redirect(redirect_uri, params), status_code=status.HTTP_303_SEE_OTHER)

    csrf_token = _csrf_token()
    response = templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state or "",
            "csrf_token": csrf_token,
            "error": "",
        },
    )
    response.set_cookie("csrf_token", csrf_token, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
    return response


@router.post("/login")
@limiter.limit(settings.RATE_LIMIT_UI_LOGIN)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    csrf_token: str = Form(...),
    state: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Process login form and redirect with authorization code."""
    _ensure_client_redirect_allowed(client_id, redirect_uri)

    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or cookie_csrf != csrf_token:
        emit_audit_event(
            request,
            action="ui_login",
            outcome="forbidden_csrf",
            email=email,
            client_id=client_id,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    user = await UserCRUD.get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        emit_audit_event(
            request,
            action="ui_login",
            outcome="failure",
            email=email,
            client_id=client_id,
            details={"client_id": client_id},
        )
        new_csrf = _csrf_token()
        response = templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "csrf_token": new_csrf,
                "error": "Invalid credentials",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
        return response

    code = await _create_stored_auth_code(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        client_id=client_id,
    )
    params = {"code": code}
    if state:
        params["state"] = state

    redirect_target = _build_redirect(redirect_uri, params)
    response = RedirectResponse(redirect_target, status_code=status.HTTP_303_SEE_OTHER)

    # This cookie enables SSO behavior across client apps sharing this auth domain.
    sso_access_token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role.value}
    )
    _set_sso_cookie(response, sso_access_token)
    emit_audit_event(
        request,
        action="ui_login",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        client_id=client_id,
        details={"client_id": client_id},
    )
    return response


@router.get("/logout")
async def logout_page(
    request: Request,
    client_id: str = "",
    redirect_uri: str = "",
):
    """Clear SSO cookie and revoke its access token."""
    if client_id or redirect_uri:
        if not client_id or not redirect_uri:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id and redirect_uri are required together")
        _ensure_client_redirect_allowed(client_id, redirect_uri)

    sso_token = request.cookies.get(settings.SSO_COOKIE_NAME)
    if sso_token:
        await denylist_access_token(sso_token)
        emit_audit_event(
            request,
            action="ui_logout",
            outcome="success",
            client_id=client_id or "",
            details={"client_id": client_id or ""},
        )
    else:
        emit_audit_event(
            request,
            action="ui_logout",
            outcome="success",
            client_id=client_id or "",
            details={"client_id": client_id or "", "cookie_present": False},
        )

    if client_id and redirect_uri:
        target = _build_redirect(
            "/ui/login",
            {"client_id": client_id, "redirect_uri": redirect_uri},
        )
    else:
        target = "/"

    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.SSO_COOKIE_NAME, domain=settings.SSO_COOKIE_DOMAIN)
    return response


@router.get("/register")
async def register_page(
    request: Request,
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
):
    """Render registration page."""
    _ensure_client_redirect_allowed(client_id, redirect_uri)

    csrf_token = _csrf_token()
    response = templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state or "",
            "csrf_token": csrf_token,
            "error": "",
        },
    )
    response.set_cookie("csrf_token", csrf_token, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
    return response


@router.post("/register")
@limiter.limit(settings.RATE_LIMIT_UI_REGISTER)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    csrf_token: str = Form(...),
    state: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Process registration form and continue to login flow."""
    _ensure_client_redirect_allowed(client_id, redirect_uri)

    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or cookie_csrf != csrf_token:
        emit_audit_event(
            request,
            action="ui_register",
            outcome="forbidden_csrf",
            email=email,
            client_id=client_id,
            details={"client_id": client_id},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    existing_user = await UserCRUD.get_user_by_email(db, email)
    if existing_user:
        emit_audit_event(
            request,
            action="ui_register",
            outcome="failure",
            email=email,
            client_id=client_id,
            details={"client_id": client_id},
        )
        new_csrf = _csrf_token()
        response = templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "csrf_token": new_csrf,
                "error": "Email already registered",
            },
            status_code=status.HTTP_409_CONFLICT,
        )
        response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
        return response

    user_data = UserCreate(email=email, password=password, full_name=full_name)
    created_user = await UserCRUD.create_user(db, user_data)
    emit_audit_event(
        request,
        action="ui_register",
        outcome="success",
        user_id=created_user.id,
        email=created_user.email,
        role=created_user.role.value,
        client_id=client_id,
        details={"client_id": client_id},
    )

    login_url = _build_redirect(
        "/ui/login",
        {"client_id": client_id, "redirect_uri": redirect_uri, "state": state},
    )
    return RedirectResponse(login_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/forgot-password")
async def forgot_password_page(
    request: Request,
    client_id: str = "",
    redirect_uri: str | None = None,
):
    """Render forgot-password page."""
    if redirect_uri or client_id:
        if not redirect_uri or not client_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id and redirect_uri are required together")
        _ensure_client_redirect_allowed(client_id, redirect_uri)

    csrf_token = _csrf_token()
    response = templates.TemplateResponse(
        "forgot_password.html",
        {
            "request": request,
            "client_id": client_id,
            "redirect_uri": redirect_uri or "",
            "csrf_token": csrf_token,
            "error": "",
            "message": "",
        },
    )
    response.set_cookie("csrf_token", csrf_token, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
    return response


@router.post("/forgot-password")
@limiter.limit(settings.RATE_LIMIT_FORGOT_PASSWORD)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    client_id: str = Form(""),
    redirect_uri: str = Form(""),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle forgot-password form and emit reset token (placeholder log)."""
    if redirect_uri or client_id:
        if not redirect_uri or not client_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id and redirect_uri are required together")
        _ensure_client_redirect_allowed(client_id, redirect_uri)

    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or cookie_csrf != csrf_token:
        emit_audit_event(request, action="ui_password_reset_requested", outcome="forbidden_csrf", email=email)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    user = await UserCRUD.get_user_by_email(db, email)
    if user and user.is_active:
        reset_token = create_password_reset_token(user.email, user.id)
        await send_password_reset_email(user.email, reset_token)
        emit_audit_event(
            request,
            action="ui_password_reset_requested",
            outcome="success",
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )
    else:
        emit_audit_event(request, action="ui_password_reset_requested", outcome="accepted", email=email)

    new_csrf = _csrf_token()
    response = templates.TemplateResponse(
        "forgot_password.html",
        {
            "request": request,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "csrf_token": new_csrf,
            "error": "",
            "message": "If the account exists, a password reset link was sent.",
        },
        status_code=status.HTTP_200_OK,
    )
    response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
    return response


@router.get("/reset-password")
async def reset_password_page(
    request: Request,
    token: str,
    client_id: str = "",
    redirect_uri: str | None = None,
):
    """Render reset-password page for a specific reset token."""
    if redirect_uri or client_id:
        if not redirect_uri or not client_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id and redirect_uri are required together")
        _ensure_client_redirect_allowed(client_id, redirect_uri)

    csrf_token = _csrf_token()
    response = templates.TemplateResponse(
        "reset_password.html",
        {
            "request": request,
            "token": token,
            "client_id": client_id,
            "redirect_uri": redirect_uri or "",
            "csrf_token": csrf_token,
            "error": "",
            "message": "",
        },
    )
    response.set_cookie("csrf_token", csrf_token, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
    return response


@router.post("/reset-password")
@limiter.limit(settings.RATE_LIMIT_RESET_PASSWORD)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    client_id: str = Form(""),
    redirect_uri: str = Form(""),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle reset-password form submission."""
    if redirect_uri or client_id:
        if not redirect_uri or not client_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id and redirect_uri are required together")
        _ensure_client_redirect_allowed(client_id, redirect_uri)

    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or cookie_csrf != csrf_token:
        emit_audit_event(request, action="ui_password_reset", outcome="forbidden_csrf")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    if new_password != confirm_password:
        emit_audit_event(request, action="ui_password_reset", outcome="failure")
        new_csrf = _csrf_token()
        response = templates.TemplateResponse(
            "reset_password.html",
            {
                "request": request,
                "token": token,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "csrf_token": new_csrf,
                "error": "Passwords do not match",
                "message": "",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
        return response

    payload = verify_token(token, token_type="password_reset")
    if not payload:
        emit_audit_event(request, action="ui_password_reset", outcome="failure")
        new_csrf = _csrf_token()
        response = templates.TemplateResponse(
            "reset_password.html",
            {
                "request": request,
                "token": token,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "csrf_token": new_csrf,
                "error": "Invalid or expired reset token",
                "message": "",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
        return response

    user_id = payload.get("sub")
    user = await UserCRUD.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        emit_audit_event(request, action="ui_password_reset", outcome="failure", user_id=user_id)
        new_csrf = _csrf_token()
        response = templates.TemplateResponse(
            "reset_password.html",
            {
                "request": request,
                "token": token,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "csrf_token": new_csrf,
                "error": "User not found or inactive",
                "message": "",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
        response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
        return response

    await UserCRUD.update_password(db, user.id, hash_password(new_password))
    emit_audit_event(
        request,
        action="ui_password_reset",
        outcome="success",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )

    new_csrf = _csrf_token()
    response = templates.TemplateResponse(
        "reset_password.html",
        {
            "request": request,
            "token": token,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "csrf_token": new_csrf,
            "error": "",
            "message": "Password updated successfully. You can now sign in.",
        },
        status_code=status.HTTP_200_OK,
    )
    response.set_cookie("csrf_token", new_csrf, httponly=True, samesite="lax", secure=settings.SSO_COOKIE_SECURE)
    return response
