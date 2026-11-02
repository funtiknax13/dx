import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.contest import ContestEntry, ContestVote
from app.models.enums import ContestFieldType, ModerationStatus, PriorExperience
from app.models.profile_edit_request import ProfileEditRequest
from app.models.survey import Survey
from app.services.media_service import media_path_to_fs
from tests.factories import add_contest_field, make_contest, make_user

# Unlike test_contest_service.py (which injects `now=` directly), the API
# never receives a fake "now" — contest_phase() always uses the real wall
# clock — so these have to be real-time-relative, not a fixed fictional date.
PAST = datetime.now(UTC) - timedelta(days=10)
SOON = datetime.now(UTC) + timedelta(days=1)

_IMG = ("shot.png", b"fake-image-bytes", "image/png")
_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Test</name><trkseg>
    <trkpt lat="55.7500" lon="37.6200"><ele>150.0</ele><time>2026-05-01T08:00:00Z</time></trkpt>
    <trkpt lat="55.7510" lon="37.6210"><ele>152.0</ele><time>2026-05-01T08:05:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _open_contest(session: AsyncSession, org):
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
    )
    link = await add_contest_field(
        session, contest, position=0, label="Ссылка", field_type=ContestFieldType.url
    )
    photo = await add_contest_field(
        session,
        contest,
        position=1,
        label="Фото",
        field_type=ContestFieldType.image,
        required=False,
        visible_to_voters=False,
    )
    return contest, link, photo


# --- listing / detail -----------------------------------------------------


