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
# Only Spanish letters and single spaces; each word must start with uppercase
# followed by lowercase letters, and at least two words (name + surname).
FULL_NAME_PATTERN = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+"
    r"(?:\s[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)+$"
)
ALLOWED_NAME_CHARS_PATTERN = re.compile(
    r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s]+$"
)
SPECIAL_CHAR_PATTERN = re.compile(r"[^A-Za-z0-9\s]")


def normalize_email(email: str) -> str:
    """Return trimmed lowercase email string."""
    return (email or "").strip().lower()


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format for any deliverable provider (Gmail, Hotmail, UTA, etc.)."""
    cleaned = normalize_email(email)
    if not cleaned:
        return (False, "Debe ingresar un correo electrónico.")
    if len(cleaned) > 120:
        return (False, "El correo electrónico excede la longitud permitida.")
    if " " in cleaned or not EMAIL_PATTERN.match(cleaned):
        return (
            False,
            "Ingrese un correo electrónico válido (ej. usuario@gmail.com, "
            "@hotmail.com o @uta.edu.ec).",
        )
    domain = cleaned.split("@", 1)[1]
    if ".." in cleaned or domain.startswith(".") or domain.startswith("-"):
        return (
            False,
            "El dominio del correo electrónico no es válido para envío SMTP.",
        )
    if domain in COMMON_DOMAIN_TYPOS:
        suggested = COMMON_DOMAIN_TYPOS[domain]
        return (
            False,
            f"El dominio '@{domain}' parece contener un error. "
            f"¿Quisiste escribir '@{suggested}'?",
        )
    return (True, "")


def validate_full_name(name: str) -> Tuple[bool, str]:
    """Validate full name: letters only, no symbols/digits, Title Case words."""
    raw = (name or "").strip()
    if not raw:
        return (False, "Debe ingresar su nombre completo.")
    if len(raw) < 5 or len(raw) > 80:
        return (
            False,
            "El nombre completo debe tener entre 5 y 80 caracteres.",
        )
    if "  " in raw:
        return (
            False,
            "No utilice espacios dobles entre los nombres y apellidos.",
        )
    if not ALLOWED_NAME_CHARS_PATTERN.match(raw):
        return (
            False,
            "El nombre solo puede contener letras y espacios; no se permiten "
            "números ni caracteres especiales.",
        )
    words = raw.split(" ")
    if len(words) < 2:
        return (
            False,
            "Ingrese al menos un nombre y un apellido (ejemplo: Juan Pérez).",
        )
    if not FULL_NAME_PATTERN.match(raw):
        return (
            False,
            "Cada nombre y apellido debe iniciar con mayúscula seguida de "
            "minúsculas (ejemplo: María José López).",
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
        return (False, "Debe ingresar una contraseña.")

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
