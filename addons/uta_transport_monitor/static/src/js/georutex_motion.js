/** @odoo-module **/

/**
 * Intentional, restrained GSAP motion utilities for GeoRutex internal workspaces.
 * - Strictly respects prefers-reduced-motion via gsap.matchMedia()
 * - Animates only GPU-composited transform (y) and opacity/autoAlpha
 * - Keeps internal workspace motion crisp (180–480ms), never blocking interaction
 * - Always returns a clean revert() function for OWL onWillUnmount teardown
 */

function prefersReducedMotion() {
    return Boolean(
        window.matchMedia &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
}

export function runGeorutexEntrance(rootEl, selectors = []) {
    const gsap = window.gsap;
    if (!gsap || !rootEl || !selectors.length) {
        return () => {};
    }

    const mm = gsap.matchMedia();
    mm.add(
        {
            reduceMotion: "(prefers-reduced-motion: reduce)",
            allowMotion: "(prefers-reduced-motion: no-preference)",
        },
        (context) => {
            if (context.conditions.reduceMotion) {
                return;
            }
            const tl = gsap.timeline({
                defaults: { ease: "power2.out", overwrite: "auto" },
            });
            selectors.forEach((entry, idx) => {
                const targets = rootEl.querySelectorAll(entry.selector);
                if (!targets.length) return;
                tl.from(
                    targets,
                    {
                        y: entry.y !== undefined ? entry.y : 12,
                        autoAlpha: 0,
                        duration: entry.duration || 0.36,
                        stagger: entry.stagger !== undefined ? entry.stagger : 0.035,
                        clearProps: "transform,opacity,visibility",
                    },
                    idx === 0 ? 0 : "-=0.22"
                );
            });
        },
        rootEl
    );

    return () => {
        try {
            mm.revert();
        } catch (_err) {
            // Safe ignore on unmounted DOM
        }
    };
}

/**
 * Smoothly animates pure integer/decimal real KPI counters on initial load.
 * Never fabricates values: ignores N/A, slashes, or non-numeric strings.
 */
export function animateGeorutexCounters(rootEl, selector = "[data-grx-counter]") {
    const gsap = window.gsap;
    if (!gsap || !rootEl || prefersReducedMotion()) {
        return () => {};
    }

    const tweens = [];
    rootEl.querySelectorAll(selector).forEach((el) => {
        const raw = (el.textContent || "").trim();
        const match = raw.match(/^(\d+(?:\.\d+)?)(.*)$/);
        if (!match) return;
        const target = parseFloat(match[1]);
        const suffix = match[2] || "";
        if (!Number.isFinite(target) || target === 0) return;

        const decimals = match[1].includes(".") ? match[1].split(".")[1].length : 0;
        const proxy = { val: 0 };
        const tw = gsap.to(proxy, {
            val: target,
            duration: 0.55,
            ease: "power2.out",
            onUpdate: () => {
                el.textContent = `${proxy.val.toFixed(decimals)}${suffix}`;
            },
            onComplete: () => {
                el.textContent = raw;
            },
        });
        tweens.push(tw);
    });

    return () => {
        tweens.forEach((tw) => {
            try {
                tw.kill();
            } catch (_err) {
                // Ignore
            }
        });
    };
}

/**
 * Lightweight GSAP Flip helper for smooth card/panel layout state transitions.
 */
export function captureGeorutexFlip(elements) {
    const Flip = window.Flip;
    if (!Flip || !elements || !elements.length || prefersReducedMotion()) {
        return null;
    }
    try {
        return Flip.getState(elements);
    } catch (_err) {
        return null;
    }
}

export function playGeorutexFlip(state, options = {}) {
    const Flip = window.Flip;
    if (!Flip || !state || prefersReducedMotion()) {
        return;
    }
    try {
        Flip.from(state, {
            duration: options.duration || 0.28,
            ease: options.ease || "power2.out",
            scale: false,
            simple: true,
        });
    } catch (_err) {
        // Ignore Flip errors if DOM changed completely
    }
}

/**
 * Crisp GSAP entrance for navbar dropdowns, notification popovers, and modals (180ms).
 */
export function animateGeorutexPopover(el) {
    const gsap = window.gsap;
    if (!gsap || !el || prefersReducedMotion()) return;
    gsap.fromTo(
        el,
        { y: -6, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.18, ease: "power2.out", clearProps: "transform,opacity" }
    );
}

/**
 * Discrete GSAP reveal for branded GeoRutex SVG empty states (.grx-nocontent).
 */
export function animateGeorutexEmptyStates(scope = document) {
    const gsap = window.gsap;
    if (!gsap || !scope || prefersReducedMotion()) return;
    if (window.DrawSVGPlugin && !window._grxDrawSvgRegistered) {
        try {
            gsap.registerPlugin(window.DrawSVGPlugin);
            window._grxDrawSvgRegistered = true;
        } catch (_err) {
            // Safe ignore
        }
    }
    const containers = scope.querySelectorAll(".grx-nocontent:not([data-grx-animated])");
    if (!containers.length) return;
    containers.forEach((box) => {
        box.setAttribute("data-grx-animated", "1");
        const icon = box.querySelector(".grx-nocontent-icon");
        const tl = gsap.timeline({ defaults: { ease: "power2.out" } });
        tl.fromTo(
            box,
            { y: 10, opacity: 0 },
            { y: 0, opacity: 1, duration: 0.3, clearProps: "transform,opacity" },
            0
        );
        if (icon) {
            tl.fromTo(
                icon,
                { scale: 0.9, opacity: 0 },
                { scale: 1, opacity: 1, duration: 0.32, clearProps: "transform,opacity" },
                0.06
            );
        }
    });
}
