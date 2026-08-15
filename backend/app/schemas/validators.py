"""Shared Pydantic field validators. Mirrored on the frontend in
src/lib/validation.ts — keep the two in sync."""

import re

# Password: printable ASCII only (Latin letters + digits + standard symbols,
# no spaces/Cyrillic), with at least one letter and one digit. Length is
# enforced by the field's min/max, not here.
_PASSWORD_CHARSET = re.compile(r"^[!-~]+$")

# Cyrillic letters plus the punctuation real names actually use: space
# (multi-word names), hyphen (Анна-Мария), apostrophe (О'Коннор). Mirrored on
# the frontend in src/lib/validation.ts (NAME_RE) — keep both in sync.
_NAME_RE = re.compile(r"^[А-ЯЁа-яё]+(?:[ '\-][А-ЯЁа-яё]+)*$")


def _validate_charset_and_capitalize(value: str) -> str:
    if not _NAME_RE.match(value):
        raise ValueError("Name must contain only Cyrillic letters, spaces, hyphens and apostrophes")
    return value[:1].upper() + value[1:]


def normalize_required_name(value: str) -> str:
    """Trim, validate the charset, capitalise the first letter. Blank is an
    error."""
    v = value.strip()
    if not v:
        raise ValueError("Name is required")
    return _validate_charset_and_capitalize(v)


def normalize_optional_name(value: str | None) -> str | None:
    """Same rule as normalize_required_name, but a blank/None value is allowed
    and normalised to None (an optional name left empty)."""
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return _validate_charset_and_capitalize(v)


def validate_password(value: str) -> str:
    if not _PASSWORD_CHARSET.match(value):
        raise ValueError("Password may contain only Latin letters, digits and symbols")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Password must contain at least one Latin letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit")
    return value
