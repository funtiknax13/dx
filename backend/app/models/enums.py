import enum


class UserRole(enum.StrEnum):
    runner = "runner"
    organizer = "organizer"
    admin = "admin"


class Gender(enum.StrEnum):
    male = "male"
    female = "female"


class FinishStatus(enum.StrEnum):
    finished = "finished"
    dnf = "dnf"


class ResultSource(enum.StrEnum):
    file = "file"
    manual = "manual"


class ModerationStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    # Result reviewed and turned down (bad screenshot, wrong data, …). Kept
    # rather than deleted so the runner sees it was rejected and can re-upload;
    # never counts toward the protocol/rating (that needs `approved`).
    rejected = "rejected"


class AvatarReview(enum.StrEnum):
    """Post-moderation of profile photos: an uploaded avatar applies immediately
    (`pending`) but sits in a queue where a moderator can keep it (`approved`) or
    remove it. Existing avatars are grandfathered to `approved` by the migration
    so they don't flood the queue."""

    pending = "pending"
    approved = "approved"


class ClaimStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SurveyQuestionType(enum.StrEnum):
    """Only long_text is used by the first real survey — kept as an enum
    (rather than a bare string) so a future choice-style question doesn't
    need a schema change, just a new value here."""

    long_text = "long_text"
    short_text = "short_text"
    single_choice = "single_choice"
    multi_choice = "multi_choice"


class PriorExperience(enum.StrEnum):
    """Self-reported at profile completion (new registrations only — see
    User.prior_experience): has this runner ever run a DX with the community
    before signing up? Drives two things: whether the newbie feedback survey
    is required, and whether to prompt them to search for/claim a matching
    guest profile right there in the form."""

    never = "never"
    once = "once"
    multiple = "multiple"


class TicketStatus(enum.StrEnum):
    """A ticket reopens on its own the moment the reporter (not staff) sends
    a new message on a closed one — see support_service.add_message."""

    open = "open"
    closed = "closed"
