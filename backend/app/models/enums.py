import enum


class UserRole(enum.StrEnum):
    runner = "runner"
    organizer = "organizer"
    admin = "admin"


class Gender(enum.StrEnum):
    male = "male"
    female = "female"
    other = "other"


class FinishStatus(enum.StrEnum):
    finished = "finished"
    dnf = "dnf"


class ResultSource(enum.StrEnum):
    file = "file"
    manual = "manual"


class ModerationStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"


class ClaimStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PriorExperience(enum.StrEnum):
    """Self-reported at profile completion (new registrations only — see
    User.prior_experience): has this runner ever run a DX with the community
    before signing up? Drives two things: whether the newbie feedback survey
    is required, and whether to prompt them to search for/claim a matching
    guest profile right there in the form."""

    never = "never"
    once = "once"
    multiple = "multiple"
