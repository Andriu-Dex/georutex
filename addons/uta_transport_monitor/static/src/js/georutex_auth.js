/* GeoRutex Unified Authentication — Dynamic Colorimetry & GSAP 3.13.0 Motion
 * - Scene-linked CSS variable colorimetry (Seguimiento #E5EEF8, Organización #E5EFEB, Evaluación #ECEAF4)
 * - Coordinated exit/color/enter carousel timelines (Clip-Path, SplitText, DrawSVG, MotionPath, Flip)
 * - Real continuous progress bar with pause/resume without reset + visibilitychange pause
 * - Cross-route scene persistence & first-visit-only entrance choreography via sessionStorage
 * - Atomic GSAP-driven password composition indicator ("Requisitos cumplidos (5/5)")
 * - Accessible deferred validation, 6-digit OTP UX, cooldown timer, double-submit guard
 */
(function () {
    "use strict";

    const SCENE_STORAGE_KEY = "grx.auth.sceneIdx";
    const INTRO_SEEN_KEY = "grx.auth.introSeen";

    const SCENE_THEMES = [
        {
            name: "Seguimiento",
            bg: "#e5eef8",
            accent: "#1a56db",
            accentSoft: "rgba(26, 86, 219, 0.14)",
            dot: "#0bbcd7",
            scrimBot: "rgba(15, 29, 54, 0.88)",
            border: "rgba(26, 86, 219, 0.14)",
            arc1: "#0bbcd7",
            arc2: "#0bbcd7",
            arc3: "#1a56db",
            beaconStroke: "#1a56db",
            beaconHalo: "rgba(11, 188, 215, 0.36)",
            nodeProgress: 0.14,
        },
        {
            name: "Organización",
            bg: "#e5efeb",
            accent: "#0f766e",
            accentSoft: "rgba(15, 118, 110, 0.14)",
            dot: "#14b8a6",
            scrimBot: "rgba(14, 34, 38, 0.90)",
            border: "rgba(15, 118, 110, 0.16)",
            arc1: "#14b8a6",
            arc2: "#0d9488",
            arc3: "#0f766e",
            beaconStroke: "#0f766e",
            beaconHalo: "rgba(20, 184, 166, 0.36)",
            nodeProgress: 0.52,
        },
        {
            name: "Evaluación",
            bg: "#eceaf4",
            accent: "#3730a3",
            accentSoft: "rgba(55, 48, 163, 0.14)",
            dot: "#fc0154",
            scrimBot: "rgba(20, 19, 44, 0.89)",
            border: "rgba(55, 48, 163, 0.16)",
            arc1: "#6366f1",
            arc2: "#3730a3",
            arc3: "#fc0154",
            beaconStroke: "#3730a3",
            beaconHalo: "rgba(252, 1, 84, 0.34)",
            nodeProgress: 0.88,
        },
    ];

    const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
    const ALLOWED_NAME_CHARS_RE = /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s'\u2019-]+$/;
    const NAME_SEGMENT_RE =
        /^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*(?:['\u2019][A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)?$/;
    const NAME_PARTICLES = new Set([
        "de", "del", "la", "las", "los", "y", "e",
        "da", "do", "dos", "das", "van", "von", "di",
    ]);
    const SPECIAL_RE = /[^A-Za-z0-9\s]/;
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

    const cleanupHandlers = [];

    function registerCleanup(fn) {
        if (typeof fn === "function") cleanupHandlers.push(fn);
    }

    // =========================================================================
    // 1. VALIDATION HELPERS (MIRRORS domain/auth_validation.py)
    // =========================================================================
    function isValidNameWord(word) {
        if (!word || word.startsWith("-") || word.endsWith("-")) return false;
        if (/^['\u2019]|['\u2019]$/.test(word)) return false;
        if (/--|''|\u2019\u2019/.test(word)) return false;
        const segments = word.split("-");
        for (let i = 0; i < segments.length; i += 1) {
            const seg = segments[i];
            if (!seg) return false;
            if (!/['\u2019]/.test(seg) && seg.length < 2) return false;
            if (!NAME_SEGMENT_RE.test(seg)) return false;
        }
        return true;
    }

    function validateName(value) {
        const raw = (value || "").trim();
        if (!raw) return "Ingresa tu nombre y apellido.";
        if (raw.length < 5 || raw.length > 80) {
            return "El nombre completo debe tener entre 5 y 80 caracteres.";
        }
        if (/\s{2,}/.test(raw)) {
            return "No utilices espacios dobles entre nombres y apellidos.";
        }
        if (!ALLOWED_NAME_CHARS_RE.test(raw)) {
            return "Solo se permiten letras, espacios, guiones o apóstrofos.";
        }
        const words = raw.split(" ");
        if (words.length < 2) {
            return "Ingresa al menos un nombre y un apellido (ejemplo: Juan Pérez).";
        }
        let significant = 0;
        for (let i = 0; i < words.length; i += 1) {
            const isEdge = i === 0 || i === words.length - 1;
            if (!isEdge && NAME_PARTICLES.has(words[i])) continue;
            if (!isValidNameWord(words[i])) {
                return "Cada nombre y apellido debe iniciar con mayúscula (ejemplo: María José López).";
            }
            significant += 1;
        }
        if (significant < 2) {
            return "Ingresa al menos un nombre y un apellido válidos.";
        }
        return "";
    }

    function validateEmail(value, allowAdmin) {
        const cleaned = (value || "").trim().toLowerCase();
        if (!cleaned) return "Ingresa tu correo electrónico.";
        if (allowAdmin && cleaned === "admin") return "";
        if (cleaned.length > 120) return "El correo electrónico excede la longitud permitida.";
        if (/\s/.test(cleaned) || !EMAIL_RE.test(cleaned)) {
            return "Ingresa un correo electrónico válido (ejemplo: nombre@correo.com).";
        }
        const domain = cleaned.split("@")[1] || "";
        if (cleaned.includes("..") || domain.startsWith(".") || domain.startsWith("-")) {
            return "El dominio del correo electrónico no tiene un formato válido.";
        }
        if (COMMON_DOMAIN_TYPOS[domain]) {
            return `El dominio '@${domain}' parece contener un error. ¿Quisiste escribir '@${COMMON_DOMAIN_TYPOS[domain]}'?`;
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
        if (!value) return "Ingresa una contraseña.";
        const rules = checkPasswordRules(value);
        const missing = [];
        if (!rules.minLength) missing.push("entre 8 y 64 caracteres");
        if (!rules.noSpaces) missing.push("sin espacios");
        if (!rules.hasUpper) missing.push("una mayúscula");
        if (!rules.hasLower) missing.push("una minúscula");
        if (!rules.hasDigit) missing.push("un número");
        if (!rules.hasSpecial) missing.push("un carácter especial");
        if (missing.length) {
            return "La contraseña debe incluir: " + missing.join(", ") + ".";
        }
        return "";
    }

    // =========================================================================
    // 2. ACCESSIBLE FIELD FEEDBACK, TOGGLES & ATOMIC GSAP PASSWORD METER
    // =========================================================================
    function getOrCreateFeedback(input) {
        const anchor = input.closest(".grx-pwd-group") || input;
        const parent = anchor.parentElement;
        let feedback = parent ? parent.querySelector(".grx-field-feedback") : null;
        if (!feedback && parent) {
            feedback = document.createElement("div");
            feedback.className = "grx-field-feedback";
            feedback.setAttribute("role", "alert");
            feedback.id = (input.id || input.name || "field") + "_feedback";
            anchor.insertAdjacentElement("afterend", feedback);
        }
        return feedback;
    }

    function setFieldState(input, errorMessage, gsap, reduceMotion) {
        if (!input) return true;
        const feedback = getOrCreateFeedback(input);
        if (errorMessage) {
            const wasInvalid = input.classList.contains("is-invalid");
            input.classList.add("is-invalid");
            input.classList.remove("is-valid");
            input.setAttribute("aria-invalid", "true");
            if (feedback) {
                input.setAttribute("aria-describedby", feedback.id);
                feedback.textContent = errorMessage;
                feedback.classList.add("is-visible");
                if (!wasInvalid && gsap && !reduceMotion) {
                    gsap.fromTo(
                        feedback,
                        { y: -4, opacity: 0 },
                        { y: 0, opacity: 1, duration: 0.2, ease: "power2.out", clearProps: "transform,opacity" }
                    );
                }
            }
            return false;
        }
        input.classList.remove("is-invalid");
        input.removeAttribute("aria-invalid");
        if ((input.value || "").trim()) {
            input.classList.add("is-valid");
        } else {
            input.classList.remove("is-valid");
        }
        if (feedback) {
            feedback.textContent = "";
            feedback.classList.remove("is-visible");
        }
        return true;
    }

    function attachPasswordToggle(input) {
        if (!input || input.dataset.grxToggle === "1") return;
        input.dataset.grxToggle = "1";

        const wrapper = document.createElement("div");
        wrapper.className = "grx-pwd-group";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "grx-pwd-toggle";
        btn.setAttribute("aria-label", "Mostrar contraseña");
        btn.setAttribute("aria-pressed", "false");
        btn.innerHTML = '<i class="fa fa-eye" aria-hidden="true"></i>';

        btn.addEventListener("click", function () {
            const reveal = input.type === "password";
            input.type = reveal ? "text" : "password";
            btn.setAttribute("aria-pressed", reveal ? "true" : "false");
            btn.setAttribute("aria-label", reveal ? "Ocultar contraseña" : "Mostrar contraseña");
            btn.innerHTML = reveal
                ? '<i class="fa fa-eye-slash" aria-hidden="true"></i>'
                : '<i class="fa fa-eye" aria-hidden="true"></i>';
        });
        wrapper.appendChild(btn);
    }

    function setSubmitLoading(form, loadingText) {
        const btn =
            form.querySelector('button[type="submit"]:not([name])') ||
            form.querySelector('button[type="submit"]');
        if (!btn || btn.dataset.grxSubmitting === "1") return;
        btn.dataset.grxSubmitting = "1";
        btn.classList.add("is-loading");
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        const label = btn.querySelector(".grx-btn-label");
        if (label && loadingText) label.textContent = loadingText;
    }

    // Single source of truth for composition checklist, bar progress, color, and text
    function updatePasswordMeter(form, pwd, gsap, reduceMotion) {
        const meter = form.querySelector(".grx-password-meter");
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
            if (!item) return;

            const wasMet = item.classList.contains("is-met");
            item.classList.toggle("is-met", met);
            const icon = item.querySelector("i");
            if (icon) {
                icon.className = met ? "fa fa-check-circle" : "fa fa-circle-o";
                if (met && !wasMet && gsap && !reduceMotion) {
                    gsap.fromTo(
                        icon,
                        { scale: 0.72 },
                        { scale: 1, duration: 0.22, ease: "back.out(2.2)", clearProps: "transform" }
                    );
                }
            }
        });

        const fill = meter.querySelector(".grx-meter-fill");
        const track = meter.querySelector(".grx-meter-track");
        const label = meter.querySelector(".grx-meter-label");
        const pct = pwd ? Math.round((score / 5) * 100) : 0;

        let barColor = "#94a3b8";
        let stateClass = "";
        let statusText = "0 de 5 requisitos";

        if (!pwd) {
            barColor = "#94a3b8";
            statusText = "0 de 5 requisitos";
        } else if (score <= 2) {
            barColor = "#dc2626";
            stateClass = "is-weak";
            statusText = `${score} de 5 requisitos`;
        } else if (score === 3) {
            barColor = "#d97706";
            stateClass = "is-medium";
            statusText = "3 de 5 requisitos";
        } else if (score === 4) {
            barColor = "#0bbcd7";
            stateClass = "is-medium";
            statusText = "4 de 5 requisitos";
        } else {
            barColor = "#15803d";
            stateClass = "is-strong";
            statusText = "Requisitos cumplidos (5/5)";
        }

        if (track) track.setAttribute("aria-valuenow", String(score));

        if (fill) {
            if (gsap && !reduceMotion) {
                gsap.to(fill, {
                    width: pct + "%",
                    backgroundColor: barColor,
                    duration: 0.28,
                    ease: "power2.out",
                    overwrite: "auto",
                });
            } else {
                fill.style.width = pct + "%";
                fill.style.backgroundColor = barColor;
            }
        }

        if (label) {
            label.textContent = statusText;
            label.classList.remove("is-weak", "is-medium", "is-strong");
            if (stateClass) label.classList.add(stateClass);
        }
    }

    // =========================================================================
    // 3. FORM CONTROLLERS (DEFERRED ERRORS, REAL LOADING, ZERO DUPLICATES)
    // =========================================================================
    function initLoginForm(gsap, reduceMotion) {
        const form = document.querySelector("form.oe_login_form");
        if (!form) return;

        const loginInput = form.querySelector('input[name="login"]');
        const pwdInput = form.querySelector('input[name="password"]');
        attachPasswordToggle(pwdInput);

        if (loginInput) {
            let touched = false;
            loginInput.addEventListener("blur", function () {
                if ((loginInput.value || "").trim()) {
                    touched = true;
                    setFieldState(loginInput, validateEmail(loginInput.value, true), gsap, reduceMotion);
                }
            });
            loginInput.addEventListener("input", function () {
                if (touched) setFieldState(loginInput, validateEmail(loginInput.value, true), gsap, reduceMotion);
            });
        }
        if (pwdInput) {
            pwdInput.addEventListener("input", function () {
                if (pwdInput.classList.contains("is-invalid") && pwdInput.value) {
                    setFieldState(pwdInput, "", gsap, reduceMotion);
                }
            });
        }

        form.addEventListener("submit", function (event) {
            if (form.dataset.grxLocked === "1") {
                event.preventDefault();
                return;
            }
            let ok = true;
            if (loginInput) {
                ok = setFieldState(loginInput, validateEmail(loginInput.value, true), gsap, reduceMotion) && ok;
            }
            if (pwdInput) {
                const pwdErr = pwdInput.value ? "" : "Ingresa tu contraseña.";
                ok = setFieldState(pwdInput, pwdErr, gsap, reduceMotion) && ok;
            }
            if (!ok) {
                event.preventDefault();
                event.stopPropagation();
                const firstBad = form.querySelector(".is-invalid");
                if (firstBad) firstBad.focus();
                return;
            }
            form.dataset.grxLocked = "1";
            setSubmitLoading(form, "Iniciando sesión…");
        });
    }

    function initSignupForm(gsap, reduceMotion) {
        const form = document.querySelector("form.oe_signup_form");
        if (!form) return;

        const loginInput = form.querySelector('input[name="login"]');
        const nameInput = form.querySelector('input[name="name"]');
        const pwdInput = form.querySelector('input[name="password"]');
        const confirmInput = form.querySelector('input[name="confirm_password"]');

        attachPasswordToggle(pwdInput);
        attachPasswordToggle(confirmInput);

        if (loginInput) {
            let touched = false;
            loginInput.addEventListener("blur", function () {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                if (loginInput.value) {
                    touched = true;
                    setFieldState(loginInput, validateEmail(loginInput.value, false), gsap, reduceMotion);
                }
            });
            loginInput.addEventListener("input", function () {
                if (touched) setFieldState(loginInput, validateEmail(loginInput.value, false), gsap, reduceMotion);
            });
        }

        if (nameInput) {
            let touched = false;
            nameInput.addEventListener("blur", function () {
                if ((nameInput.value || "").trim()) {
                    touched = true;
                    setFieldState(nameInput, validateName(nameInput.value), gsap, reduceMotion);
                }
            });
            nameInput.addEventListener("input", function () {
                if (touched) setFieldState(nameInput, validateName(nameInput.value), gsap, reduceMotion);
            });
        }

        if (pwdInput) {
            let touched = false;
            const onPwdInput = function () {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
                if (touched) {
                    setFieldState(pwdInput, validateStrongPassword(pwdInput.value), gsap, reduceMotion);
                }
                if (confirmInput && confirmInput.value) {
                    const matchErr =
                        confirmInput.value === pwdInput.value
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr, gsap, reduceMotion);
                }
            };
            pwdInput.addEventListener("input", onPwdInput);
            pwdInput.addEventListener("blur", function () {
                if (pwdInput.value) {
                    touched = true;
                    setFieldState(pwdInput, validateStrongPassword(pwdInput.value), gsap, reduceMotion);
                }
            });
            updatePasswordMeter(form, pwdInput.value, gsap, true);
        }

        if (confirmInput) {
            let touched = false;
            const checkConfirm = function () {
                const matchErr =
                    confirmInput.value === (pwdInput ? pwdInput.value : "")
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                setFieldState(confirmInput, matchErr, gsap, reduceMotion);
            };
            confirmInput.addEventListener("blur", function () {
                if (confirmInput.value) {
                    touched = true;
                    checkConfirm();
                }
            });
            confirmInput.addEventListener("input", function () {
                if (touched || (pwdInput && confirmInput.value.length >= pwdInput.value.length && confirmInput.value.length > 0)) {
                    checkConfirm();
                }
            });
        }

        form.addEventListener("submit", function (event) {
            if (form.dataset.grxLocked === "1") {
                event.preventDefault();
                return;
            }
            let ok = true;
            if (loginInput) {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                ok = setFieldState(loginInput, validateEmail(loginInput.value, false), gsap, reduceMotion) && ok;
            }
            if (nameInput) {
                nameInput.value = (nameInput.value || "").trim();
                ok = setFieldState(nameInput, validateName(nameInput.value), gsap, reduceMotion) && ok;
            }
            if (pwdInput) {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
                ok = setFieldState(pwdInput, validateStrongPassword(pwdInput.value), gsap, reduceMotion) && ok;
            }
            if (confirmInput) {
                const matchErr =
                    confirmInput.value === (pwdInput ? pwdInput.value : "")
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                ok = setFieldState(confirmInput, matchErr, gsap, reduceMotion) && ok;
            }
            if (!ok) {
                event.preventDefault();
                event.stopPropagation();
                const firstBad = form.querySelector(".is-invalid");
                if (firstBad) firstBad.focus();
                return;
            }
            form.dataset.grxLocked = "1";
            setSubmitLoading(form, "Creando cuenta…");
        });
    }

    function initResetForm(gsap, reduceMotion) {
        const form = document.querySelector("form.oe_reset_password_form");
        if (!form) return;

        const loginInput = form.querySelector('input[name="login"]:not([readonly])');
        const pwdInput = form.querySelector('input[name="password"]');
        const confirmInput = form.querySelector('input[name="confirm_password"]');

        attachPasswordToggle(pwdInput);
        attachPasswordToggle(confirmInput);

        if (loginInput && !pwdInput) {
            let touched = false;
            loginInput.addEventListener("blur", function () {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                if (loginInput.value) {
                    touched = true;
                    setFieldState(loginInput, validateEmail(loginInput.value, false), gsap, reduceMotion);
                }
            });
            loginInput.addEventListener("input", function () {
                if (touched) setFieldState(loginInput, validateEmail(loginInput.value, false), gsap, reduceMotion);
            });
        }

        if (pwdInput) {
            let touched = false;
            pwdInput.addEventListener("input", function () {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
                if (touched) setFieldState(pwdInput, validateStrongPassword(pwdInput.value), gsap, reduceMotion);
                if (confirmInput && confirmInput.value) {
                    const matchErr =
                        confirmInput.value === pwdInput.value
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr, gsap, reduceMotion);
                }
            });
            pwdInput.addEventListener("blur", function () {
                if (pwdInput.value) {
                    touched = true;
                    setFieldState(pwdInput, validateStrongPassword(pwdInput.value), gsap, reduceMotion);
                }
            });
            updatePasswordMeter(form, pwdInput.value, gsap, true);
        }

        if (confirmInput) {
            let touched = false;
            confirmInput.addEventListener("blur", function () {
                if (confirmInput.value) {
                    touched = true;
                    const matchErr =
                        confirmInput.value === (pwdInput ? pwdInput.value : "")
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr, gsap, reduceMotion);
                }
            });
            confirmInput.addEventListener("input", function () {
                if (touched) {
                    const matchErr =
                        confirmInput.value === (pwdInput ? pwdInput.value : "")
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr, gsap, reduceMotion);
                }
            });
        }

        form.addEventListener("submit", function (event) {
            if (form.dataset.grxLocked === "1") {
                event.preventDefault();
                return;
            }
            let ok = true;
            if (loginInput && !pwdInput) {
                loginInput.value = (loginInput.value || "").trim().toLowerCase();
                ok = setFieldState(loginInput, validateEmail(loginInput.value, false), gsap, reduceMotion) && ok;
            }
            if (pwdInput) {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
                ok = setFieldState(pwdInput, validateStrongPassword(pwdInput.value), gsap, reduceMotion) && ok;
            }
            if (confirmInput && pwdInput) {
                const matchErr =
                    confirmInput.value === pwdInput.value
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                ok = setFieldState(confirmInput, matchErr, gsap, reduceMotion) && ok;
            }
            if (!ok) {
                event.preventDefault();
                event.stopPropagation();
                const firstBad = form.querySelector(".is-invalid");
                if (firstBad) firstBad.focus();
                return;
            }
            form.dataset.grxLocked = "1";
            setSubmitLoading(
                form,
                pwdInput ? "Actualizando contraseña…" : "Enviando instrucciones…"
            );
        });
    }

    function initOtpForm(gsap, reduceMotion) {
        const form = document.querySelector("form.grx-otp-form");
        if (!form) return;

        const digits = Array.from(form.querySelectorAll(".grx-otp-digit"));
        const hiddenInput = form.querySelector("#georutex_otp_hidden");
        const errorBox = form.querySelector("#grxOtpInlineError");
        let wasComplete = false;

        function syncHidden() {
            const combined = digits
                .map(function (el) {
                    const v = (el.value || "").replace(/\D/g, "").slice(0, 1);
                    el.classList.toggle("is-filled", Boolean(v));
                    if (v) el.classList.remove("is-invalid");
                    return v;
                })
                .join("");
            if (hiddenInput) hiddenInput.value = combined;
            if (errorBox && combined.length === digits.length) {
                errorBox.classList.remove("is-visible");
                errorBox.textContent = "";
            }
            const isComplete = combined.length === digits.length;
            if (isComplete && !wasComplete && gsap && !reduceMotion) {
                gsap.fromTo(
                    digits,
                    { scale: 0.95 },
                    { scale: 1, duration: 0.22, stagger: 0.025, ease: "back.out(2)", clearProps: "transform" }
                );
            }
            wasComplete = isComplete;
        }

        digits.forEach(function (input, idx) {
            input.addEventListener("input", function () {
                const cleaned = (input.value || "").replace(/\D/g, "");
                if (cleaned.length > 1) {
                    cleaned.slice(0, digits.length).split("").forEach(function (ch, offset) {
                        if (digits[offset]) digits[offset].value = ch;
                    });
                    const target = digits[Math.min(cleaned.length, digits.length) - 1];
                    if (target) target.focus();
                } else {
                    input.value = cleaned;
                    if (cleaned && gsap && !reduceMotion) {
                        gsap.fromTo(input, { scale: 0.94 }, { scale: 1, duration: 0.18, clearProps: "transform" });
                    }
                    if (cleaned && digits[idx + 1]) digits[idx + 1].focus();
                }
                syncHidden();
            });

            input.addEventListener("keydown", function (event) {
                if (event.key === "Backspace" && !input.value && digits[idx - 1]) {
                    digits[idx - 1].value = "";
                    digits[idx - 1].focus();
                    syncHidden();
                } else if (event.key === "ArrowLeft" && digits[idx - 1]) {
                    event.preventDefault();
                    digits[idx - 1].focus();
                } else if (event.key === "ArrowRight" && digits[idx + 1]) {
                    event.preventDefault();
                    digits[idx + 1].focus();
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
            if (form.dataset.grxLocked === "1") {
                event.preventDefault();
                return;
            }
            syncHidden();
            if (!hiddenInput || hiddenInput.value.length !== 6) {
                event.preventDefault();
                digits.forEach(function (el) {
                    if (!el.value) el.classList.add("is-invalid");
                });
                if (errorBox) {
                    errorBox.textContent = "Completa los 6 dígitos del código enviado a tu correo.";
                    errorBox.classList.add("is-visible");
                }
                const firstEmpty = digits.find(function (el) { return !el.value; });
                if (firstEmpty) firstEmpty.focus();
                return;
            }
            form.dataset.grxLocked = "1";
            setSubmitLoading(form, "Verificando código…");
        });

        // Server-synced resend cooldown timer
        const resendBtn = document.getElementById("grxResendBtn");
        if (resendBtn) {
            let remaining = parseInt(resendBtn.dataset.cooldown || "0", 10);
            const labelEl = resendBtn.querySelector(".grx-resend-label");
            const renderCooldown = function () {
                if (remaining > 0) {
                    resendBtn.disabled = true;
                    if (labelEl) labelEl.textContent = `Reenviar código (${remaining} s)`;
                } else {
                    resendBtn.disabled = false;
                    if (labelEl) labelEl.textContent = "Reenviar código";
                }
            };
            renderCooldown();
            if (remaining > 0) {
                const timer = window.setInterval(function () {
                    remaining -= 1;
                    renderCooldown();
                    if (remaining <= 0) window.clearInterval(timer);
                }, 1000);
                registerCleanup(() => window.clearInterval(timer));
            }
        }
    }

    // =========================================================================
    // 4. DYNAMIC COLORIMETRY & COORDINATED 3-SCENE CAROUSEL
    // =========================================================================
    function readSavedSceneIdx() {
        try {
            const raw = window.sessionStorage.getItem(SCENE_STORAGE_KEY);
            const idx = parseInt(raw || "0", 10);
            return idx >= 0 && idx < SCENE_THEMES.length ? idx : 0;
        } catch (_err) {
            return 0;
        }
    }

    function saveSceneIdx(idx) {
        try {
            window.sessionStorage.setItem(SCENE_STORAGE_KEY, String(idx));
        } catch (_err) {
            // Ignore restricted storage environments
        }
    }

    function initVisualCarousel(gsap, SplitText, Flip, DrawSVGPlugin, MotionPathPlugin, reduceMotion, isFirstVisit) {
        const visualPanel = document.querySelector(".grx-auth-visual");
        const stage = document.getElementById("grxSceneStage");
        const slides = Array.from(document.querySelectorAll(".grx-scene-slide"));
        const tabs = Array.from(document.querySelectorAll(".grx-carousel-tab"));
        const toggleBtn = document.getElementById("grxCarouselToggle");
        if (!visualPanel || !stage || slides.length < 2) return null;

        const SCENE_DURATION_SEC = 6.4;
        let currentIdx = readSavedSceneIdx();
        let manualPaused = Boolean(reduceMotion);
        let inputFocused = false;
        let hovered = false;
        let tabHidden = Boolean(document.hidden);
        let progressTween = null;
        let transitionTl = null;
        const splitMap = new Map();

        const shouldAutoplayRun = () =>
            !manualPaused &&
            !inputFocused &&
            !hovered &&
            !tabHidden &&
            !reduceMotion &&
            window.getComputedStyle(stage).display !== "none";

        const updateToggleUI = () => {
            if (!toggleBtn) return;
            toggleBtn.setAttribute("aria-pressed", manualPaused ? "true" : "false");
            toggleBtn.setAttribute(
                "aria-label",
                manualPaused ? "Reanudar presentación visual" : "Pausar presentación visual"
            );
            toggleBtn.innerHTML = manualPaused
                ? '<i class="fa fa-play" aria-hidden="true"></i>'
                : '<i class="fa fa-pause" aria-hidden="true"></i>';
        };

        const applyThemeColors = (idx, instant) => {
            const theme = SCENE_THEMES[idx] || SCENE_THEMES[0];
            const dur = instant || reduceMotion ? 0 : 0.72;
            const cssVars = {
                "--grx-scene-bg": theme.bg,
                "--grx-scene-accent": theme.accent,
                "--grx-scene-accent-soft": theme.accentSoft,
                "--grx-scene-dot": theme.dot,
                "--grx-scene-scrim-bot": theme.scrimBot,
                "--grx-scene-border": theme.border,
            };
            if (gsap && dur > 0) {
                gsap.to(visualPanel, { ...cssVars, duration: dur, ease: "power2.inOut", overwrite: "auto" });
                const stop1 = document.getElementById("grxArcStop1");
                const stop2 = document.getElementById("grxArcStop2");
                const stop3 = document.getElementById("grxArcStop3");
                const halo = document.getElementById("grxBeaconHalo");
                const core = document.getElementById("grxBeaconCore");
                if (stop1) gsap.to(stop1, { attr: { "stop-color": theme.arc1 }, duration: dur });
                if (stop2) gsap.to(stop2, { attr: { "stop-color": theme.arc2 }, duration: dur });
                if (stop3) gsap.to(stop3, { attr: { "stop-color": theme.arc3 }, duration: dur });
                if (halo) gsap.to(halo, { attr: { fill: theme.beaconHalo }, duration: dur });
                if (core) gsap.to(core, { attr: { stroke: theme.beaconStroke }, duration: dur });
            } else {
                Object.keys(cssVars).forEach((k) => visualPanel.style.setProperty(k, cssVars[k]));
                const stop1 = document.getElementById("grxArcStop1");
                const stop2 = document.getElementById("grxArcStop2");
                const stop3 = document.getElementById("grxArcStop3");
                const halo = document.getElementById("grxBeaconHalo");
                const core = document.getElementById("grxBeaconCore");
                if (stop1) stop1.setAttribute("stop-color", theme.arc1);
                if (stop2) stop2.setAttribute("stop-color", theme.arc2);
                if (stop3) stop3.setAttribute("stop-color", theme.arc3);
                if (halo) halo.setAttribute("fill", theme.beaconHalo);
                if (core) core.setAttribute("stroke", theme.beaconStroke);
            }
        };

        const moveBeaconTo = (idx, instant) => {
            if (!gsap || !MotionPathPlugin) return;
            const beacon = document.getElementById("grxAuthBeacon");
            const path = document.getElementById("grxAuthRoutePath");
            if (!beacon || !path) return;
            const theme = SCENE_THEMES[idx] || SCENE_THEMES[0];
            gsap.to(beacon, {
                duration: instant || reduceMotion ? 0 : 0.78,
                ease: "power2.inOut",
                motionPath: {
                    path: "#grxAuthRoutePath",
                    align: "#grxAuthRoutePath",
                    alignOrigin: [0.5, 0.5],
                    end: theme.nodeProgress,
                },
            });
            document.querySelectorAll(".grx-route-node").forEach((n, i) => {
                gsap.to(n, {
                    attr: { r: i === idx ? 5.2 : 3.8 },
                    duration: instant || reduceMotion ? 0 : 0.35,
                    ease: "power2.out",
                });
            });
        };

        // Real continuous progress fill that pauses/resumes without resetting!
        const startProgressFor = (idx) => {
            if (progressTween) {
                progressTween.kill();
                progressTween = null;
            }
            tabs.forEach((tab, i) => {
                const fill = tab.querySelector(".grx-tab-fill");
                tab.classList.toggle("is-done", i < idx);
                if (!fill) return;
                if (gsap) gsap.killTweensOf(fill);
                if (i < idx) {
                    fill.style.transform = "scaleX(1)";
                } else if (i === idx && reduceMotion) {
                    fill.style.transform = "scaleX(1)";
                } else {
                    fill.style.transform = "scaleX(0)";
                }
            });

            const activeFill = tabs[idx] ? tabs[idx].querySelector(".grx-tab-fill") : null;
            if (!activeFill || !gsap || reduceMotion) return;

            progressTween = gsap.fromTo(
                activeFill,
                { scaleX: 0 },
                {
                    scaleX: 1,
                    duration: SCENE_DURATION_SEC,
                    ease: "none",
                    paused: !shouldAutoplayRun(),
                    onComplete: () => {
                        activateScene((currentIdx + 1) % slides.length, false);
                    },
                }
            );
        };

        const syncPlayback = () => {
            if (!progressTween) return;
            if (shouldAutoplayRun()) progressTween.play();
            else progressTween.pause();
        };

        const activateScene = (nextIdx, instant) => {
            if (nextIdx === currentIdx && !instant) return;
            const prevSlide = slides[currentIdx];
            const nextSlide = slides[nextIdx];
            if (!nextSlide) return;

            const direction = nextIdx > currentIdx || (currentIdx === slides.length - 1 && nextIdx === 0) ? 1 : -1;
            const flipState = Flip && !reduceMotion && !instant ? Flip.getState(tabs) : null;

            tabs.forEach((tab, i) => {
                const active = i === nextIdx;
                tab.classList.toggle("is-active", active);
                tab.setAttribute("aria-selected", active ? "true" : "false");
            });

            if (Flip && flipState) {
                Flip.from(flipState, { duration: 0.3, ease: "power2.out", simple: true });
            }

            applyThemeColors(nextIdx, instant);
            saveSceneIdx(nextIdx);

            if (!gsap || reduceMotion || instant) {
                slides.forEach((s, i) => {
                    s.classList.remove("is-leaving");
                    s.classList.toggle("is-active", i === nextIdx);
                    s.style.opacity = "";
                    s.style.clipPath = "";
                });
                currentIdx = nextIdx;
                moveBeaconTo(nextIdx, true);
                startProgressFor(nextIdx);
                return;
            }

            if (transitionTl) transitionTl.kill();

            const prevImg = prevSlide ? prevSlide.querySelector("img") : null;
            const prevCap = prevSlide ? prevSlide.querySelector(".grx-scene-caption") : null;
            const nextImg = nextSlide.querySelector("img");
            const nextEyebrow = nextSlide.querySelector(".grx-scene-eyebrow");
            const nextTitle = nextSlide.querySelector(".grx-scene-title");
            const nextDesc = nextSlide.querySelector(".grx-scene-desc");

            slides.forEach((s) => s.classList.remove("is-leaving", "is-active"));
            if (prevSlide && prevSlide !== nextSlide) prevSlide.classList.add("is-leaving");
            nextSlide.classList.add("is-active");

            const startInset =
                direction >= 0
                    ? "inset(0% 0% 0% 100% round 20px)"
                    : "inset(0% 100% 0% 0% round 20px)";

            transitionTl = gsap.timeline({
                defaults: { ease: "power3.out" },
                onComplete: () => {
                    slides.forEach((s) => {
                        s.classList.remove("is-leaving");
                        gsap.set(s, { clearProps: "clipPath,opacity" });
                    });
                    if (prevCap) gsap.set(prevCap, { clearProps: "transform,opacity" });
                    if (prevImg) gsap.set(prevImg, { clearProps: "transform" });
                },
            });

            // 1. Outgoing exit motion
            if (prevCap) {
                transitionTl.to(prevCap, { y: -10, opacity: 0, duration: 0.28, ease: "power2.in" }, 0);
            }
            if (prevImg) {
                transitionTl.to(prevImg, { scale: 1.04, xPercent: direction * -2, duration: 0.64, ease: "power2.inOut" }, 0);
            }

            // 2. Incoming clip-path mask reveal + moderate parallax
            transitionTl.fromTo(
                nextSlide,
                { clipPath: startInset, opacity: 0.85 },
                { clipPath: "inset(0% 0% 0% 0% round 20px)", opacity: 1, duration: 0.76, ease: "power3.inOut" },
                0.04
            );
            if (nextImg) {
                transitionTl.fromTo(
                    nextImg,
                    { scale: 1.07, xPercent: direction * 3 },
                    { scale: 1, xPercent: 0, duration: 0.92, ease: "power3.out", clearProps: "transform" },
                    0.04
                );
            }

            // 3. Coordinated SplitText title + eyebrow & description entrance
            if (nextEyebrow) {
                transitionTl.fromTo(
                    nextEyebrow,
                    { y: 10, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.38, clearProps: "transform,opacity" },
                    0.26
                );
            }
            if (nextTitle && SplitText) {
                let sp = splitMap.get(nextTitle);
                if (!sp) {
                    sp = SplitText.create(nextTitle, { type: "words" });
                    splitMap.set(nextTitle, sp);
                }
                transitionTl.fromTo(
                    sp.words,
                    { y: 14, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.44, stagger: 0.032, clearProps: "transform,opacity" },
                    0.3
                );
            } else if (nextTitle) {
                transitionTl.fromTo(
                    nextTitle,
                    { y: 12, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.42, clearProps: "transform,opacity" },
                    0.3
                );
            }
            if (nextDesc) {
                transitionTl.fromTo(
                    nextDesc,
                    { y: 10, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.42, clearProps: "transform,opacity" },
                    0.38
                );
            }

            currentIdx = nextIdx;
            moveBeaconTo(nextIdx, false);
            startProgressFor(nextIdx);
        };

        tabs.forEach((tab, idx) => {
            tab.addEventListener("click", () => activateScene(idx, false));
            tab.addEventListener("keydown", (ev) => {
                if (ev.key === "ArrowRight") {
                    ev.preventDefault();
                    const n = (idx + 1) % tabs.length;
                    tabs[n].focus();
                    activateScene(n, false);
                } else if (ev.key === "ArrowLeft") {
                    ev.preventDefault();
                    const p = (idx - 1 + tabs.length) % tabs.length;
                    tabs[p].focus();
                    activateScene(p, false);
                }
            });
        });

        if (toggleBtn) {
            toggleBtn.addEventListener("click", () => {
                manualPaused = !manualPaused;
                updateToggleUI();
                syncPlayback();
            });
        }

        const onMouseEnter = () => {
            hovered = true;
            syncPlayback();
        };
        const onMouseLeave = () => {
            hovered = false;
            syncPlayback();
        };
        stage.addEventListener("mouseenter", onMouseEnter);
        stage.addEventListener("mouseleave", onMouseLeave);

        // Pause cleanly when page is hidden; resume seamlessly without reset!
        const onVisChange = () => {
            tabHidden = Boolean(document.hidden);
            syncPlayback();
        };
        document.addEventListener("visibilitychange", onVisChange);

        // Calm UX: auto-pause while user focuses any form input (resumes without reset on blur)
        document.querySelectorAll(".grx-auth-card input, .grx-auth-card textarea").forEach((inp) => {
            inp.addEventListener("focus", () => {
                inputFocused = true;
                syncPlayback();
            });
            inp.addEventListener("blur", () => {
                window.setTimeout(() => {
                    const active = document.activeElement;
                    inputFocused = Boolean(
                        active && active.closest && active.closest(".grx-auth-card") && active.tagName === "INPUT"
                    );
                    syncPlayback();
                }, 120);
            });
        });

        registerCleanup(() => {
            if (progressTween) progressTween.kill();
            if (transitionTl) transitionTl.kill();
            stage.removeEventListener("mouseenter", onMouseEnter);
            stage.removeEventListener("mouseleave", onMouseLeave);
            document.removeEventListener("visibilitychange", onVisChange);
        });

        // Apply saved initial scene immediately (zero flicker across auth routes)
        activateScene(currentIdx, true);
        updateToggleUI();

        if (gsap && DrawSVGPlugin && !reduceMotion && isFirstVisit && document.getElementById("grxAuthRoutePath")) {
            gsap.fromTo(
                "#grxAuthRoutePath",
                { drawSVG: "0%" },
                { drawSVG: "100%", duration: 0.95, ease: "power2.out", delay: 0.16 }
            );
        }

        return { syncPlayback };
    }

    // =========================================================================
    // 5. FIRST-VISIT 6-STEP ENTRANCE VS. LIGHTWEIGHT SUBSEQUENT TRANSITIONS
    // =========================================================================
    function initEntranceMotion(gsap, SplitText, reduceMotion, isFirstVisit) {
        if (!gsap || reduceMotion) return;

        const runEntrance = () => {
            const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
            const visualStage = document.getElementById("grxSceneStage");
            const visualVisible = visualStage && window.getComputedStyle(visualStage).display !== "none";

            if (isFirstVisit && visualVisible) {
                // Full 6-step initial choreography (fast, non-blocking ~0.62s)
                tl.fromTo(
                    ".grx-auth-visual .grx-auth-brand-link",
                    { y: -8, opacity: 0.4 },
                    { y: 0, opacity: 1, duration: 0.34, clearProps: "transform,opacity" },
                    0
                );
                tl.fromTo(
                    visualStage,
                    { clipPath: "inset(4% 2% 4% 2% round 20px)", opacity: 0.72 },
                    { clipPath: "inset(0% 0% 0% 0% round 20px)", opacity: 1, duration: 0.56, clearProps: "clipPath,opacity" },
                    0.04
                );
                tl.fromTo(
                    ".grx-scene-slide.is-active .grx-scene-caption > *",
                    { y: 10, opacity: 0.4 },
                    { y: 0, opacity: 1, duration: 0.38, stagger: 0.05, clearProps: "transform,opacity" },
                    0.16
                );
                tl.fromTo(
                    ".grx-carousel-bar",
                    { y: 6, opacity: 0.4 },
                    { y: 0, opacity: 1, duration: 0.32, clearProps: "transform,opacity" },
                    0.26
                );
            }

            // Right card subtle entrance (always crisp & fast on route navigation)
            const card = document.querySelector(".grx-auth-card");
            if (card && !isFirstVisit) {
                tl.fromTo(
                    card,
                    { y: 8, opacity: 0.72 },
                    { y: 0, opacity: 1, duration: 0.28, clearProps: "transform,opacity" },
                    0
                );
            }

            const stateIcon = document.querySelector(".grx-state-icon");
            if (stateIcon) {
                tl.fromTo(
                    stateIcon,
                    { scale: 0.72, opacity: 0.4 },
                    { scale: 1, opacity: 1, duration: 0.36, ease: "back.out(2)", clearProps: "transform,opacity" },
                    0.04
                );
            }

            const heading = document.querySelector(".grx-form-title");
            if (heading && SplitText) {
                const split = SplitText.create(heading, { type: "words" });
                tl.fromTo(
                    split.words,
                    { y: 9, opacity: 0.5 },
                    { y: 0, opacity: 1, duration: 0.36, stagger: 0.022, clearProps: "transform,opacity" },
                    0.04
                );
            }

            const formItems = document.querySelectorAll(
                ".grx-form-eyebrow, .grx-form-desc, .grx-auth-card .mb-3, .grx-auth-card .oe_login_buttons, .grx-auth-card .grx-otp-grid, .grx-auth-card .grx-state-actions"
            );
            if (formItems.length) {
                tl.fromTo(
                    formItems,
                    { y: 8, opacity: 0.6 },
                    { y: 0, opacity: 1, duration: 0.32, stagger: 0.032, clearProps: "transform,opacity" },
                    0.06
                );
            }

            // Discreet error alert attention pulse when returned from server
            const serverErr = document.querySelector(".grx-auth-card .alert-danger, .grx-auth-card .grx-alert--danger");
            if (serverErr) {
                gsap.fromTo(
                    serverErr,
                    { x: -5 },
                    { x: 0, duration: 0.32, ease: "elastic.out(1.2, 0.45)", clearProps: "transform" }
                );
            }

            try {
                window.sessionStorage.setItem(INTRO_SEEN_KEY, "1");
            } catch (_err) {
                // Ignore restricted storage
            }
        };

        if (document.fonts && document.fonts.ready) {
            Promise.race([
                document.fonts.ready,
                new Promise((resolve) => window.setTimeout(resolve, 150)),
            ]).then(runEntrance);
        } else {
            runEntrance();
        }
    }

    // =========================================================================
    // 6. BOOTSTRAP & CLEANUP
    // =========================================================================
    function boot() {
        if (window.__grxAuthBooted) return;
        window.__grxAuthBooted = true;

        const gsap = window.gsap || null;
        const SplitText = window.SplitText || null;
        const DrawSVGPlugin = window.DrawSVGPlugin || null;
        const MotionPathPlugin = window.MotionPathPlugin || null;
        const Flip = window.Flip || null;

        if (gsap) {
            const plugins = [SplitText, DrawSVGPlugin, MotionPathPlugin, Flip].filter(Boolean);
            if (plugins.length) gsap.registerPlugin(...plugins);
        }

        const reduceMotion = Boolean(
            window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
        );

        let isFirstVisit = true;
        try {
            isFirstVisit = window.sessionStorage.getItem(INTRO_SEEN_KEY) !== "1";
        } catch (_err) {
            isFirstVisit = true;
        }

        initLoginForm(gsap, reduceMotion);
        initSignupForm(gsap, reduceMotion);
        initResetForm(gsap, reduceMotion);
        initOtpForm(gsap, reduceMotion);
        initVisualCarousel(gsap, SplitText, Flip, DrawSVGPlugin, MotionPathPlugin, reduceMotion, isFirstVisit);
        initEntranceMotion(gsap, SplitText, reduceMotion, isFirstVisit);

        window.addEventListener("pagehide", () => {
            cleanupHandlers.forEach((fn) => {
                try { fn(); } catch (_err) {}
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
