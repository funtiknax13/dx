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
