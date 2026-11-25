"""Deterministic Pytest unit tests for GeoRutex authentication validations."""

import pytest

from odoo.addons.uta_transport_monitor.domain.auth_validation import (
    evaluate_password_rules,
    normalize_email,
    validate_email,
    validate_full_name,
    validate_signup_payload,
    validate_strong_password,
)


class TestEmailValidation:
    """Validate email normalization and strict format checks."""

    def test_valid_emails(self):
        assert normalize_email("  Juan.Perez@GMAIL.COM  ") == "juan.perez@gmail.com"
        assert validate_email("conductor@gmail.com")[0] is True
        assert validate_email("conductor@hotmail.com")[0] is True
        assert validate_email("conductor@outlook.com")[0] is True
        assert validate_email("conductor@uta.edu.ec")[0] is True
        assert validate_email("maria.lopez+bus@yahoo.com")[0] is True

    @pytest.mark.parametrize(
        "bad_email",
        [
            "",
            "   ",
            "sin_arroba.com",
            "usuario@",
            "@dominio.com",
            "usuario@dominio",
            "con espacio@gmail.com",
            "usuario@gmail.con",
            "usuario@hotmial.com",
            "usuario@outlok.com",
        ],
    )
    def test_invalid_emails_rejected(self, bad_email):
        ok, err = validate_email(bad_email)
        assert ok is False
        assert err


class TestFullNameValidation:
    """Validate legitimate names with accents, hyphens, apostrophes, and particles."""

    @pytest.mark.parametrize(
        "good_name",
        [
            "Juan Pérez",
            "María José López",
            "Ángel Núñez Quiñónez",
            "Carlos Andrés Paredes",
            "María-José López",
            "Gabriel García-Márquez",
            "Carlos O'Connor",
            "Lucía D'Alessandro",
            "Ana de la Cruz",
            "José del Valle",
            "Sofía de los Ángeles Mora",
        ],
    )
    def test_valid_names_accepted(self, good_name):
        ok, err = validate_full_name(good_name)
        assert ok is True
        assert err == ""

    @pytest.mark.parametrize(
        "bad_name",
        [
            "",
            "Juan",  # single word only
            "juan perez",  # lowercase
            "Juan perez",  # second word lowercase
            "JUAN PEREZ",  # all caps
            "Juan Perez1",  # contains digit
            "Juan @Perez",  # special character
            "Juan_Perez",  # underscore
            "Juan  Pérez",  # double space
            "Juan-Pérez",  # single hyphenated token without surname space
            "-Juan Pérez",  # leading hyphen
            "Juan 'Pérez",  # leading apostrophe
            "de la Cruz",  # starts with lowercase particle
            "Juan de",  # ends with lowercase particle
        ],
    )
    def test_invalid_names_rejected(self, bad_name):
        ok, err = validate_full_name(bad_name)
        assert ok is False
        assert err


class TestStrongPasswordValidation:
    """Validate strong password rules forbidding letters-only passwords."""

    @pytest.mark.parametrize(
        "strong_pwd",
        [
            "GeoRutex!2026",
            "UtaBus#99a",
            "Segura$2026x",
        ],
    )
    def test_strong_passwords_accepted(self, strong_pwd):
        ok, err = validate_strong_password(strong_pwd)
        assert ok is True
        assert err == ""
        rules = evaluate_password_rules(strong_pwd)
        assert all(rules.values())

    @pytest.mark.parametrize(
        "weak_pwd",
        [
            "",
            "SoloLetras",  # letters only
            "sololetras",  # lowercase letters only
            "12345678",  # digits only
            "GeoRutex2026",  # missing special char
            "georutex!2026",  # missing uppercase
            "GEORUTEX!2026",  # missing lowercase
            "GeoRutex!abc",  # missing digit
            "Ab1!xyz",  # too short (< 8)
            "Geo Rutex!2026",  # contains space
        ],
    )
    def test_weak_passwords_rejected(self, weak_pwd):
        ok, err = validate_strong_password(weak_pwd)
        assert ok is False
        assert err


def test_signup_payload_validation_end_to_end():
    """Full signup payload validates name, email, strong password, and confirmation."""
    ok, err = validate_signup_payload(
        "Ana de la Cruz", "ana.cruz@ejemplo.com", "GeoRutex!2026", "GeoRutex!2026"
    )
    assert ok is True
    assert err == ""

    ok, err = validate_signup_payload(
        "Carlos O'Connor", "carlos.oconnor@ejemplo.com", "GeoRutex!2026", "Otra!2026"
    )
    assert ok is False
    assert "coinciden" in err
