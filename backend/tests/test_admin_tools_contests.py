import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.contest import Contest, ContestEntry, ContestField
from app.models.enums import ModerationStatus, StaffPermission, UserRole
from app.models.support import SupportMessage, SupportTicket
from app.services.permissions_service import set_permissions
from tests.factories import add_contest_field, make_contest, make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


async def _organizer_with_contests(session: AsyncSession, email: str, admin) -> "object":
    org = await make_user(session, email, UserRole.organizer)
    await set_permissions(session, org, {StaffPermission.contests}, granted_by=admin)
    return org


# --- access control -----------------------------------------------------


@pytest.mark.asyncio
async def test_contests_page_requires_permission(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-ac1@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/contests", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_organizer_only_sees_own_contests(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-ac2@example.com", UserRole.admin)
    org_a = await _organizer_with_contests(session, "org-ac2a@example.com", admin)
    org_b = await _organizer_with_contests(session, "org-ac2b@example.com", admin)
    contest_a = await make_contest(session, org_a)
    await make_contest(session, org_b)
    await session.commit()
    await _login(client, org_a.id)

    resp = await client.get("/admin-tools/contests")
    assert resp.status_code == 200
    assert contest_a.title in resp.text
    # Only one contest row (org_a's) — org_b's never rendered.
    assert resp.text.count('href="/admin-tools/contests/') >= 1


