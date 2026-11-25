"""Six-digit numeric email verification (OTP) model for GeoRutex signup."""

from datetime import timedelta
import hashlib
import logging
import secrets
from urllib.parse import urlencode

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


def mask_email(email: str) -> str:
    """Return privacy-masked email for UI hints (e.g. j***z@correo.com)."""
    cleaned = (email or "").strip().lower()
    if "@" not in cleaned:
        return cleaned
    local, domain = cleaned.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***" if local else "***"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


class TransportEmailVerification(models.Model):
    """Stores time-limited, hashed 6-digit numeric OTP codes for signup."""

    _name = "transport.email.verification"
    _description = "Verificación Numérica de Correo GeoRutex"
    _order = "create_date desc, id desc"

    email = fields.Char(
        string="Correo Electrónico",
        required=True,
        index=True,
    )
    full_name = fields.Char(
        string="Nombre Completo",
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Usuario Asociado",
        ondelete="cascade",
        index=True,
    )
    code_salt = fields.Char(
        string="Salt",
        required=True,
        readonly=True,
    )
    code_hash = fields.Char(
        string="Hash del Código",
        required=True,
        readonly=True,
    )
    expires_at = fields.Datetime(
        string="Fecha de Expiración (UTC)",
        required=True,
    )
    attempts = fields.Integer(
        string="Intentos Fallidos",
        default=0,
    )
    verified = fields.Boolean(
        string="Verificado",
        default=False,
    )
    verified_at = fields.Datetime(
        string="Fecha de Verificación (UTC)",
        readonly=True,
    )
    delivery_status = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("sent", "Enviado por SMTP"),
            ("smtp_not_configured", "SMTP No Configurado"),
            ("failed", "Error de Envío SMTP"),
        ],
        string="Estado de Envío",
        default="pending",
        required=True,
    )
    delivery_error = fields.Char(
        string="Detalle de Envío",
        readonly=True,
    )

    @staticmethod
    def _hash_code(salt: str, code: str) -> str:
        return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_numeric_code() -> str:
        """Generate a cryptographically secure 6-digit numeric code."""
        return f"{secrets.randbelow(900000) + 100000:06d}"

    @api.model
    def get_resend_cooldown_seconds(self, email: str) -> int:
        """Return remaining cooldown seconds before a new OTP may be resent."""
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            return 0
        latest = self.sudo().search(
            [
                ("email", "=", normalized_email),
                ("verified", "=", False),
            ],
            order="id desc",
            limit=1,
        )
        if not latest or not latest.create_date:
            return 0
        # Allow immediate retry if prior delivery failed or SMTP wasn't configured
        if latest.delivery_status in ("failed", "smtp_not_configured"):
            return 0
        elapsed = (fields.Datetime.now() - latest.create_date).total_seconds()
        remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
        return max(0, remaining)

    @api.model
    def create_and_send_otp(self, user, email: str, full_name: str):
        """Invalidate previous open OTPs, generate a 6-digit code, and send via SMTP."""
        normalized_email = (email or "").strip().lower()
        # Expire any prior unverified codes for this email
        prior = self.sudo().search([
            ("email", "=", normalized_email),
            ("verified", "=", False),
        ])
        if prior:
            prior.write({"expires_at": fields.Datetime.now() - timedelta(seconds=1)})

        plain_code = self._generate_numeric_code()
        salt = secrets.token_hex(16)
        now = fields.Datetime.now()
        record = self.sudo().create({
            "email": normalized_email,
            "full_name": full_name,
            "user_id": user.id if user else False,
            "code_salt": salt,
            "code_hash": self._hash_code(salt, plain_code),
            "expires_at": now + timedelta(minutes=OTP_EXPIRY_MINUTES),
            "attempts": 0,
            "verified": False,
            "delivery_status": "pending",
        })

        record._send_verification_email(plain_code)
        return record, plain_code

    def _send_verification_email(self, plain_code: str) -> bool:
        """Deliver the branded GeoRutex HTML email using Odoo's configured SMTP server."""
        self.ensure_one()
        mail_servers = self.env["ir.mail_server"].sudo().search(
            [("active", "=", True)], order="sequence asc", limit=1
        )
        if not mail_servers:
            self.sudo().write({
                "delivery_status": "smtp_not_configured",
                "delivery_error": (
                    "No existe un servidor SMTP saliente configurado en Odoo "
                    "(ir.mail_server)."
                ),
            })
            _logger.warning(
                "GeoRutex OTP email for %s was not sent: no active ir.mail_server configured.",
                mask_email(self.email),
            )
            return False

        template = self.env.ref(
            "uta_transport_monitor.mail_template_georutex_email_verification",
            raise_if_not_found=False,
        )
        if not template:
            self.sudo().write({
                "delivery_status": "failed",
                "delivery_error": "Plantilla de verificación de correo no encontrada.",
            })
            return False

        smtp_server = mail_servers[0]
        email_from = (
            smtp_server.from_filter
            or smtp_server.smtp_user
            or self.env.company.email
            or "no-reply@georutex.local"
        )
        spaced_code = " ".join(list(plain_code))
        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
            .rstrip("/")
        )
        verify_url = (
            f"{base_url}/georutex/verificar-correo?"
            f"{urlencode({'email': self.email})}"
            if base_url
            else ""
        )
        try:
            mail_id = template.sudo().with_context(
                otp_code=plain_code,
                otp_code_spaced=spaced_code,
                otp_expiry_minutes=OTP_EXPIRY_MINUTES,
                georutex_base_url=base_url,
                georutex_verify_url=verify_url,
            ).send_mail(
                self.id,
                force_send=False,
                email_values={
                    "email_to": self.email,
                    "email_from": email_from,
                    "mail_server_id": smtp_server.id,
                },
            )
            mail = self.env["mail.mail"].sudo().browse(mail_id)
            mail.send(raise_exception=True)
            self.sudo().write({
                "delivery_status": "sent",
                "delivery_error": False,
            })
            _logger.info(
                "GeoRutex OTP verification email sent via SMTP to %s.",
                mask_email(self.email),
            )
            return True
        except Exception as exc:
            err_text = str(exc)[:240]
            self.sudo().write({
                "delivery_status": "failed",
                "delivery_error": err_text,
            })
            _logger.error(
                "GeoRutex SMTP delivery failed for %s: %s",
                mask_email(self.email),
                err_text,
            )
            return False

    @api.model
    def verify_code(self, email: str, submitted_code: str):
        """Verify 6-digit numeric OTP and return (ok, message, user)."""
        normalized_email = (email or "").strip().lower()
        code = "".join(ch for ch in (submitted_code or "") if ch.isdigit())
        if len(code) != 6:
            return (
                False,
                "Ingresa los 6 dígitos numéricos del código enviado a tu correo.",
                False,
            )

        record = self.sudo().search(
            [
                ("email", "=", normalized_email),
                ("verified", "=", False),
            ],
            order="id desc",
            limit=1,
        )
        if not record:
            return (
                False,
                "No existe una verificación pendiente para este correo. "
                "Solicita un nuevo código o inicia sesión.",
                False,
            )

        now = fields.Datetime.now()
        if record.expires_at < now:
            return (
                False,
                "El código de verificación ha expirado. "
                "Solicita un nuevo código para continuar.",
                False,
            )

        if record.attempts >= OTP_MAX_ATTEMPTS:
            return (
                False,
                "Superaste el máximo de intentos permitidos. "
                "Solicita un nuevo código de verificación.",
                False,
            )

        expected = record.code_hash
        actual = self._hash_code(record.code_salt, code)
        if not secrets.compare_digest(expected, actual):
            new_attempts = record.attempts + 1
            record.sudo().write({"attempts": new_attempts})
            remaining = max(0, OTP_MAX_ATTEMPTS - new_attempts)
            if remaining == 0:
                return (
                    False,
                    "Código incorrecto. Alcanzaste el límite de intentos; solicita un nuevo código.",
                    False,
                )
            return (
                False,
                f"Código incorrecto. Te quedan {remaining} "
                f"{'intento' if remaining == 1 else 'intentos'}.",
                False,
            )

        record.sudo().write({
            "verified": True,
            "verified_at": now,
        })
        user = record.with_context(active_test=False).user_id.sudo()
        if user and not user.active:
            user.write({"active": True})
        return (True, "Correo verificado correctamente.", user)
