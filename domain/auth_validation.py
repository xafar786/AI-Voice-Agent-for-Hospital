from __future__ import annotations

import re
from typing import Any


USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{3,31}$")
SPECIAL_CHARACTER_PATTERN = re.compile(r"[^A-Za-z0-9]")


class AuthValidationError(ValueError):
    pass


def normalize_admin_name(value: Any) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if len(name) < 2:
        raise AuthValidationError("Full name must contain at least 2 characters.")
    if len(name) > 80:
        raise AuthValidationError("Full name must not exceed 80 characters.")
    if any(ord(char) < 32 for char in name):
        raise AuthValidationError("Full name contains invalid characters.")
    if sum(char.isalpha() for char in name) < 2:
        raise AuthValidationError("Full name must contain at least 2 letters.")
    return name


def normalize_admin_username(value: Any) -> str:
    username = str(value or "").strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AuthValidationError(
            "Username must be 4–32 characters, start with a letter, and use only letters, numbers, dots, underscores, or hyphens."
        )
    return username


def password_rule_results(password: Any, *, username: Any = "") -> dict[str, bool]:
    value = str(password or "")
    username_value = str(username or "").strip().lower()
    return {
        "length": 8 <= len(value) <= 128,
        "uppercase": any(char.isupper() for char in value),
        "lowercase": any(char.islower() for char in value),
        "number": any(char.isdigit() for char in value),
        "special": bool(SPECIAL_CHARACTER_PATTERN.search(value)),
        "no_whitespace": not any(char.isspace() for char in value),
        "not_username": not username_value or username_value not in value.lower(),
    }


def validate_admin_password(password: Any, *, username: Any = "") -> str:
    value = str(password or "")
    rules = password_rule_results(value, username=username)
    messages = {
        "length": "Password must contain 8–128 characters.",
        "uppercase": "Password must contain at least one uppercase letter.",
        "lowercase": "Password must contain at least one lowercase letter.",
        "number": "Password must contain at least one number.",
        "special": "Password must contain at least one special character.",
        "no_whitespace": "Password must not contain spaces.",
        "not_username": "Password must not contain your username.",
    }
    failures = [messages[key] for key, passed in rules.items() if not passed]
    if failures:
        raise AuthValidationError(" ".join(failures))
    return value


def validate_login_password(password: Any) -> str:
    value = str(password or "")
    if not value:
        raise AuthValidationError("Username and password are required.")
    if len(value) > 128:
        raise AuthValidationError("Password must not exceed 128 characters.")
    return value