@pytest.mark.asyncio
async def test_list_contests_only_shows_published(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi1@example.com")
    published = await make_contest(session, org, is_published=True)
    await make_contest(session, org, is_published=False)
    await session.commit()

    resp = await client.get("/api/v1/contests")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [published.id]


@pytest.mark.asyncio
async def test_unpublished_contest_404s(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi2@example.com")
    draft = await make_contest(session, org, is_published=False)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{draft.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upcoming_contest_hides_fields(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi3@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=SOON)
    await add_contest_field(session, contest)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "upcoming"
    assert body["fields"] is None


@pytest.mark.asyncio
async def test_open_contest_shows_fields(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi4@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "submissions_open"
    assert [f["id"] for f in body["fields"]] == [link.id, photo.id]


# --- submission -----------------------------------------------------


@pytest.mark.asyncio
async def test_submit_entry_with_text_and_file_fields(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi5@example.com")
    runner = await make_user(session, "runner-capi5@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/route"},
        files={f"field_{photo.id}": _IMG},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    values = {v["field_id"]: v["value"] for v in body["values"]}
    assert values[link.id] == "https://example.com/route"
    photo_paths = json.loads(values[photo.id])
    assert photo_paths and all(p.startswith("/media/contests/") for p in photo_paths)


@pytest.mark.asyncio
async def test_submit_entry_missing_required_field_422s(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi6@example.com")
    runner = await make_user(session, "runner-capi6@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={},
    )
    assert resp.status_code == 422
    assert str(link.id) in resp.json()["detail"]["errors"]


@pytest.mark.asyncio
async def test_resubmit_keeps_file_when_not_reuploaded(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi7@example.com")
    runner = await make_user(session, "runner-capi7@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/a"},
        files={f"field_{photo.id}": _IMG},
    )
    assert first.status_code == 201, first.text
    entry_id = first.json()["id"]
    first_photo_path = {v["field_id"]: v["value"] for v in first.json()["values"]}[photo.id]

    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={"entry_id": str(entry_id), f"field_{link.id}": "https://example.com/b"},
    )
    assert second.status_code == 201, second.text
    second_values = {v["field_id"]: v["value"] for v in second.json()["values"]}
    assert second_values[link.id] == "https://example.com/b"
    assert second_values[photo.id] == first_photo_path  # untouched


@pytest.mark.asyncio
async def test_submit_multi_select_field_stores_selection(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-ms-api1@example.com")
    runner = await make_user(session, "runner-ms-api1@example.com")
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session,
        contest,
        field_type=ContestFieldType.multi_select,
        options=["Зима", "Весна", "Лето", "Осень"],
    )
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": json.dumps(["Зима", "Лето"])},
    )
    assert resp.status_code == 201, resp.text
    values = {v["field_id"]: v["value"] for v in resp.json()["values"]}
    assert json.loads(values[field.id]) == ["Зима", "Лето"]


@pytest.mark.asyncio
async def test_submit_several_images_rejects_more_than_configured_max(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-img-api1@example.com")
    runner = await make_user(session, "runner-img-api1@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    too_many = settings.contest_entry_max_images + 2
    files = [
        (f"field_{photo.id}", (f"shot{i}.png", b"fake-bytes", "image/png")) for i in range(too_many)
    ]
    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/route"},
        files=files,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_submit_second_entry_without_cap_creates_a_new_entry(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-multi-api1@example.com")
    runner = await make_user(session, "runner-multi-api1@example.com")
    contest, link, _photo = await _open_contest(session, org)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/a"},
    )
    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/b"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_submit_second_entry_blocked_once_cap_reached(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-multi-api2@example.com")
    runner = await make_user(session, "runner-multi-api2@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
        max_entries_per_runner=1,
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": "https://example.com/a"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": "https://example.com/b"},
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_submit_entry_blocked_outside_window(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi8@example.com")
    runner = await make_user(session, "runner-capi8@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": "https://example.com"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_my_entries_requires_auth_and_returns_empty_when_absent(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi9@example.com")
    runner = await make_user(session, "runner-capi9@example.com")
    contest, _link, _photo = await _open_contest(session, org)
    await session.commit()

    anon = await client.get(f"/api/v1/contests/{contest.id}/my-entries")
    assert anon.status_code == 401

    resp = await client.get(f"/api/v1/contests/{contest.id}/my-entries", headers=_auth(runner.id))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_my_entries_lists_all_of_a_runners_entries(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi9b@example.com")
    runner = await make_user(session, "runner-capi9b@example.com")
    contest, link, _photo = await _open_contest(session, org)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/first"},
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/second"},
    )
    assert second.status_code == 201, second.text

    resp = await client.get(f"/api/v1/contests/{contest.id}/my-entries", headers=_auth(runner.id))
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {first.json()["id"], second.json()["id"]}


# --- gpx route map -----------------------------------------------------


async def _contest_with_gpx_field(session: AsyncSession, org):
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session, contest, field_type=ContestFieldType.gpx, required=True, visible_to_voters=True
    )
    return contest, field


@pytest.mark.asyncio
async def test_entry_route_map_visible_to_owner_while_pending(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-gpx-api1@example.com")
    runner = await make_user(session, "runner-gpx-api1@example.com")
    contest, field = await _contest_with_gpx_field(session, org)
    await session.commit()

    submit = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        files={f"field_{field.id}": ("route.gpx", _GPX.encode(), "application/gpx+xml")},
    )
    assert submit.status_code == 201, submit.text
    entry_id = submit.json()["id"]

    resp = await client.get(
        f"/api/v1/contests/{contest.id}/entries/{entry_id}/values/{field.id}/route-map",
        headers=_auth(runner.id),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["track_points"]) == 2


@pytest.mark.asyncio
async def test_entry_route_map_hidden_from_others_before_approval(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-gpx-api2@example.com")
    runner = await make_user(session, "runner-gpx-api2@example.com")
    other = await make_user(session, "other-gpx-api2@example.com")
    contest, field = await _contest_with_gpx_field(session, org)
    await session.commit()

    submit = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        files={f"field_{field.id}": ("route.gpx", _GPX.encode(), "application/gpx+xml")},
    )
    entry_id = submit.json()["id"]

    resp = await client.get(
        f"/api/v1/contests/{contest.id}/entries/{entry_id}/values/{field.id}/route-map",
        headers=_auth(other.id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entry_route_map_visible_to_anyone_once_approved_during_voting(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-gpx-api3@example.com")
    author = await make_user(session, "author-gpx-api3@example.com")
    voter = await make_user(session, "voter-gpx-api3@example.com")
    contest, field = await _contest_with_gpx_field(session, org)
    await session.commit()

    submit = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(author.id),
        files={f"field_{field.id}": ("route.gpx", _GPX.encode(), "application/gpx+xml")},
    )
    assert submit.status_code == 201, submit.text
    entry_id = submit.json()["id"]

    entry = await session.get(ContestEntry, entry_id)
    assert entry is not None
    entry.status = ModerationStatus.approved
    contest.submissions_close_at = PAST + timedelta(days=1)
    contest.voting_open_at = PAST + timedelta(days=2)
    contest.voting_close_at = SOON
    await session.commit()

    resp = await client.get(
        f"/api/v1/contests/{contest.id}/entries/{entry_id}/values/{field.id}/route-map",
        headers=_auth(voter.id),
    )
    assert resp.status_code == 200, resp.text


# --- voting -----------------------------------------------------


async def _voting_contest_with_approved_entry(session: AsyncSession, org, author):
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=PAST + timedelta(days=2),
        voting_close_at=SOON,
    )
    field = await add_contest_field(
        session, contest, field_type=ContestFieldType.url, visible_to_voters=True
    )
    hidden_field = await add_contest_field(
        session,
        contest,
        position=1,
        label="Заметка для админа",
        field_type=ContestFieldType.text,
        required=False,
        visible_to_voters=False,
    )
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=author.id,
        status=ModerationStatus.approved,
        submitted_at=PAST,
    )
    session.add(entry)
    await session.flush()
    from app.models.contest import ContestEntryValue

    session.add(ContestEntryValue(entry_id=entry.id, field_id=field.id, value="https://x.com"))
    session.add(ContestEntryValue(entry_id=entry.id, field_id=hidden_field.id, value="secret"))
    await session.flush()
    return contest, entry, field, hidden_field


@pytest.mark.asyncio
async def test_entries_hidden_before_voting_opens(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi10@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=PAST)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}/entries")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


@pytest.mark.asyncio
async def test_entries_list_filters_hidden_fields_and_vote_counts(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi11@example.com")
    author = await make_user(session, "author-capi11@example.com")
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}/entries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["votes_visible"] is False
    assert len(body["entries"]) == 1
    entry_out = body["entries"][0]
    field_ids = [v["field_id"] for v in entry_out["values"]]
    assert field.id in field_ids
    assert hidden_field.id not in field_ids
    assert entry_out["vote_count"] is None  # votes_visible_live is off by default


@pytest.mark.asyncio
async def test_cast_vote_updates_my_vote_and_tally_when_live(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi12@example.com")
    author = await make_user(session, "author-capi12@example.com")
    voter = await make_user(session, "voter-capi12@example.com")
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    contest.votes_visible_live = True
    await session.commit()

    vote_resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries/{entry.id}/vote", headers=_auth(voter.id)
    )
    assert vote_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/contests/{contest.id}/entries", headers=_auth(voter.id))
    body = list_resp.json()
    assert body["my_vote_entry_id"] == entry.id
    assert body["entries"][0]["vote_count"] == 1


@pytest.mark.asyncio
async def test_cast_vote_blocks_self_vote(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi13@example.com")
    author = await make_user(session, "author-capi13@example.com")
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries/{entry.id}/vote", headers=_auth(author.id)
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cast_vote_requires_complete_profile(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi14@example.com")
    author = await make_user(session, "author-capi14@example.com")
    incomplete_voter = await make_user(session, "voter-capi14@example.com", complete_profile=False)
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries/{entry.id}/vote",
        headers=_auth(incomplete_voter.id),
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("reason", [
    "profile_incomplete", "email_unverified", "profile_pending_review", "survey_required",
])
async def test_contest_submission_and_voting_use_rating_access_rules(
    session: AsyncSession, client: AsyncClient, reason: str,
) -> None:
    org = await make_user(session, "access-org@example.com")
    runner = await make_user(session, "access-runner@example.com")
    contest, link, _photo = await _open_contest(session, org)
    voting, entry, _, _ = await _voting_contest_with_approved_entry(session, org, org)
    if reason == "profile_incomplete":
        runner.phone = None
    elif reason == "email_unverified":
        runner.email_verified = False
    elif reason == "profile_pending_review":
        session.add(ProfileEditRequest(user_id=runner.id, changes={"first_name": "Новое"}))
    else:
        runner.prior_experience = PriorExperience.never
        session.add(Survey(
            title="Опрос", created_by=org.id, is_active=True, is_required_for_access=True,
        ))
    await session.commit()
    headers = _auth(runner.id)
    rating = await client.get("/api/v1/rating", headers=headers)
    detail = await client.get(f"/api/v1/contests/{contest.id}", headers=headers)
    assert detail.json()["lock_reason"] == rating.json()["lock_reason"]
    assert detail.json()["lock_reason"] is not None
    response = await client.post(
        f"/api/v1/contests/{contest.id}/entries", headers=headers,
        data={f"field_{link.id}": "https://example.com"},
    )
    assert response.status_code == 403
    response = await client.post(
        f"/api/v1/contests/{voting.id}/entries/{entry.id}/vote", headers=headers,
    )
    assert response.status_code == 403


async def test_vote_is_final_and_does_not_reorder_works(
    session: AsyncSession, client: AsyncClient,
) -> None:
    org = await make_user(session, "final-org@example.com")
    voter = await make_user(session, "final-voter@example.com")
    contest, first, _, _ = await _voting_contest_with_approved_entry(session, org, org)
    second = ContestEntry(
        contest_id=contest.id, runner_id=org.id, status=ModerationStatus.approved,
        submitted_at=PAST,
    )
    session.add(second)
    contest.votes_visible_live = True
    await session.commit()
    url = f"/api/v1/contests/{contest.id}/entries"
    headers = _auth(voter.id)
    assert (await client.post(f"{url}/{second.id}/vote", headers=headers)).status_code == 204
    for target in (first, second):
        response = await client.post(f"{url}/{target.id}/vote", headers=headers)
        assert response.status_code == 400
        assert "Изменить голос нельзя" in response.json()["detail"]
    body = (await client.get(url, headers=headers)).json()
    assert [e["id"] for e in body["entries"]] == [first.id, second.id]
    assert [e["vote_count"] for e in body["entries"]] == [0, 1]
    assert body["my_vote_entry_id"] == second.id
    assert body["statistics"] is None


async def test_statistics_only_after_voting_count_approved_works_and_unique_people(
    session: AsyncSession, client: AsyncClient,
) -> None:
    org = await make_user(session, "stats-org@example.com")
    other = await make_user(session, "stats-author@example.com")
    voter = await make_user(session, "stats-voter@example.com")
    contest, first, _, _ = await _voting_contest_with_approved_entry(session, org, org)
    second = ContestEntry(contest_id=contest.id, runner_id=org.id,
                          status=ModerationStatus.approved, submitted_at=PAST)
    third = ContestEntry(contest_id=contest.id, runner_id=other.id,
                         status=ModerationStatus.approved, submitted_at=PAST)
    rejected = ContestEntry(contest_id=contest.id, runner_id=voter.id,
                            status=ModerationStatus.rejected, submitted_at=PAST)
    session.add_all([second, third, rejected])
    await session.flush()
    session.add_all([
        ContestVote(contest_id=contest.id, voter_id=voter.id, entry_id=first.id),
        ContestVote(contest_id=contest.id, voter_id=other.id, entry_id=second.id),
        ContestVote(contest_id=contest.id, voter_id=org.id, entry_id=rejected.id),
    ])
    await session.commit()
    url = f"/api/v1/contests/{contest.id}/entries"
    assert (await client.get(url)).json()["statistics"] is None
    contest.voting_close_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    body = (await client.get(url)).json()
    assert body["statistics"] == {"participants": 2, "entries": 3, "voters": 2}
    assert body["votes_visible"] is False  # totals do not expose per-work votes


async def test_images_append_remove_and_cannot_change_after_approval(
    session: AsyncSession, client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    org = await make_user(session, "photos-org@example.com")
    runner = await make_user(session, "photos-runner@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()
    url = f"/api/v1/contests/{contest.id}/entries"
    headers = _auth(runner.id)
    data = {f"field_{link.id}": "https://example.com"}
    first = await client.post(url, headers=headers, data=data, files={f"field_{photo.id}": _IMG})
    assert first.status_code == 201
    entry_id = first.json()["id"]
    data["entry_id"] = str(entry_id)

    def paths(response):
        return json.loads(next(v["value"] for v in response.json()["values"]
                               if v["field_id"] == photo.id))

    original = paths(first)[0]
    second = await client.post(url, headers=headers, data=data, files={f"field_{photo.id}": _IMG})
    assert second.status_code == 201
    assert len(paths(second)) == 2
    assert paths(second)[0] == original
    retained = paths(second)[1]
    data[f"keep_field_{photo.id}"] = json.dumps([retained])
    removed = await client.post(url, headers=headers, data=data)
    assert removed.status_code == 201
    assert paths(removed) == [retained]
    assert not media_path_to_fs(original).exists()
    assert media_path_to_fs(retained).exists()

    entry = await session.get(ContestEntry, entry_id)
    entry.status = ModerationStatus.approved
    await session.commit()
    data[f"keep_field_{photo.id}"] = "[]"
    blocked = await client.post(url, headers=headers, data=data, files={f"field_{photo.id}": _IMG})
    assert blocked.status_code == 400
    assert media_path_to_fs(retained).exists()
    assert list(Path(settings.media_root).rglob("*.png")) == [media_path_to_fs(retained)]


async def test_image_removal_validation_does_not_delete_saved_files_or_leak_new_files(
    session: AsyncSession, client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    org = await make_user(session, "keep-org@example.com")
    contest, link, photo = await _open_contest(session, org)
    photo.required = True
    await session.commit()
    url = f"/api/v1/contests/{contest.id}/entries"
    headers = _auth(org.id)
    data = {f"field_{link.id}": "https://example.com"}
    first = await client.post(url, headers=headers, data=data, files={f"field_{photo.id}": _IMG})
    assert first.status_code == 201
    data["entry_id"] = str(first.json()["id"])
    original = json.loads(next(v["value"] for v in first.json()["values"]
                               if v["field_id"] == photo.id))[0]
    for invalid in ('["/media/someone-elses.png"]', '{}', 'not-json'):
        data[f"keep_field_{photo.id}"] = invalid
        assert (await client.post(url, headers=headers, data=data)).status_code == 400
    data[f"keep_field_{photo.id}"] = "[]"
    assert (await client.post(url, headers=headers, data=data)).status_code == 422
    data[f"field_{link.id}"] = ""  # new image saved, but another required field fails
    response = await client.post(url, headers=headers, data=data, files={f"field_{photo.id}": _IMG})
    assert response.status_code == 422
    assert media_path_to_fs(original).exists()
    assert list(Path(settings.media_root).rglob("*.png")) == [media_path_to_fs(original)]
    values = await session.scalar(
        select(ContestEntry).where(ContestEntry.id == int(data["entry_id"]))
    )
    await session.refresh(values, attribute_names=["values"])
    assert json.loads(next(v.value for v in values.values if v.field_id == photo.id)) == [original]
