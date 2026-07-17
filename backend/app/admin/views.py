from typing import Any

from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, OperationColumnFilter, StaticValuesFilter
from sqladmin.widgets import BooleanInputWidget
from sqlalchemy import select
from sqlalchemy.sql.expression import Select
from starlette.requests import Request
from wtforms import PasswordField
from wtforms.validators import Length

from app.core.security import hash_password
from app.models.attendance import AttendanceRecord
from app.models.event import Event, EventPhoto
from app.models.group import Group
from app.models.guest_claim import GuestClaim
from app.models.result import Result
from app.models.runner_baseline import RunnerBaseline
from app.models.signup import Signup
from app.models.user import User

# sqladmin 0.28's BooleanInputWidget subclasses wtforms' raw `Input` widget without
# setting `validation_attrs`, which `Input.__call__` requires as of wtforms 3.2 —
# renders (e.g. the create/edit form for `User.email_verified`) crash with
# `AttributeError: 'BooleanInputWidget' object has no attribute 'validation_attrs'`.
# Patch the missing attribute rather than pin around it, since builtin wtforms
# widgets already define their own `validation_attrs` and are unaffected.
if not hasattr(BooleanInputWidget, "validation_attrs"):
    BooleanInputWidget.validation_attrs = []


class BaseAdmin(ModelView):
    """Shared defaults for every SQLAdmin view — 25/page instead of the
    default 10, so a name/date/status search doesn't need to hop pages."""

    page_size = 25
    page_size_options = [25, 50, 100]


