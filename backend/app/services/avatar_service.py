from app.models.enums import AvatarReview
from app.models.user import User


def visible_avatar(user: User | None, viewer_id: int | None) -> str | None:
    """The avatar URL as a given viewer is allowed to see it.

    A freshly uploaded avatar sits in `pending` post-moderation (see
    AvatarReview). Until a moderator approves it, only its owner sees it —
    everyone else gets the placeholder (None), so an un-reviewed photo is never
    exposed to the community. Approved avatars (the default state, and every
    grandfathered one) are visible to all."""
    if user is None or user.avatar is None:
        return None
    if user.avatar_review == AvatarReview.approved or user.id == viewer_id:
        return user.avatar
    return None