@pytest.mark.asyncio
async def test_organizer_cannot_edit_another_organizers_contest(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ac3@example.com", UserRole.admin)
    owner = await _organizer_with_contests(session, "owner-ac3@example.com", admin)
    other = await _organizer_with_contests(session, "other-ac3@example.com", admin)
    contest = await make_contest(session, owner)
    await session.commit()
    await _login(client, other.id)

    resp = await client.get(f"/admin-tools/contests/{contest.id}/edit", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin-tools/contests"


# --- constructor -----------------------------------------------------


@pytest.mark.asyncio
async def test_create_contest_with_fields(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-ctor1@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-ctor1@example.com", admin)
    await session.commit()
    await _login(client, org.id)

    fields_json = json.dumps(
        [
            {
                "id": None,
                "label": "Ссылка на маршрут",
                "description": "Strava/Garmin",
                "field_type": "url",
                "required": True,
                "visible_to_voters": True,
            },
            {
                "id": None,
                "label": "Фото",
                "description": "",
                "field_type": "image",
                "required": False,
                "visible_to_voters": False,
            },
        ]
    )
    resp = await client.post(
        "/admin-tools/contests/new",
        data={
            "title": "Конкурс маршрутов",
            "description": "Условия тут",
            "submissions_open_at": "",
            "submissions_close_at": "",
            "voting_open_at": "",
            "voting_close_at": "",
            "fields": fields_json,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    contest = await session.scalar(select(Contest).where(Contest.title == "Конкурс маршрутов"))
    assert contest is not None
    assert contest.is_published is False
    fields = list(
        await session.scalars(
            select(ContestField)
            .where(ContestField.contest_id == contest.id)
            .order_by(ContestField.position)
        )
    )
    assert [f.label for f in fields] == ["Ссылка на маршрут", "Фото"]
    assert fields[1].visible_to_voters is False


@pytest.mark.asyncio
async def test_edit_contest_syncs_fields_add_update_remove(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ctor2@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-ctor2@example.com", admin)
    contest = await make_contest(session, org)
    keep_field = await add_contest_field(session, contest, position=0, label="Держим")
    remove_field = await add_contest_field(session, contest, position=1, label="Удалим")
    await session.commit()
    keep_field_id, remove_field_id = keep_field.id, remove_field.id

    fields_json = json.dumps(
        [
            {
                "id": keep_field.id,
                "label": "Держим (переименовано)",
                "description": "",
                "field_type": "url",
                "required": True,
                "visible_to_voters": True,
            },
            {
                "id": None,
                "label": "Новое поле",
                "description": "",
                "field_type": "text",
                "required": False,
                "visible_to_voters": True,
            },
        ]
    )
    contest_id, contest_title = contest.id, contest.title
    await _login(client, org.id)
    resp = await client.post(
        f"/admin-tools/contests/{contest_id}/edit",
        data={
            "title": contest_title,
            "description": "",
            "submissions_open_at": "",
            "submissions_close_at": "",
            "voting_open_at": "",
            "voting_close_at": "",
            "fields": fields_json,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    session.expire_all()

    remaining = list(
        await session.scalars(
            select(ContestField)
            .where(ContestField.contest_id == contest_id)
            .order_by(ContestField.position)
        )
    )
    assert [f.label for f in remaining] == ["Держим (переименовано)", "Новое поле"]
    assert remaining[0].id == keep_field_id  # same row, updated in place
    assert await session.get(ContestField, remove_field_id) is None


@pytest.mark.asyncio
async def test_create_contest_with_multi_select_field_and_entries_cap(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ctor3@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-ctor3@example.com", admin)
    await session.commit()
    await _login(client, org.id)

    fields_json = json.dumps(
        [
            {
                "id": None,
                "label": "Сезонность",
                "description": "",
                "field_type": "multi_select",
                "required": True,
                "visible_to_voters": True,
                "options": ["Зима", "Весна", "", "Лето", "Осень"],
            }
        ]
    )
    resp = await client.post(
        "/admin-tools/contests/new",
        data={
            "title": "Конкурс сезонов",
            "description": "",
            "submissions_open_at": "",
            "submissions_close_at": "",
            "voting_open_at": "",
            "voting_close_at": "",
            "max_entries_per_runner": "3",
            "fields": fields_json,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    contest = await session.scalar(select(Contest).where(Contest.title == "Конкурс сезонов"))
    assert contest is not None
    assert contest.max_entries_per_runner == 3
    field = await session.scalar(select(ContestField).where(ContestField.contest_id == contest.id))
    assert field is not None
    # Blank option dropped, the rest kept in order.
    assert field.options == ["Зима", "Весна", "Лето", "Осень"]


@pytest.mark.asyncio
async def test_max_entries_per_runner_blank_means_unlimited(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ctor4@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-ctor4@example.com", admin)
    contest = await make_contest(session, org, max_entries_per_runner=5)
    await session.commit()
    contest_id, contest_title = contest.id, contest.title
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/contests/{contest_id}/edit",
        data={
            "title": contest_title,
            "description": "",
            "submissions_open_at": "",
            "submissions_close_at": "",
            "voting_open_at": "",
            "voting_close_at": "",
            "max_entries_per_runner": "",
            "fields": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    session.expire_all()
    refreshed = await session.get(Contest, contest_id)
    assert refreshed is not None
    assert refreshed.max_entries_per_runner is None


@pytest.mark.asyncio
async def test_publish_and_unpublish_toggle(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-pub1@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-pub1@example.com", admin)
    contest = await make_contest(session, org, is_published=False)
    await session.commit()
    await _login(client, org.id)

    resp = await client.post(f"/admin-tools/contests/{contest.id}/publish", follow_redirects=False)
    assert resp.status_code == 303
    await session.refresh(contest)
    assert contest.is_published is True

    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/unpublish", follow_redirects=False
    )
    assert resp.status_code == 303
    await session.refresh(contest)
    assert contest.is_published is False


# --- moderation -----------------------------------------------------


@pytest.mark.asyncio
async def test_approve_entry(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-mod1@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-mod1@example.com", admin)
    runner = await make_user(session, "runner-mod1@example.com")
    contest = await make_contest(session, org)
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.pending,
        submitted_at=contest.created_at,
    )
    session.add(entry)
    await session.commit()
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/entries/{entry.id}/approve", follow_redirects=False
    )
    assert resp.status_code == 303
    await session.refresh(entry)
    assert entry.status == ModerationStatus.approved


@pytest.mark.asyncio
async def test_contests_review_only_user_can_approve_entry_not_owned(
    session: AsyncSession, client: AsyncClient
) -> None:
    """contests_review is deliberately global (not ownership-scoped, unlike
    `contests`) — see _get_contest_for_moderation — so a reviewer can
    moderate a contest someone else created without being granted
    `contests` at all."""
    admin = await make_user(session, "admin-mod3@example.com", UserRole.admin)
    owner = await _organizer_with_contests(session, "owner-mod3@example.com", admin)
    reviewer = await make_user(session, "reviewer-mod3@example.com", UserRole.organizer)
    await set_permissions(session, reviewer, {StaffPermission.contests_review}, granted_by=admin)
    runner = await make_user(session, "runner-mod3@example.com")
    contest = await make_contest(session, owner)
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.pending,
        submitted_at=contest.created_at,
    )
    session.add(entry)
    await session.commit()
    await _login(client, reviewer.id)

    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/entries/{entry.id}/approve", follow_redirects=False
    )
    assert resp.status_code == 303
    await session.refresh(entry)
    assert entry.status == ModerationStatus.approved


@pytest.mark.asyncio
async def test_user_with_neither_contests_permission_is_blocked(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-mod4@example.com", UserRole.admin)
    owner = await _organizer_with_contests(session, "owner-mod4@example.com", admin)
    bystander = await make_user(session, "bystander-mod4@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-mod4@example.com")
    contest = await make_contest(session, owner)
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.pending,
        submitted_at=contest.created_at,
    )
    session.add(entry)
    await session.commit()
    await _login(client, bystander.id)

    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/entries/{entry.id}/approve", follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"
    await session.refresh(entry)
    assert entry.status == ModerationStatus.pending


@pytest.mark.asyncio
async def test_contest_entries_inbox_requires_contests_review(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Owning contests (`contests` only, no `contests_review`) is not enough
    for the cross-contest inbox — that one's reserved for the broad,
    delegable-to-anyone review right."""
    admin = await make_user(session, "admin-inbox1@example.com", UserRole.admin)
    owner = await _organizer_with_contests(session, "owner-inbox1@example.com", admin)
    await session.commit()
    await _login(client, owner.id)

    resp = await client.get("/admin-tools/contest-entries", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_contest_entries_inbox_lists_pending_across_contests(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-inbox2@example.com", UserRole.admin)
    owner_a = await _organizer_with_contests(session, "owner-inbox2a@example.com", admin)
    owner_b = await _organizer_with_contests(session, "owner-inbox2b@example.com", admin)
    reviewer = await make_user(session, "reviewer-inbox2@example.com", UserRole.organizer)
    await set_permissions(session, reviewer, {StaffPermission.contests_review}, granted_by=admin)
    runner = await make_user(session, "runner-inbox2@example.com")

    contest_a = await make_contest(session, owner_a)
    contest_b = await make_contest(session, owner_b)
    pending_a = ContestEntry(
        contest_id=contest_a.id,
        runner_id=runner.id,
        status=ModerationStatus.pending,
        submitted_at=contest_a.created_at,
    )
    pending_b = ContestEntry(
        contest_id=contest_b.id,
        runner_id=runner.id,
        status=ModerationStatus.pending,
        submitted_at=contest_b.created_at,
    )
    session.add_all([pending_a, pending_b])
    await session.flush()
    # An already-approved entry elsewhere must not show up in this inbox —
    # it's specifically a pending-only queue, like /admin-tools/results.
    approved_runner = await make_user(session, "runner-inbox2b@example.com")
    approved = ContestEntry(
        contest_id=contest_a.id,
        runner_id=approved_runner.id,
        status=ModerationStatus.approved,
        submitted_at=contest_a.created_at,
    )
    session.add(approved)
    await session.commit()
    await _login(client, reviewer.id)

    resp = await client.get("/admin-tools/contest-entries")
    assert resp.status_code == 200
    assert contest_a.title in resp.text
    assert f"/admin-tools/contests/{contest_a.id}/entries/{pending_a.id}/approve" in resp.text
    assert f"/admin-tools/contests/{contest_b.id}/entries/{pending_b.id}/approve" in resp.text
    assert f"/admin-tools/contests/{contest_a.id}/entries/{approved.id}/approve" not in resp.text


@pytest.mark.asyncio
async def test_reject_entry_sets_reason_and_notifies(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-mod2@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-mod2@example.com", admin)
    runner = await make_user(session, "runner-mod2@example.com")
    contest = await make_contest(session, org)
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.pending,
        submitted_at=contest.created_at,
    )
    session.add(entry)
    await session.commit()
    runner_id, entry_id = runner.id, entry.id
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/entries/{entry_id}/reject",
        data={"reason": "Нет обязательных данных"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    await session.refresh(entry)
    assert entry.status == ModerationStatus.rejected
    assert entry.rejection_reason == "Нет обязательных данных"

    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
    )
    assert ticket is not None
    msg = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
    assert msg is not None
    assert "Нет обязательных данных" in msg.body


# --- results -----------------------------------------------------


@pytest.mark.asyncio
async def test_set_placement_and_publish_results(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-res1@example.com", UserRole.admin)
    org = await _organizer_with_contests(session, "org-res1@example.com", admin)
    runner = await make_user(session, "runner-res1@example.com")
    contest = await make_contest(session, org)
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.approved,
        submitted_at=contest.created_at,
    )
    session.add(entry)
    await session.commit()
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/results/{entry.id}/placement",
        data={"placement": "1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    await session.refresh(entry)
    assert entry.placement == 1

    assert contest.results_published_at is None
    resp = await client.post(
        f"/admin-tools/contests/{contest.id}/results/publish", follow_redirects=False
    )
    assert resp.status_code == 303
    await session.refresh(contest)
    assert contest.results_published_at is not None
