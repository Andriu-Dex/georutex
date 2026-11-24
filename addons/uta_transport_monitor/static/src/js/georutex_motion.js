/** @odoo-module **/

/**
 * Reusable GSAP entrance choreography for Odoo 16 OWL components.
 * Follows gsap-core & gsap-performance best practices:
 * - Uses gsap.matchMedia() for prefers-reduced-motion accessibility
 * - Animates only GPU-composited transform (y) and autoAlpha
 * - Clears inline transform/opacity props after completion so CSS hovers stay smooth
 * - Returns a revert() handle for OWL onWillUnmount cleanup (zero stray tweens)
 */
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
                defaults: { ease: "power3.out", overwrite: "auto" },
            });
            selectors.forEach((entry, idx) => {
                const targets = rootEl.querySelectorAll(entry.selector);
                if (!targets.length) return;
                tl.from(
                    targets,
                    {
                        y: entry.y !== undefined ? entry.y : 18,
                        autoAlpha: 0,
                        duration: entry.duration || 0.48,
                        stagger: entry.stagger !== undefined ? entry.stagger : 0.055,
                        clearProps: "transform,opacity,visibility",
                    },
                    idx === 0 ? 0 : "-=0.28"
                );
            });
        },
        rootEl
    );

    return () => {
        try {
            mm.revert();
        } catch (_err) {
            // Ignore cleanup errors if DOM already unmounted
        }
    };
}
