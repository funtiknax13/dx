from datetime import date, timedelta

import pytest

from app.schemas.user import UserUpdate, normalize_ru_phone, validate_birthday


def test_normalize_phone_accepts_common_forms() -> None:
    assert normalize_ru_phone("+7 (900) 123-45-67") == "+79001234567"
    assert normalize_ru_phone("8 900 123 45 67") == "+79001234567"
    assert normalize_ru_phone("9001234567") == "+79001234567"
    assert normalize_ru_phone("") is None
    assert normalize_ru_phone(None) is None


def test_normalize_phone_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        normalize_ru_phone("123")
    with pytest.raises(ValueError):
        normalize_ru_phone("+7 900 123")


def test_validate_birthday_rejects_future_and_ancient() -> None:
    with pytest.raises(ValueError):
        validate_birthday(date.today() + timedelta(days=1))
    with pytest.raises(ValueError):
        validate_birthday(date(1800, 1, 1))


def test_validate_birthday_accepts_reasonable() -> None:
    assert validate_birthday(date(1990, 5, 3)) == date(1990, 5, 3)
    assert validate_birthday(None) is None


def test_user_update_normalizes_phone_and_guards_birthday() -> None:
    ok = UserUpdate(phone="8 (900) 123-45-67", birthday=date(1990, 1, 1))
    assert ok.phone == "+79001234567"

    with pytest.raises(ValueError):
        UserUpdate(birthday=date.today() + timedelta(days=1))
