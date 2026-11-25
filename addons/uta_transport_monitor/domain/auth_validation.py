"""Pure deterministic validation rules for GeoRutex authentication forms.

Zero Odoo or I/O imports so these rules can be unit-tested independently with
Pytest and reused across HTTP controllers and ORM models.
"""

import re
from typing import List, Tuple

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)
COMMON_DOMAIN_TYPOS = {
    "gmail.con": "gmail.com",
    "gmail.co": "gmail.com",
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmal.com": "gmail.com",
    "hotmail.con": "hotmail.com",
    "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com",
    "outlook.con": "outlook.com",
    "outlok.com": "outlook.com",
    "yahoo.con": "yahoo.com",
    "yaho.com": "yahoo.com",
}

# Allowed characters in personal names: Latin/Spanish letters, single spaces,
# internal hyphens (e.g. María-José, García-Márquez) and apostrophes (O'Connor).
ALLOWED_NAME_CHARS_PATTERN = re.compile(
    r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s'\u2019-]+$"
)
# Lowercase connector particles valid only between capitalized name words.
NAME_PARTICLES = frozenset(
    {
        "de",
        "del",
        "la",
        "las",
        "los",
        "y",
        "e",
        "da",
        "do",
        "dos",
        "das",
        "van",
        "von",
        "di",
    }
)
# Each capitalized word may contain internal apostrophes or hyphens joining
# capitalized segments (e.g., O'Connor, D'Amico, María-José, McDonald).
NAME_SEGMENT_PATTERN = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*"
    r"(?:['\u2019][A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)?$"
)
SPECIAL_CHAR_PATTERN = re.compile(r"[^A-Za-z0-9\s]")


def normalize_email(email: str) -> str:
    """Return trimmed lowercase email string."""
    return (email or "").strip().lower()


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format for any deliverable provider."""
    cleaned = normalize_email(email)
    if not cleaned:
        return (False, "Ingresa tu correo electrónico.")
    if len(cleaned) > 120:
        return (False, "El correo electrónico excede la longitud permitida.")
    if " " in cleaned or not EMAIL_PATTERN.match(cleaned):
        return (
            False,
            "Ingresa un correo electrónico válido (ejemplo: nombre@correo.com).",
        )
    domain = cleaned.split("@", 1)[1]
    if ".." in cleaned or domain.startswith(".") or domain.startswith("-"):
        return (
            False,
            "El dominio del correo electrónico no tiene un formato válido.",
        )
    if domain in COMMON_DOMAIN_TYPOS:
        suggested = COMMON_DOMAIN_TYPOS[domain]
        return (
            False,
            f"El dominio '@{domain}' parece contener un error. "
            f"¿Quisiste escribir '@{suggested}'?",
        )
    return (True, "")


def _is_valid_capitalized_name_word(word: str) -> bool:
    """Return True if a single non-particle word is properly capitalized."""
    if not word or word.startswith("-") or word.endswith("-"):
        return False
    if word.startswith(("'", "\u2019")) or word.endswith(("'", "\u2019")):
        return False
    if "--" in word or "''" in word or "\u2019\u2019" in word:
        return False

    segments = word.split("-")
    for segment in segments:
        if not segment:
            return False
        # Require at least 2 characters for standalone segments unless followed
        # by an apostrophe prefix (e.g., O'Connor, D'Amico).
        if "'" not in segment and "\u2019" not in segment and len(segment) < 2:
            return False
        if not NAME_SEGMENT_PATTERN.match(segment):
            return False
    return True


def validate_full_name(name: str) -> Tuple[bool, str]:
    """Validate full name allowing accents, internal hyphens, apostrophes, and particles."""
    raw = (name or "").strip()
    if not raw:
        return (False, "Ingresa tu nombre y apellido.")
    if len(raw) < 5 or len(raw) > 80:
        return (
            False,
            "El nombre completo debe tener entre 5 y 80 caracteres.",
        )
    if "  " in raw or "\t" in raw or "\n" in raw:
        return (
            False,
            "No utilices espacios dobles entre nombres y apellidos.",
        )
    if not ALLOWED_NAME_CHARS_PATTERN.match(raw):
        return (
            False,
            "El nombre solo puede incluir letras, espacios, guiones o "
            "apóstrofos; no se permiten números ni otros símbolos.",
        )
    words = raw.split(" ")
    if len(words) < 2:
        return (
            False,
            "Ingresa al menos un nombre y un apellido (ejemplo: Juan Pérez).",
        )

    significant_words = 0
    for idx, word in enumerate(words):
        is_edge = idx == 0 or idx == len(words) - 1
        if not is_edge and word in NAME_PARTICLES:
            continue
        if not _is_valid_capitalized_name_word(word):
            return (
                False,
                "Cada nombre y apellido debe iniciar con mayúscula "
                "(ejemplo: María José López, Carlos O'Connor o Ana de la Cruz).",
            )
        significant_words += 1

    if significant_words < 2:
        return (
            False,
            "Ingresa al menos un nombre y un apellido válidos.",
        )
    return (True, "")


def evaluate_password_rules(password: str) -> dict:
    """Return structured boolean checks for password policy enforcement."""
    pwd = password or ""
    return {
        "min_length": 8 <= len(pwd) <= 64,
        "has_upper": any(ch.isupper() for ch in pwd),
        "has_lower": any(ch.islower() for ch in pwd),
        "has_digit": any(ch.isdigit() for ch in pwd),
        "has_special": bool(SPECIAL_CHAR_PATTERN.search(pwd)),
        "no_spaces": not any(ch.isspace() for ch in pwd),
    }


def validate_strong_password(password: str) -> Tuple[bool, str]:
    """Enforce strong password policy (forbids letters-only passwords)."""
    pwd = password or ""
    if not pwd:
        return (False, "Ingresa una contraseña.")

    checks = evaluate_password_rules(pwd)
    missing: List[str] = []
    if not checks["min_length"]:
        missing.append("entre 8 y 64 caracteres")
    if not checks["no_spaces"]:
        missing.append("sin espacios en blanco")
    if not checks["has_upper"]:
        missing.append("al menos una letra mayúscula")
    if not checks["has_lower"]:
        missing.append("al menos una letra minúscula")
    if not checks["has_digit"]:
        missing.append("al menos un número")
    if not checks["has_special"]:
        missing.append("al menos un carácter especial (ej. !@#$%&*)")

    if missing:
        return (
            False,
            "La contraseña no es segura. Debe incluir: "
            + ", ".join(missing)
            + ".",
        )
    return (True, "")


def validate_signup_payload(
    name: str, email: str, password: str, confirm_password: str
) -> Tuple[bool, str]:
    """Validate all registration fields in order and return first failure."""
    ok, err = validate_full_name(name)
    if not ok:
        return (False, err)

    ok, err = validate_email(email)
    if not ok:
        return (False, err)

    ok, err = validate_strong_password(password)
    if not ok:
        return (False, err)

    if password != (confirm_password or ""):
        return (False, "Las contraseñas ingresadas no coinciden.")

    return (True, "")
