import re

from pydantic import BaseModel, EmailStr, Field, field_validator

# Password: Latin letters + digits + standard symbols only (printable ASCII,
# no spaces/Cyrillic), and must contain at least one letter and one digit.
# Length is enforced separately by the field's min/max. Mirrored on the frontend
# in src/lib/validation.ts.
_PASSWORD_CHARSET = re.compile(r"^[!-~]+$")


def _normalize_name(value: str) -> str:
    """Trim, reject digits, and capitalise the first letter — the same rule the
    register form applies client-side (src/lib/validation.ts)."""
    v = value.strip()
    if not v:
        raise ValueError("Name is required")
    if any(ch.isdigit() for ch in v):
        raise ValueError("Name must not contain digits")
    return v[:1].upper() + v[1:]


def _validate_password(value: str) -> str:
    if not _PASSWORD_CHARSET.match(value):
        raise ValueError("Password may contain only Latin letters, digits and symbols")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Password must contain at least one Latin letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit")
    return value


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    accept_privacy_policy: bool
    # Only sent once the adaptive gate has asked for it (after repeated attempts).
    captcha_token: str | None = None

    _normalize_names = field_validator("first_name", "last_name")(_normalize_name)
    _check_password = field_validator("password")(_validate_password)

    @field_validator("accept_privacy_policy")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent to the privacy policy is required")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

    _check_password = field_validator("new_password")(_validate_password)


class MessageResponse(BaseModel):
    detail: str
