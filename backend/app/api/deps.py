from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import ACCESS, decode_token
from app.models.enums import UserRole
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)
bearer_scheme_optional = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: SessionDep,
) -> User:
    try:
        subject = decode_token(credentials.credentials, ACCESS)
        user_id = int(subject)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme_optional)],
    session: SessionDep,
) -> User | None:
    """Like get_current_user, but for public-but-personalizable endpoints — a
    missing or invalid token just means "anonymous", not a 401."""
    if credentials is None:
        return None
    try:
        subject = decode_token(credentials.credentials, ACCESS)
        user_id = int(subject)
    except (jwt.PyJWTError, ValueError):
        return None
    return await session.get(User, user_id)


OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


def require_roles(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return checker


require_admin = require_roles(UserRole.admin)
require_organizer = require_roles(UserRole.organizer, UserRole.admin)

AdminUser = Annotated[User, Depends(require_admin)]
OrganizerUser = Annotated[User, Depends(require_organizer)]
