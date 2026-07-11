from typing import Any

from sqladmin import ModelView
from sqladmin.widgets import BooleanInputWidget
from starlette.requests import Request
from wtforms import PasswordField
from wtforms.validators import Length

from app.core.security import hash_password
from app.models.attendance import AttendanceRecord
from app.models.event import Event, EventPhoto
from app.models.group import Group
from app.models.guest_claim import GuestClaim
from app.models.result import Result
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


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
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


class EventAdmin(ModelView, model=Event):
    name = "Event"
    name_plural = "Events"
    icon = "fa-solid fa-calendar"
    column_list = [Event.id, Event.title, Event.date, Event.creator]
    column_searchable_list = [Event.title]
    column_sortable_list = [Event.id, Event.date]


class EventPhotoAdmin(ModelView, model=EventPhoto):
    name = "Event Photo"
    name_plural = "Event Photos"
    icon = "fa-solid fa-image"
    column_list = [EventPhoto.id, EventPhoto.event, EventPhoto.image, EventPhoto.thumbnail]


class GroupAdmin(ModelView, model=Group):
    name = "Group"
    name_plural = "Groups"
    icon = "fa-solid fa-people-group"
    column_list = [
        Group.id,
        Group.event,
        Group.location,
        Group.name,
        Group.target_distance_km,
        Group.start_time,
    ]
    column_searchable_list = [Group.name, Group.location]


class SignupAdmin(ModelView, model=Signup):
    name = "Signup"
    name_plural = "Signups"
    icon = "fa-solid fa-clipboard-check"
    column_list = [Signup.id, Signup.runner, Signup.group, Signup.created_at]


class AttendanceRecordAdmin(ModelView, model=AttendanceRecord):
    name = "Attendance Record"
    name_plural = "Attendance Records"
    icon = "fa-solid fa-list-check"
    column_list = [
        AttendanceRecord.id,
        AttendanceRecord.group,
        AttendanceRecord.raw_name,
        AttendanceRecord.runner,
        AttendanceRecord.finish_status,
    ]
    column_searchable_list = [AttendanceRecord.raw_name, AttendanceRecord.raw_email]


class GuestClaimAdmin(ModelView, model=GuestClaim):
    name = "Guest Claim"
    name_plural = "Guest Claims"
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
    # Normal handling is the /admin-tools/claims queue (which also performs the
    # merge on approval) — this view is a fallback for inspecting/correcting
    # stray records, not the everyday moderation path.
    form_columns = [GuestClaim.status, GuestClaim.decided_at]


class ResultAdmin(ModelView, model=Result):
    name = "Result"
    name_plural = "Results"
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
    # Admin approves results by editing the `status` field here.
    form_columns = [
        Result.distance_km,
        Result.duration_seconds,
        Result.pace_seconds_per_km,
        Result.start_time,
        Result.finish_status,
        Result.status,
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
]
