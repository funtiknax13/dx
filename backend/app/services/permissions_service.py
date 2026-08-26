"""The flexible replacement for the old blanket `role == admin` gate on
individual admin-tools moderation pages — see StaffPermission for the
catalog and app.admin.tools_permissions for the (admin-only, not itself
delegable) page that manages grants."""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffPermission, UserRole
from app.models.organizer_permission import OrganizerPermission
from app.models.user import User


@dataclass(frozen=True)
class PermissionMeta:
    label: str
    description: str


PERMISSION_META: dict[StaffPermission, PermissionMeta] = {
    StaffPermission.csv_import: PermissionMeta(
        "Импорт CSV и сопоставление участников",
        "Загрузка протокола события, привязка неопознанных записей к аккаунтам, поиск бегунов.",
    ),
    StaffPermission.guest_claims: PermissionMeta(
        "Заявки на объединение и гостевые профили",
        "Подтверждение заявок «это я», ручное объединение гостевых профилей.",
    ),
    StaffPermission.avatars: PermissionMeta(
        "Модерация аватаров",
        "Проверка загруженных фото профиля, удаление неподобающих.",
    ),
    StaffPermission.baselines: PermissionMeta(
        "Импорт стартовых данных",
        "Загрузка стартовой статистики бегунов из CSV.",
    ),
    StaffPermission.profile_review: PermissionMeta(
        "Модерация анкет",
        "Проверка изменений профиля бегунов (имя, город, дата рождения и т.д.).",
    ),
    StaffPermission.results_review: PermissionMeta(
        "Модерация результатов",
        "Подтверждение или отклонение загруженных результатов забегов.",
    ),
    StaffPermission.surveys: PermissionMeta(
        "Анкеты обратной связи",
        "Создание опросов для новичков, просмотр и выгрузка ответов.",
    ),
}


async def permissions_for(session: AsyncSession, user: User) -> set[StaffPermission]:
    """Every StaffPermission for admin (implicit, never stored); only what's
    been explicitly granted for an organizer; nothing for anyone else."""
    if user.role == UserRole.admin:
        return set(StaffPermission)
    if user.role != UserRole.organizer:
        return set()
    rows = await session.scalars(
        select(OrganizerPermission.permission).where(OrganizerPermission.user_id == user.id)
    )
    return set(rows)


async def set_permissions(
    session: AsyncSession,
    target: User,
    granted: set[StaffPermission],
    *,
    granted_by: User,
) -> None:
    """Replace target's full grant set with exactly `granted` — diffs against
    what's currently stored so only the rows that actually changed are
    touched."""
    if target.role != UserRole.organizer:
        raise ValueError("Permissions can only be granted to an organizer")
    current = await permissions_for(session, target)
    to_add = granted - current
    to_remove = current - granted
    if to_remove:
        await session.execute(
            delete(OrganizerPermission).where(
                OrganizerPermission.user_id == target.id,
                OrganizerPermission.permission.in_(to_remove),
            )
        )
    for perm in to_add:
        session.add(
            OrganizerPermission(user_id=target.id, permission=perm, granted_by_id=granted_by.id)
        )
