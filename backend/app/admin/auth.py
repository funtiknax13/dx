from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from starlette.requests import Request

from app.core.db import SessionLocal
from app.core.security import verify_password
from app.models.enums import UserRole
from app.models.user import User

SESSION_KEY = "admin_user_id"


async def _admin_by_credentials(email: str, password: str) -> User | None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
    if user is None or user.role != UserRole.admin:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def is_admin_request(request: Request) -> bool:
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return False
    async with SessionLocal() as session:
        user = await session.get(User, int(user_id))
    return user is not None and user.role == UserRole.admin


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = str(form.get("username", ""))
        password = str(form.get("password", ""))
        user = await _admin_by_credentials(email, password)
        if user is None:
            return False
        request.session[SESSION_KEY] = str(user.id)
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return await is_admin_request(request)
