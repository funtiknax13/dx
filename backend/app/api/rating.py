from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import OptionalUser, SessionDep
from app.schemas.rating import RatingItem, RatingResponse
from app.services.profile_completeness_service import stats_access_lock
from app.services.rating_service import compute_rating

router = APIRouter(tags=["rating"])

PAGE_SIZE = 20


@router.get("/rating", response_model=RatingResponse)
async def rating(
    session: SessionDep,
    user: OptionalUser,
    period: Literal["all", "year", "month"] = "all",
    page: int = Query(1, ge=1),
) -> RatingResponse:
    lock_reason, missing_fields = await stats_access_lock(session, user)
    if lock_reason is not None:
        return RatingResponse(
            period=period,
            entries=[],
            total=0,
            page=1,
            page_size=PAGE_SIZE,
            lock_reason=lock_reason,
            missing_fields=missing_fields,
        )

    # compute_rating already drops anyone with 0 activity in the window, so the
    # ranking never lists someone sitting at 0 for the selected period.
    entries = await compute_rating(session, period)
    items = [
        RatingItem(
            rank=i,
            runner_id=e.runner_id,
            first_name=e.first_name,
            last_name=e.last_name,
            avatar=e.avatar,
            finished_count=e.finished_count,
        )
        for i, e in enumerate(entries, start=1)
    ]

    total = len(items)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_items = items[start : start + PAGE_SIZE]

    # Only surface a personal "me" row when the user is ranked but *not* on the
    # page being viewed — otherwise they're already visible. Its rank tells the
    # frontend which page to highlight.
    me = None
    if user is not None:
        on_page = {it.runner_id for it in page_items}
        me = next(
            (it for it in items if it.runner_id == user.id and it.runner_id not in on_page),
            None,
        )

    return RatingResponse(
        period=period,
        entries=page_items,
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        me=me,
    )
