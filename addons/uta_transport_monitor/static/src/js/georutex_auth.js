/* GeoRutex Unified Authentication Motion & UX (GSAP 3.13.0)
 * - Editorial 3-scene carousel with Clip-Path mask reveal, DrawSVG route,
 *   MotionPath beacon, manual controls, and auto-pause on form input focus.
 * - Deferred-until-interaction validation aligned with server rules.
 * - Smooth password checklist with GSAP Flip, 6-digit OTP UX, cooldown timer,
 *   double-submit prevention, and full prefers-reduced-motion compliance.
 */
(function () {
    "use strict";

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
    // 2. ACCESSIBLE FIELD FEEDBACK & PASSWORD TOGGLES
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

    function setFieldState(input, errorMessage) {
        if (!input) return true;
        const feedback = getOrCreateFeedback(input);
        if (errorMessage) {
            input.classList.add("is-invalid");
            input.classList.remove("is-valid");
            input.setAttribute("aria-invalid", "true");
            if (feedback) {
                input.setAttribute("aria-describedby", feedback.id);
                feedback.textContent = errorMessage;
                feedback.classList.add("is-visible");
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
        const btn = form.querySelector('button[type="submit"]:not([name])') || form.querySelector('button[type="submit"]');
        if (!btn) return;
        if (btn.dataset.grxSubmitting === "1") return;
        btn.dataset.grxSubmitting = "1";
        btn.classList.add("is-loading");
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        const label = btn.querySelector(".grx-btn-label");
        if (label && loadingText) {
            label.textContent = loadingText;
        }
    }

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
                        { scale: 1, duration: 0.24, ease: "back.out(2.2)", clearProps: "transform" }
                    );
                }
            }
        });

        const fill = meter.querySelector(".grx-meter-fill");
        const label = meter.querySelector(".grx-meter-label");
        const pct = pwd ? Math.round((score / 5) * 100) : 0;

        if (fill) {
            fill.style.width = pct + "%";
            fill.classList.remove("is-medium", "is-good", "is-strong");
            if (score === 3) fill.classList.add("is-medium");
            else if (score === 4) fill.classList.add("is-good");
            else if (score === 5) fill.classList.add("is-strong");
        }
        if (label) {
            const labels = ["Sin ingresar", "Débil", "Regular", "Aceptable", "Buena", "Segura"];
            label.textContent = pwd ? labels[score] : labels[0];
            label.classList.remove("is-weak", "is-medium", "is-strong");
            if (pwd && score <= 2) label.classList.add("is-weak");
            else if (score === 3 || score === 4) label.classList.add("is-medium");
            else if (score === 5) label.classList.add("is-strong");
        }
    }

    // =========================================================================
    // 3. FORM CONTROLLERS (DEFERRED ERRORS UNTIL INTERACTION / SUBMIT)
    // =========================================================================
    function initLoginForm() {
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
                    setFieldState(loginInput, validateEmail(loginInput.value, true));
                }
            });
            loginInput.addEventListener("input", function () {
                if (touched) setFieldState(loginInput, validateEmail(loginInput.value, true));
            });
        }
        if (pwdInput) {
            pwdInput.addEventListener("input", function () {
                if (pwdInput.classList.contains("is-invalid") && pwdInput.value) {
                    setFieldState(pwdInput, "");
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
                ok = setFieldState(loginInput, validateEmail(loginInput.value, true)) && ok;
            }
            if (pwdInput) {
                const pwdErr = pwdInput.value ? "" : "Ingresa tu contraseña.";
                ok = setFieldState(pwdInput, pwdErr) && ok;
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
                    setFieldState(loginInput, validateEmail(loginInput.value, false));
                }
            });
            loginInput.addEventListener("input", function () {
                if (touched) setFieldState(loginInput, validateEmail(loginInput.value, false));
            });
        }

        if (nameInput) {
            let touched = false;
            nameInput.addEventListener("blur", function () {
                if ((nameInput.value || "").trim()) {
                    touched = true;
                    setFieldState(nameInput, validateName(nameInput.value));
                }
            });
            nameInput.addEventListener("input", function () {
                if (touched) setFieldState(nameInput, validateName(nameInput.value));
            });
        }

        if (pwdInput) {
            let touched = false;
            const onPwdInput = function () {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
                if (touched) {
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
            pwdInput.addEventListener("input", onPwdInput);
            pwdInput.addEventListener("blur", function () {
                if (pwdInput.value) {
                    touched = true;
                    setFieldState(pwdInput, validateStrongPassword(pwdInput.value));
                }
            });
            if (pwdInput.value) updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
        }

        if (confirmInput) {
            let touched = false;
            const checkConfirm = function () {
                const matchErr =
                    confirmInput.value === (pwdInput ? pwdInput.value : "")
                        ? ""
                        : "Las contraseñas ingresadas no coinciden.";
                setFieldState(confirmInput, matchErr);
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
                ok = setFieldState(loginInput, validateEmail(loginInput.value, false)) && ok;
            }
            if (nameInput) {
                nameInput.value = (nameInput.value || "").trim();
                ok = setFieldState(nameInput, validateName(nameInput.value)) && ok;
            }
            if (pwdInput) {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
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
                    setFieldState(loginInput, validateEmail(loginInput.value, false));
                }
            });
            loginInput.addEventListener("input", function () {
                if (touched) setFieldState(loginInput, validateEmail(loginInput.value, false));
            });
        }

        if (pwdInput) {
            let touched = false;
            pwdInput.addEventListener("input", function () {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
                if (touched) setFieldState(pwdInput, validateStrongPassword(pwdInput.value));
                if (confirmInput && confirmInput.value) {
                    const matchErr =
                        confirmInput.value === pwdInput.value
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr);
                }
            });
            pwdInput.addEventListener("blur", function () {
                if (pwdInput.value) {
                    touched = true;
                    setFieldState(pwdInput, validateStrongPassword(pwdInput.value));
                }
            });
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
                    setFieldState(confirmInput, matchErr);
                }
            });
            confirmInput.addEventListener("input", function () {
                if (touched) {
                    const matchErr =
                        confirmInput.value === (pwdInput ? pwdInput.value : "")
                            ? ""
                            : "Las contraseñas ingresadas no coinciden.";
                    setFieldState(confirmInput, matchErr);
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
                ok = setFieldState(loginInput, validateEmail(loginInput.value, false)) && ok;
            }
            if (pwdInput) {
                updatePasswordMeter(form, pwdInput.value, gsap, reduceMotion);
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

    function initOtpForm() {
        const form = document.querySelector("form.grx-otp-form");
        if (!form) return;

        const digits = Array.from(form.querySelectorAll(".grx-otp-digit"));
        const hiddenInput = form.querySelector("#georutex_otp_hidden");
        const errorBox = form.querySelector("#grxOtpInlineError");

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
            }
        }
    }

    // =========================================================================
    // 4. LEFT EDITORIAL 3-SCENE CAROUSEL & GSAP CHOREOGRAPHY
    // =========================================================================
    function initVisualCarousel(gsap, Flip, DrawSVGPlugin, MotionPathPlugin, reduceMotion) {
        const stage = document.getElementById("grxSceneStage");
        const slides = Array.from(document.querySelectorAll(".grx-scene-slide"));
        const tabs = Array.from(document.querySelectorAll(".grx-carousel-tab"));
        const toggleBtn = document.getElementById("grxCarouselToggle");
        if (!stage || slides.length < 2) return;

        const NODE_PROGRESS = [0.14, 0.52, 0.88];
        const INTERVAL_MS = 6400;
        let currentIdx = 0;
        let manualPaused = Boolean(reduceMotion);
        let inputFocused = false;
        let hovered = false;
        let timerId = null;

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

        const moveBeaconTo = (idx, instant) => {
            if (!gsap || !MotionPathPlugin) return;
            const beacon = document.getElementById("grxAuthBeacon");
            const path = document.getElementById("grxAuthRoutePath");
            if (!beacon || !path) return;
            const endPos = NODE_PROGRESS[idx] || 0.14;
            gsap.to(beacon, {
                duration: instant || reduceMotion ? 0 : 0.75,
                ease: "power2.inOut",
                motionPath: {
                    path: "#grxAuthRoutePath",
                    align: "#grxAuthRoutePath",
                    alignOrigin: [0.5, 0.5],
                    end: endPos,
                },
            });
        };

        const activateScene = (nextIdx, instant) => {
            if (nextIdx === currentIdx && !instant) return;
            const prevSlide = slides[currentIdx];
            const nextSlide = slides[nextIdx];
            if (!nextSlide) return;

            const flipState = Flip && !reduceMotion && !instant ? Flip.getState(tabs) : null;
            tabs.forEach((tab, i) => {
                const active = i === nextIdx;
                tab.classList.toggle("is-active", active);
                tab.setAttribute("aria-selected", active ? "true" : "false");
            });
            if (Flip && flipState) {
                Flip.from(flipState, { duration: 0.34, ease: "power2.out", simple: true });
            }

            if (!gsap || reduceMotion || instant) {
                slides.forEach((s, i) => {
                    s.classList.remove("is-leaving");
                    s.classList.toggle("is-active", i === nextIdx);
                    s.style.opacity = "";
                    s.style.clipPath = "";
                });
                currentIdx = nextIdx;
                moveBeaconTo(nextIdx, true);
                return;
            }

            const img = nextSlide.querySelector("img");
            const captionItems = nextSlide.querySelectorAll(".grx-scene-eyebrow, .grx-scene-title, .grx-scene-desc");

            slides.forEach((s) => s.classList.remove("is-leaving", "is-active"));
            if (prevSlide && prevSlide !== nextSlide) prevSlide.classList.add("is-leaving");
            nextSlide.classList.add("is-active");

            const tl = gsap.timeline({
                defaults: { ease: "power3.out" },
                onComplete: () => {
                    slides.forEach((s) => s.classList.remove("is-leaving"));
                    gsap.set(nextSlide, { clearProps: "clipPath,opacity" });
                },
            });

            tl.fromTo(
                nextSlide,
                { opacity: 0.25, clipPath: "inset(0% 0% 0% 8% round 20px)" },
                { opacity: 1, clipPath: "inset(0% 0% 0% 0% round 20px)", duration: 0.72 },
                0
            );
            if (img) {
                tl.fromTo(img, { scale: 1.06 }, { scale: 1, duration: 0.9, clearProps: "transform" }, 0);
            }
            if (captionItems.length) {
                tl.fromTo(
                    captionItems,
                    { y: 12, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.48, stagger: 0.06, clearProps: "transform,opacity" },
                    0.16
                );
            }

            currentIdx = nextIdx;
            moveBeaconTo(nextIdx, false);
        };

        const scheduleNext = () => {
            if (timerId) window.clearTimeout(timerId);
            if (manualPaused || inputFocused || hovered || reduceMotion) return;
            // Skip autoplay when the left panel is hidden on mobile/tablet
            if (window.getComputedStyle(stage).display === "none") return;
            timerId = window.setTimeout(() => {
                activateScene((currentIdx + 1) % slides.length, false);
                scheduleNext();
            }, INTERVAL_MS);
        };

        tabs.forEach((tab, idx) => {
            tab.addEventListener("click", () => {
                activateScene(idx, false);
                scheduleNext();
            });
            tab.addEventListener("keydown", (ev) => {
                if (ev.key === "ArrowRight") {
                    ev.preventDefault();
                    const n = (idx + 1) % tabs.length;
                    tabs[n].focus();
                    activateScene(n, false);
                    scheduleNext();
                } else if (ev.key === "ArrowLeft") {
                    ev.preventDefault();
                    const p = (idx - 1 + tabs.length) % tabs.length;
                    tabs[p].focus();
                    activateScene(p, false);
                    scheduleNext();
                }
            });
        });

        if (toggleBtn) {
            toggleBtn.addEventListener("click", () => {
                manualPaused = !manualPaused;
                updateToggleUI();
                if (manualPaused && timerId) window.clearTimeout(timerId);
                else scheduleNext();
            });
        }

        stage.addEventListener("mouseenter", () => {
            hovered = true;
            if (timerId) window.clearTimeout(timerId);
        });
        stage.addEventListener("mouseleave", () => {
            hovered = false;
            scheduleNext();
        });

        // Calm UX: automatically pause carousel while user types credentials
        document.querySelectorAll(".grx-auth-card input, .grx-auth-card textarea").forEach((inp) => {
            inp.addEventListener("focus", () => {
                inputFocused = true;
                if (timerId) window.clearTimeout(timerId);
            });
            inp.addEventListener("blur", () => {
                window.setTimeout(() => {
                    const active = document.activeElement;
                    inputFocused = Boolean(active && active.closest && active.closest(".grx-auth-card") && active.tagName === "INPUT");
                    if (!inputFocused) scheduleNext();
                }, 120);
            });
        });

        // Initial DrawSVG route entrance & beacon placement
        if (gsap && DrawSVGPlugin && !reduceMotion && document.getElementById("grxAuthRoutePath")) {
            gsap.fromTo(
                "#grxAuthRoutePath",
                { drawSVG: "0%" },
                { drawSVG: "100%", duration: 1.05, ease: "power2.out", delay: 0.2 }
            );
        }
        moveBeaconTo(0, true);
        updateToggleUI();
        scheduleNext();
    }

    function initEntranceMotion(gsap, SplitText, reduceMotion) {
        if (!gsap || reduceMotion) return;

        const runEntrance = () => {
            const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

            const visualStage = document.getElementById("grxSceneStage");
            if (visualStage && window.getComputedStyle(visualStage).display !== "none") {
                tl.fromTo(
                    visualStage,
                    { clipPath: "inset(3% 2% 3% 2% round 20px)", opacity: 0.75 },
                    { clipPath: "inset(0% 0% 0% 0% round 20px)", opacity: 1, duration: 0.62, clearProps: "clipPath,opacity" },
                    0
                );
            }

            const heading = document.querySelector(".grx-form-title");
            if (heading && SplitText) {
                const split = SplitText.create(heading, { type: "words" });
                tl.fromTo(
                    split.words,
                    { y: 10, opacity: 0.45 },
                    { y: 0, opacity: 1, duration: 0.4, stagger: 0.026, clearProps: "transform,opacity" },
                    0.04
                );
            }

            const formItems = document.querySelectorAll(
                ".grx-form-eyebrow, .grx-form-desc, .grx-auth-card .mb-3, .grx-auth-card .oe_login_buttons, .grx-auth-card .grx-otp-grid, .grx-auth-card .grx-state-actions"
            );
            if (formItems.length) {
                tl.fromTo(
                    formItems,
                    { y: 10, opacity: 0.55 },
                    { y: 0, opacity: 1, duration: 0.36, stagger: 0.04, clearProps: "transform,opacity" },
                    0.08
                );
            }
        };

        if (document.fonts && document.fonts.ready) {
            Promise.race([
                document.fonts.ready,
                new Promise((resolve) => window.setTimeout(resolve, 160)),
            ]).then(runEntrance);
        } else {
            runEntrance();
        }
    }

    // =========================================================================
    // 5. BOOTSTRAP
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

        initLoginForm();
        initSignupForm(gsap, reduceMotion);
        initResetForm(gsap, reduceMotion);
        initOtpForm();
        initVisualCarousel(gsap, Flip, DrawSVGPlugin, MotionPathPlugin, reduceMotion);
        initEntranceMotion(gsap, SplitText, reduceMotion);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
