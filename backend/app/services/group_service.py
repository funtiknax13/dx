from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group
from app.services.media_service import delete_media


async def set_group_route_gpx(session: AsyncSession, group: Group, new_path: str) -> None:
    """Replace a group's GPX route file, deleting the previous one only if no
    other group still points at it.

    Duplicating a group (admin-tools "Дублировать группу") intentionally
    copies the route_gpx path rather than the file itself, so pace groups
    running the same course share one physical file. Blindly deleting on
    every re-upload would silently break every other group still pointing
    at that shared file the moment any one of them gets a new route.
    """
    old_path = group.route_gpx
    if old_path and old_path != new_path:
        still_referenced = await session.scalar(
            select(Group.id).where(Group.route_gpx == old_path, Group.id != group.id).limit(1)
        )
        if still_referenced is None:
            delete_media(old_path)
    group.route_gpx = new_path
