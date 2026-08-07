import logging
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.email import build_frontend_link, render_email_html, send_email
from app.core.net import client_ip
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
from app.services import rate_guard
from app.services.captcha_service import verify_captcha

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("app.auth")

# 428 Precondition Required — the frontend reads this status as "show the
# captcha, then resubmit with a token" (see api/client.ts and the auth pages).
CAPTCHA_REQUIRED = HTTPException(
    status.HTTP_428_PRECONDITION_REQUIRED, "Подтвердите, что вы не робот"
)


async def _require_captcha_if_gated(
    scope: str, threshold: int, ip: str | None, token: str | None
) -> None:
    """Enforce a captcha only once the adaptive gate has flagged this IP."""
    if not settings.captcha_enabled:
        return
    if rate_guard.should_challenge(scope, ip, threshold) and not await verify_captcha(token, ip):
        raise CAPTCHA_REQUIRED


@router.get("/captcha-config")
async def captcha_config() -> dict[str, object]:
    """Public: lets the SPA render the widget with the right key, or skip it
    entirely when captcha isn't configured."""
    return {
        "enabled": settings.captcha_enabled,
        "client_key": settings.smartcaptcha_client_key or None,
    }


GENERIC_REGISTER_OK = MessageResponse(
    detail="Registration successful. Check your email to verify."
)


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, request: Request, session: SessionDep
) -> MessageResponse:
    ip = client_ip(request)
    await _require_captcha_if_gated(
        "register", settings.captcha_register_threshold, ip, payload.captcha_token
    )
    # Registration abuse is about volume, not correctness — every attempt counts
    # toward the gate, so a flood from one IP starts hitting the captcha.
    rate_guard.record("register", ip)

    existing = await session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        # Never reveal that an address is already taken (email enumeration):
        # return the same generic response either way. For the real owner we
        # still do something useful — re-send verification if they never
        # confirmed — but a stranger probing addresses learns nothing.
        if not existing.email_verified:
            link = build_frontend_link("/verify-email", create_email_token(existing.email, VERIFY))
            try:
                await send_email(
                    existing.email,
                    "Подтвердите почту — DАЙ ХАРD",
                    f"Похоже, вы уже начинали регистрацию в DАЙ ХАРD.\n\n"
                    f"Подтвердите почту, чтобы войти: {link}\n\n"
                    "Если это были не вы — просто проигнорируйте письмо.",
                    render_email_html(
                        "verify_email.html", first_name=existing.first_name, link=link
                    ),
                )
            except Exception:
                logger.exception("Re-send of verification email failed for %s", payload.email)
        return GENERIC_REGISTER_OK

    user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        privacy_accepted_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()

    token = create_email_token(user.email, VERIFY)
    link = build_frontend_link("/verify-email", token)
    # The account is only committed once the verification email is actually
    # accepted for delivery — if SMTP is down/misconfigured, roll back so no
    # unverifiable, un-loginnable account is left behind blocking a clean retry
    # (the account can't be used without verifying anyway).
    try:
        await send_email(
            user.email,
            "Подтвердите почту — DАЙ ХАРD",
            f"Добро пожаловать в DАЙ ХАРD, {user.first_name}!\n\n"
            f"Подтвердите почту, чтобы начать бегать с сообществом: {link}\n\n"
            "Если вы не регистрировались — просто проигнорируйте это письмо.",
            render_email_html("verify_email.html", first_name=user.first_name, link=link),
        )
    except Exception:
        await session.rollback()
        logger.exception("Verification email failed for %s; rolled back", payload.email)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Не удалось отправить письмо для подтверждения почты. Попробуйте позже.",
        ) from None

    await session.commit()
    return GENERIC_REGISTER_OK


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
async def login(payload: LoginRequest, request: Request, session: SessionDep) -> TokenPair:
    ip = client_ip(request)
    await _require_captcha_if_gated(
        "login", settings.captcha_login_threshold, ip, payload.captcha_token
    )

    user = await session.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        # Count wrong-credential attempts so brute force trips the captcha gate.
        rate_guard.record("login", ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    # Reaching here means the password was correct, so revealing "not verified"
    # leaks nothing an attacker couldn't already tell — it's the owner's cue to
    # confirm their email, not an enumeration vector.
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")
    rate_guard.reset("login", ip)
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
        # Never let an email failure change the response — it would both leak
        # which addresses are registered (500 vs 200) and crash the request.
        try:
            await send_email(
                user.email,
                "Восстановление пароля — DАЙ ХАРD",
                f"Ссылка для сброса пароля (действует 2 часа): {link}\n\n"
                "Если вы не запрашивали сброс — просто проигнорируйте это письмо.",
                render_email_html("reset_password.html", link=link),
            )
        except Exception:
            logger.exception("Password-reset email failed for %s", payload.email)
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
