import re

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.guest_claim import GuestClaim
from tests.factories import make_user


async def test_guest_claim_search_matches_either_person(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "search-admin@example.com", UserRole.admin)
    guest = await make_user(session, "search-guest@example.com")
    guest.is_guest = True
    guest.first_name, guest.last_name = "Алексей", "Ильин"
    claimant = await make_user(session, "search-claimant@example.com")
    claimant.first_name, claimant.last_name = "Сергей", "Петров"
    other_guest = await make_user(session, "search-other-guest@example.com")
    other_guest.is_guest = True
    other_guest.first_name, other_guest.last_name = "Иван", "Сидоров"
    other_claimant = await make_user(session, "search-other-claimant@example.com")
    other_claimant.first_name, other_claimant.last_name = "Борис", "Ильин"

    claims = [
        GuestClaim(guest_user_id=guest.id, claimant_user_id=claimant.id),
        GuestClaim(guest_user_id=other_guest.id, claimant_user_id=other_claimant.id),
        GuestClaim(guest_user_id=other_guest.id, claimant_user_id=claimant.id),
        GuestClaim(guest_user_id=guest.id, claimant_user_id=other_claimant.id),
    ]
    session.add_all(claims)
    await session.commit()
    guest_match, claimant_match, unrelated, both_match = [claim.id for claim in claims]

    login = await client.get(
        "/admin-tools/sso", params={"token": create_access_token(admin.id)}
    )
    assert login.status_code == 302

    # Exercise SQLAdmin's real count query, list query and rendering together.
    # Matching both people must still return the claim only once.
    for term, expected in [
        ("Ильин", {guest_match, claimant_match, both_match}),
        ("Иль", {guest_match, claimant_match, both_match}),
        ("Алексей", {guest_match, both_match}),
        ("Борис", {claimant_match, both_match}),
        ("Петров", {guest_match, unrelated}),
        ("Несуществующий", set()),
        ("", {guest_match, claimant_match, unrelated, both_match}),
    ]:
        response = await client.get("/admin/guest-claim/list", params={"search": term})
        assert response.status_code == 200, response.text
        ids = re.findall(r'data-pk="(\d+)"', response.text)
        assert {int(pk) for pk in ids} == expected, term
        assert len(ids) == len(expected), term
