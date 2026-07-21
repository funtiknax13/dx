from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.email import build_frontend_link, render_email_html, send_email
from app.core.security import (
    REFRESH,
    RESET,
    VERIFY,
    create_access_token,
    create_email_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> MessageResponse:
    existing = await session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        privacy_accepted_at=datetime.now(UTC),
    )
    session.add(user)
    await session.commit()

    token = create_email_token(user.email, VERIFY)
    link = build_frontend_link("/verify-email", token)
    await send_email(
        user.email,
        "Подтвердите почту — DАЙ ХАРD",
        f"Добро пожаловать в DАЙ ХАРD, {user.first_name}!\n\n"
        f"Подтвердите почту, чтобы начать бегать с сообществом: {link}\n\n"
        "Если вы не регистрировались — просто проигнорируйте это письмо.",
        render_email_html("verify_email.html", first_name=user.first_name, link=link),
    )
    return MessageResponse(detail="Registration successful. Check your email to verify.")


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, session: SessionDep) -> MessageResponse:
    try:
        email = decode_token(token, VERIFY)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token") from exc

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.email_verified = True
    await session.commit()
    return MessageResponse(detail="Email verified. You can now log in.")


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: SessionDep) -> TokenPair:
    user = await session.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    try:
        user_id = int(decode_token(payload.refresh_token, REFRESH))
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, session: SessionDep) -> MessageResponse:
    user = await session.scalar(select(User).where(User.email == payload.email))
    # Always return the same response to avoid leaking which emails are registered.
    if user is not None:
        token = create_email_token(user.email, RESET, hours=2)
        link = build_frontend_link("/reset-password", token)
        await send_email(
            user.email,
            "Восстановление пароля — DАЙ ХАРD",
            f"Ссылка для сброса пароля (действует 2 часа): {link}\n\n"
            "Если вы не запрашивали сброс — просто проигнорируйте это письмо.",
            render_email_html("reset_password.html", link=link),
        )
    return MessageResponse(detail="If that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, session: SessionDep) -> MessageResponse:
    try:
        email = decode_token(payload.token, RESET)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token") from exc

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return MessageResponse(detail="Password updated. You can now log in.")