class UserAdmin(BaseAdmin, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"
    column_list = [
        User.id,
        User.first_name,
        User.last_name,
        User.email,
        User.role,
        User.email_verified,
        User.city,
        User.is_guest,
        User.merged_into,
    ]
    column_searchable_list = [User.first_name, User.last_name, User.email]
    column_sortable_list = [User.id, User.last_name, User.role]
    column_filters = [
        StaticValuesFilter(
            User.role,
            title="Роль",
            values=[("runner", "Бегун"), ("organizer", "Организатор"), ("admin", "Админ")],
        ),
        BooleanFilter(User.is_guest, title="Гостевой аккаунт"),
    ]
    form_excluded_columns = [User.signups, User.attendance_records]

    # `password_hash` is a real (NOT NULL) column, so it can't just be excluded from
    # the form — there'd be no way to set it when creating a user, and the insert
    # would fail a NOT NULL constraint. Show it only on the *create* form (relabelled
    # "Password", masked, hashed in on_model_change below) and keep it off the *edit*
    # form entirely, so editing a user never risks overwriting/exposing the hash.
    _editable_fields = [
        "first_name",
        "last_name",
        "email",
        "role",
        "email_verified",
        "city",
        "gender",
        "birthday",
        "phone",
        "avatar",
    ]
    form_create_rules = [*_editable_fields, "password_hash"]
    form_edit_rules = _editable_fields

    form_overrides = {"password_hash": PasswordField}
    form_args = {"password_hash": {"label": "Password", "validators": [Length(min=8)]}}

    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        if is_created and data.get("password_hash"):
            data["password_hash"] = hash_password(data["password_hash"])


class EventAdmin(BaseAdmin, model=Event):
    name = "Событие"
    name_plural = "События"
    icon = "fa-solid fa-calendar"
    column_list = [Event.id, Event.title, Event.date, Event.creator]
    column_searchable_list = [Event.title]
    column_sortable_list = [Event.id, Event.date]
    column_filters = [OperationColumnFilter(Event.date, title="Дата")]


class EventPhotoAdmin(BaseAdmin, model=EventPhoto):
    name = "Фото события"
    name_plural = "Фотографии событий"
    icon = "fa-solid fa-image"
    column_list = [EventPhoto.id, EventPhoto.event, EventPhoto.image, EventPhoto.thumbnail]


class GroupAdmin(BaseAdmin, model=Group):
    name = "Группа"
    name_plural = "Группы"
    icon = "fa-solid fa-people-group"
    column_list = [
        Group.id,
        Group.event,
        Group.location,
        Group.name,
        Group.distance_code,
        Group.target_distance_km,
        Group.start_time,
        Group.counts_toward_rating,
    ]
    column_searchable_list = [Group.name, Group.location]
    column_filters = [BooleanFilter(Group.counts_toward_rating, title="Учитывается в рейтинге")]


class SignupAdmin(BaseAdmin, model=Signup):
    name = "Запись на группу"
    name_plural = "Записи на группы"
    icon = "fa-solid fa-clipboard-check"
    column_list = [Signup.id, Signup.runner, Signup.group, Signup.created_at]
    column_filters = [OperationColumnFilter(Signup.created_at, title="Дата записи")]


class AttendanceRecordAdmin(BaseAdmin, model=AttendanceRecord):
    name = "Факт участия"
    name_plural = "Протокол (факты участия)"
    icon = "fa-solid fa-list-check"
    column_list = [
        AttendanceRecord.id,
        AttendanceRecord.group,
        AttendanceRecord.raw_name,
        AttendanceRecord.runner,
        AttendanceRecord.finish_status,
    ]
    column_searchable_list = [AttendanceRecord.raw_name, AttendanceRecord.raw_email]
    column_filters = [
        StaticValuesFilter(
            AttendanceRecord.finish_status,
            title="Статус",
            values=[("finished", "Пробежал"), ("dnf", "DNF")],
        ),
        # AttendanceRecord itself has no date column — the group's parent
        # event does, and that's what "when did this happen" actually means
        # here. Requires the base query to join group -> event (below).
        OperationColumnFilter(Event.date, title="Дата события"),
    ]

    def list_query(self, request: Request) -> Select[tuple[AttendanceRecord]]:
        return (
            select(AttendanceRecord)
            .join(Group, AttendanceRecord.group_id == Group.id)
            .join(Event, Group.event_id == Event.id)
        )


class GuestClaimAdmin(BaseAdmin, model=GuestClaim):
    name = "Заявка на объединение"
    name_plural = "Заявки на объединение"
    icon = "fa-solid fa-user-check"
    column_list = [
        GuestClaim.id,
        GuestClaim.guest,
        GuestClaim.claimant,
        GuestClaim.status,
        GuestClaim.created_at,
        GuestClaim.decided_at,
    ]
    column_sortable_list = [GuestClaim.id, GuestClaim.status]
    column_filters = [
        StaticValuesFilter(
            GuestClaim.status,
            title="Статус",
            values=[
                ("pending", "На рассмотрении"),
                ("approved", "Одобрена"),
                ("rejected", "Отклонена"),
            ],
        ),
    ]
    # Normal handling is the /admin-tools/claims queue (which also performs the
    # merge on approval) — this view is a fallback for inspecting/correcting
    # stray records, not the everyday moderation path.
    form_columns = [GuestClaim.status, GuestClaim.decided_at]


class ResultAdmin(BaseAdmin, model=Result):
    name = "Результат"
    name_plural = "Результаты"
    icon = "fa-solid fa-stopwatch"
    column_list = [
        Result.id,
        Result.attendance_record,
        Result.distance_km,
        Result.duration_seconds,
        Result.finish_status,
        Result.status,
        Result.source,
    ]
    column_sortable_list = [Result.id, Result.status, Result.finish_status]
    column_filters = [
        StaticValuesFilter(
            Result.status,
            title="Модерация",
            values=[("pending", "На проверке"), ("approved", "Подтверждён")],
        ),
        StaticValuesFilter(
            Result.finish_status,
            title="Статус",
            values=[("finished", "Пробежал"), ("dnf", "DNF")],
        ),
    ]
    # Admin approves results by editing the `status` field here.
    form_columns = [
        Result.distance_km,
        Result.duration_seconds,
        Result.pace_seconds_per_km,
        Result.start_time,
        Result.finish_status,
        Result.status,
    ]


class RunnerBaselineAdmin(BaseAdmin, model=RunnerBaseline):
    name = "Стартовые показатели"
    name_plural = "Стартовые показатели"
    icon = "fa-solid fa-clock-rotate-left"
    column_list = [
        RunnerBaseline.id,
        RunnerBaseline.runner,
        RunnerBaseline.dx_count,
        RunnerBaseline.total_runs,
        RunnerBaseline.total_km,
    ]
    # Carry-over totals from before this platform existed (e.g. a runner's
    # community history that predates CSV imports) — admin-only, never
    # editable by the runner themselves. Folded into lifetime totals and the
    # all-time rating/leaderboard only (see app.services.baseline_service).
    form_columns = [
        RunnerBaseline.runner,
        RunnerBaseline.dx_count,
        RunnerBaseline.total_runs,
        RunnerBaseline.total_km,
    ]


ALL_VIEWS = [
    UserAdmin,
    EventAdmin,
    EventPhotoAdmin,
    GroupAdmin,
    SignupAdmin,
    AttendanceRecordAdmin,
    ResultAdmin,
    GuestClaimAdmin,
    RunnerBaselineAdmin,
]
