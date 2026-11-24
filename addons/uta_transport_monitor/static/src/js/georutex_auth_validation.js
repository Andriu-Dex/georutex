/* GeoRutex Frontend Authentication Validation & Password UX (Bootstrap 5) */
(function () {
    "use strict";

    const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
    const ALLOWED_NAME_CHARS_RE = /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s]+$/;
    const FULL_NAME_RE =
        /^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)+$/;
    const SPECIAL_RE = /[^A-Za-z0-9\s]/;

    function validateName(value) {
        const raw = (value || "").trim();
        if (!raw) {
            return "Debe ingresar su nombre completo.";
        }
        if (raw.length < 5 || raw.length > 80) {
            return "El nombre completo debe tener entre 5 y 80 caracteres.";
        }
        if (/\s{2,}/.test(raw)) {
            return "No utilice espacios dobles entre nombres y apellidos.";
        }
        if (!ALLOWED_NAME_CHARS_RE.test(raw)) {
            return "Solo se permiten letras y espacios; no ingrese números ni caracteres especiales.";
        }
        if (raw.split(" ").length < 2) {
            return "Ingrese al menos un nombre y un apellido (ej. Juan Pérez).";
        }
        if (!FULL_NAME_RE.test(raw)) {
            return "Cada nombre y apellido debe iniciar con mayúscula (ej. María José López).";
        }
        return "";
    }

    const COMMON_DOMAIN_TYPOS = {
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
    };

    function validateEmail(value, allowAdmin) {
        const cleaned = (value || "").trim().toLowerCase();
        if (!cleaned) {
            return "Debe ingresar su correo electrónico.";
        }
        if (allowAdmin && cleaned === "admin") {
            return "";
        }
        if (!EMAIL_RE.test(cleaned)) {
            return "Ingrese un correo válido (ej. usuario@gmail.com, @hotmail.com o @uta.edu.ec).";
        }
        const domain = cleaned.split("@")[1] || "";
        if (COMMON_DOMAIN_TYPOS[domain]) {
            return (
                "El dominio '@" +
                domain +
                "' parece incorrecto. ¿Quisiste escribir '@" +
                COMMON_DOMAIN_TYPOS[domain] +
                "'?"
            );
        }
        return "";
    }

    function checkPasswordRules(pwd) {
        const value = pwd || "";
        return {
            minLength: value.length >= 8 && value.length <= 64,
            hasUpper: /[A-Z]/.test(value),
            hasLower: /[a-z]/.test(value),
            hasDigit: /[0-9]/.test(value),
            hasSpecial: SPECIAL_RE.test(value),
            noSpaces: !/\s/.test(value),
        };
    }

    function validateStrongPassword(pwd) {
        const value = pwd || "";
        if (!value) {
            return "Debe ingresar una contraseña.";
        }
        const rules = checkPasswordRules(value);
        const missing = [];
        if (!rules.minLength) missing.push("entre 8 y 64 caracteres");
        if (!rules.noSpaces) missing.push("sin espacios");
        if (!rules.hasUpper) missing.push("una mayúscula");
        if (!rules.hasLower) missing.push("una minúscula");
        if (!rules.hasDigit) missing.push("un número");
        if (!rules.hasSpecial) missing.push("un carácter especial");
        if (missing.length) {
            return "Contraseña insegura. Debe incluir: " + missing.join(", ") + ".";
        }
        return "";
    }

    function getOrCreateFeedback(input) {
        const container =
            input.closest(".input-group") || input;
        let feedback = container.parentElement.querySelector(
            ".georutex-field-feedback"
        );
        if (!feedback) {
            feedback = document.createElement("div");
            feedback.className = "georutex-field-feedback";
            feedback.setAttribute("role", "alert");
            container.insertAdjacentElement("afterend", feedback);
        }
        return feedback;
    }

    function setFieldState(input, errorMessage) {
        const feedback = getOrCreateFeedback(input);
        if (errorMessage) {
            input.classList.add("is-invalid");
            input.classList.remove("is-valid");
            feedback.textContent = errorMessage;
            feedback.classList.add("is-visible");
            return false;
        }
        input.classList.remove("is-invalid");
        if ((input.value || "").trim()) {
            input.classList.add("is-valid");
        } else {
            input.classList.remove("is-valid");
        }
        feedback.textContent = "";
        feedback.classList.remove("is-visible");
        return true;
    }

    function attachPasswordToggle(input) {
        if (!input || input.dataset.georutexToggleAttached === "1") return;
        input.dataset.georutexToggleAttached = "1";

        const wrapper = document.createElement("div");
        wrapper.className = "input-group";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn georutex-pwd-toggle";
        btn.setAttribute("aria-label", "Mostrar u ocultar contraseña");
        btn.innerHTML = '<i class="fa fa-eye" aria-hidden="true"></i>';
        btn.addEventListener("click", function () {
            const isHidden = input.type === "password";
            input.type = isHidden ? "text" : "password";
            btn.innerHTML = isHidden
                ? '<i class="fa fa-eye-slash" aria-hidden="true"></i>'
                : '<i class="fa fa-eye" aria-hidden="true"></i>';
        });
        wrapper.appendChild(btn);
    }

    function updatePasswordMeter(form, pwd) {
        const meter = form.querySelector(".georutex-password-meter");
        if (!meter) return;

        const rules = checkPasswordRules(pwd);
        const mapping = {
            "min-length": rules.minLength && rules.noSpaces,
            upper: rules.hasUpper,
            lower: rules.hasLower,
            digit: rules.hasDigit,
            special: rules.hasSpecial,
        };

        let score = 0;
        Object.keys(mapping).forEach(function (key) {
            const item = meter.querySelector('[data-rule="' + key + '"]');
            const met = Boolean(mapping[key]);
            if (met) score += 1;
            if (item) {
                item.classList.toggle("is-met", met);
                const icon = item.querySelector("i");
                if (icon) {
                    icon.className = met
                        ? "fa fa-check-circle"
                        : "fa fa-circle-o";
                }
            }
        });

        const bar = meter.querySelector(".progress-bar");
        const label = meter.querySelector(".georutex-meter-label");
        const pct = Math.round((score / 5) * 100);
        if (bar) {
            bar.style.width = pct + "%";
            bar.classList.remove("bg-danger", "bg-warning", "bg-info", "bg-primary", "bg-success");
            if (score <= 2) {
                bar.classList.add("bg-danger");
            } else if (score === 3) {
                bar.classList.add("bg-warning");
            } else if (score === 4) {
                bar.classList.add("bg-info");
            } else {
                bar.classList.add("bg-primary");
            }
        }
        if (label) {
            const labels = ["Muy débil", "Débil", "Regular", "Media", "Buena", "Segura"];
            label.textContent = pwd ? labels[score] : "Sin ingresar";
        }
    }

    function initLoginForm() {
        const form = document.querySelector("form.oe_login_form");
        if (!form) return;

        const loginInput = form.querySelector('input[name="login"]');
        const pwdInput = form.querySelector('input[name="password"]');
        attachPasswordToggle(pwdInput);

        if (loginInput) {
            loginInput.addEventListener("blur", function () {
                setFieldState(loginInput, validateEmail(loginInput.value, true));
            });
        }

        form.addEventListener("submit", function (event) {
            let ok = true;
            if (loginInput) {
                ok = setFieldState(loginInput, validateEmail(loginInput.value, true)) && ok;
            }
            if (pwdInput) {
                const pwdErr = (pwdInput.value || "")
                    ? ""
                    : "Debe ingresar su contraseña.";
                ok = setFieldState(pwdInput, pwdErr) && ok;
            }
            if (!ok) {
                event.preventDefault();
                event.stopPropagation();
            }
        });
    }

    function initSignupForm() {
        const form = document.querySelector("form.oe_signup_form");
        if (!form) return;

        const nameInput = form.querySelector('input[name="name"]');
        const loginInput = form.querySelector('input[name="login"]');
        const pwdInput = form.querySelector('input[name="password"]');
        const confirmInput = form.querySelector('input[name="confirm_password"]');

        attachPasswordToggle(pwdInput);
        attachPasswordToggle(confirmInput);

        if (nameInput) {
            nameInput.addEventListener("input", function () {
                setFieldState(nameInput, validateName(nameInput.value));
            });
        }
        if (loginInput) {
            loginInput.addEventListener("blur", function () {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                setFieldState(loginInput, validateEmail(loginInput.value, false));
            });
        }
        if (pwdInput) {
            const onPwdChange = function () {
                updatePasswordMeter(form, pwdInput.value);
                if (pwdInput.value) {
                    setFieldState(pwdInput, validateStrongPassword(pwdInput.value));
                }
                if (confirmInput && confirmInput.value) {
                    const matchErr =
                        confirmInput.value === pwdInput.value
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr);
                }
            };
            pwdInput.addEventListener("input", onPwdChange);
            pwdInput.addEventListener("keyup", onPwdChange);
            pwdInput.addEventListener("change", onPwdChange);
            if (pwdInput.value) {
                onPwdChange();
            }
        }
        if (confirmInput) {
            const onConfirmChange = function () {
                const matchErr =
                    confirmInput.value === (pwdInput ? pwdInput.value : "")
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                setFieldState(confirmInput, matchErr);
            };
            confirmInput.addEventListener("input", onConfirmChange);
            confirmInput.addEventListener("keyup", onConfirmChange);
            confirmInput.addEventListener("change", onConfirmChange);
        }

        form.addEventListener("submit", function (event) {
            let ok = true;
            if (nameInput) {
                nameInput.value = (nameInput.value || "").trim();
                ok = setFieldState(nameInput, validateName(nameInput.value)) && ok;
            }
            if (loginInput) {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                ok = setFieldState(loginInput, validateEmail(loginInput.value, false)) && ok;
            }
            if (pwdInput) {
                updatePasswordMeter(form, pwdInput.value);
                ok = setFieldState(pwdInput, validateStrongPassword(pwdInput.value)) && ok;
            }
            if (confirmInput) {
                const matchErr =
                    confirmInput.value === (pwdInput ? pwdInput.value : "")
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                ok = setFieldState(confirmInput, matchErr) && ok;
            }
            if (!ok) {
                event.preventDefault();
                event.stopPropagation();
            }
        });
    }

    function initResetForm() {
        const form = document.querySelector("form.oe_reset_password_form");
        if (!form) return;

        const loginInput = form.querySelector('input[name="login"]');
        const pwdInput = form.querySelector('input[name="password"]');
        const confirmInput = form.querySelector('input[name="confirm_password"]');

        attachPasswordToggle(pwdInput);
        attachPasswordToggle(confirmInput);

        if (pwdInput) {
            pwdInput.addEventListener("input", function () {
                updatePasswordMeter(form, pwdInput.value);
                setFieldState(pwdInput, validateStrongPassword(pwdInput.value));
            });
        }

        form.addEventListener("submit", function (event) {
            let ok = true;
            if (loginInput && !pwdInput) {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                ok = setFieldState(loginInput, validateEmail(loginInput.value, false)) && ok;
            }
            if (pwdInput) {
                ok = setFieldState(pwdInput, validateStrongPassword(pwdInput.value)) && ok;
            }
            if (confirmInput && pwdInput) {
                const matchErr =
                    confirmInput.value === pwdInput.value
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                ok = setFieldState(confirmInput, matchErr) && ok;
            }
            if (!ok) {
                event.preventDefault();
                event.stopPropagation();
            }
        });
    }

    function initOtpForm() {
        const form = document.querySelector("form.georutex-otp-form");
        if (!form) return;

        const digits = Array.from(form.querySelectorAll(".georutex-otp-digit"));
        const hiddenInput = form.querySelector("#georutex_otp_hidden");

        function syncHidden() {
            if (hiddenInput) {
                hiddenInput.value = digits.map(function (el) {
                    return (el.value || "").replace(/\D/g, "").slice(0, 1);
                }).join("");
            }
        }

        digits.forEach(function (input, idx) {
            input.addEventListener("input", function () {
                const cleaned = (input.value || "").replace(/\D/g, "");
                if (cleaned.length > 1) {
                    cleaned.slice(0, digits.length).split("").forEach(function (ch, offset) {
                        if (digits[offset]) digits[offset].value = ch;
                    });
                    const lastIdx = Math.min(cleaned.length, digits.length) - 1;
                    if (lastIdx >= 0) digits[lastIdx].focus();
                } else {
                    input.value = cleaned;
                    if (cleaned && digits[idx + 1]) {
                        digits[idx + 1].focus();
                    }
                }
                syncHidden();
            });

            input.addEventListener("keydown", function (event) {
                if (event.key === "Backspace" && !input.value && digits[idx - 1]) {
                    digits[idx - 1].focus();
                }
            });

            input.addEventListener("paste", function (event) {
                const pasted = (event.clipboardData || window.clipboardData)
                    .getData("text")
                    .replace(/\D/g, "");
                if (pasted) {
                    event.preventDefault();
                    pasted.slice(0, digits.length).split("").forEach(function (ch, i) {
                        if (digits[i]) digits[i].value = ch;
                    });
                    const target = digits[Math.min(pasted.length, digits.length) - 1];
                    if (target) target.focus();
                    syncHidden();
                }
            });
        });

        form.addEventListener("submit", function (event) {
            syncHidden();
            if (!hiddenInput || hiddenInput.value.length !== 6) {
                event.preventDefault();
                digits.forEach(function (el) {
                    if (!el.value) el.classList.add("is-invalid");
                });
                const firstEmpty = digits.find(function (el) {
                    return !el.value;
                });
                if (firstEmpty) firstEmpty.focus();
            }
        });
    }

    function bootstrapGeoRutexAuth() {
        if (window.__georutexAuthInitDone) return;
        window.__georutexAuthInitDone = true;
        initLoginForm();
        initSignupForm();
        initResetForm();
        initOtpForm();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrapGeoRutexAuth);
    } else {
        bootstrapGeoRutexAuth();
    }
    window.addEventListener("load", bootstrapGeoRutexAuth);
})();
