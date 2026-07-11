import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User

logger = logging.getLogger("app.bootstrap")


async def ensure_initial_admin() -> None:
    """Create the first admin from env vars if no admin exists. Idempotent — safe on
    every startup. Solves the chicken-and-egg problem where roles are otherwise only
    assignable by an existing admin via SQLAdmin."""
    async with SessionLocal() as session:
        existing_admin = await session.scalar(
            select(User).where(User.role == UserRole.admin).limit(1)
        )
        if existing_admin is not None:
            return

        # Reuse an account that already has the bootstrap email, or create a new one.
        user = await session.scalar(
            select(User).where(User.email == settings.initial_admin_email)
        )
        if user is None:
            user = User(
                first_name="Admin",
                last_name="User",
                email=settings.initial_admin_email,
                password_hash=hash_password(settings.initial_admin_password),
            )
            session.add(user)
        user.role = UserRole.admin
        user.email_verified = True
        await session.commit()
        logger.info("Bootstrapped initial admin: %s", settings.initial_admin_email)
