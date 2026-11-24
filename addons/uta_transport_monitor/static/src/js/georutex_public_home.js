/* GeoRutex Public Home — Warm Editorial GSAP 3.13.0 Narrative Choreography
 * Plugins: ScrollTrigger, SplitText, DrawSVGPlugin, MotionPathPlugin, Flip
 */
(function () {
    "use strict";

    const JOURNEY_LABELS = [
        "Salida desde Campus Huachi",
        "En ruta por Av. Los Chasquis",
        "Control en Redondel Cumandá",
        "Llegada a Campus Ingahurco",
    ];

    function initMagnetic(gsap, reduceMotion) {
        if (reduceMotion) return;
        document.querySelectorAll(".grx-magnetic").forEach((el) => {
            const xTo = gsap.quickTo(el, "x", { duration: 0.35, ease: "power3.out" });
            const yTo = gsap.quickTo(el, "y", { duration: 0.35, ease: "power3.out" });
            el.addEventListener("mousemove", (e) => {
                const r = el.getBoundingClientRect();
                xTo((e.clientX - r.left - r.width / 2) * 0.2);
                yTo((e.clientY - r.top - r.height / 2) * 0.2);
            });
            el.addEventListener("mouseleave", () => {
                xTo(0);
                yTo(0);
            });
        });
    }

    function initInteractiveShowcase(Flip) {
        const tabs = Array.from(document.querySelectorAll("#grxFeatureTabs .grx-ftab"));
        const panels = Array.from(document.querySelectorAll("#grxFeatureStage .grx-stage-panel"));
        if (!tabs.length || !panels.length) return;

        tabs.forEach((tab) => {
            tab.addEventListener("click", () => {
                if (tab.classList.contains("is-active")) return;
                const key = tab.dataset.feature;
                const state = Flip ? Flip.getState(tabs) : null;

                tabs.forEach((t) => {
                    const active = t === tab;
                    t.classList.toggle("is-active", active);
                    t.setAttribute("aria-selected", active ? "true" : "false");
                });

                panels.forEach((p) => {
                    p.classList.toggle("is-active", p.dataset.panel === key);
                });

                if (Flip && state) {
                    Flip.from(state, {
                        duration: 0.42,
                        ease: "power2.inOut",
                        simple: true,
                    });
                    if (window.ScrollTrigger) {
                        window.ScrollTrigger.refresh();
                    }
                }
            });
        });
    }

    function boot() {
        const gsap = window.gsap;
        const ScrollTrigger = window.ScrollTrigger;
        const SplitText = window.SplitText;
        const DrawSVGPlugin = window.DrawSVGPlugin;
        const MotionPathPlugin = window.MotionPathPlugin;
        const Flip = window.Flip;

        if (!gsap) return;
        const plugins = [ScrollTrigger, SplitText, DrawSVGPlugin, MotionPathPlugin, Flip].filter(Boolean);
        gsap.registerPlugin(...plugins);

        initInteractiveShowcase(Flip);

        const mm = gsap.matchMedia();
        mm.add(
            {
                isDesktop: "(min-width: 992px)",
                reduceMotion: "(prefers-reduced-motion: reduce)",
            },
            (context) => {
                const { isDesktop, reduceMotion } = context.conditions;
                initMagnetic(gsap, reduceMotion);

                if (reduceMotion) {
                    document.querySelectorAll(".gsap-counter").forEach((el) => {
                        el.textContent = `${el.dataset.target || 0}${el.dataset.suffix || ""}`;
                    });
                    return;
                }

                // 1. Hero Entrance: SplitText warm word glide + gentle media arrival
                const heroTitle = document.querySelector(".gsap-split-hero");
                const runSplit = () => {
                    if (!SplitText || !heroTitle) return;
                    const split = SplitText.create(heroTitle, { type: "words" });
                    gsap.fromTo(
                        split.words,
                        { y: 18, opacity: 0.12 },
                        {
                            y: 0,
                            opacity: 1,
                            duration: 0.65,
                            stagger: 0.035,
                            ease: "power3.out",
                            clearProps: "transform,opacity",
                        }
                    );
                };
                if (document.fonts && document.fonts.ready) {
                    Promise.race([
                        document.fonts.ready,
                        new Promise((r) => window.setTimeout(r, 250)),
                    ]).then(runSplit);
                } else {
                    runSplit();
                }

                gsap.fromTo(
                    ".gsap-hero-in",
                    { y: 14, opacity: 0.15 },
                    { y: 0, opacity: 1, duration: 0.55, stagger: 0.08, ease: "power3.out", clearProps: "transform,opacity" }
                );

                // Hero continuous live route trace & animated shuttle bus
                if (DrawSVGPlugin) {
                    gsap.fromTo(
                        "#heroLiveTrace",
                        { drawSVG: "0%" },
                        { drawSVG: "100%", duration: 1.4, ease: "power2.inOut" }
                    );
                }
                if (MotionPathPlugin) {
                    gsap.to("#heroLiveBus", {
                        duration: 9,
                        repeat: -1,
                        ease: "none",
                        motionPath: {
                            path: "#heroLiveTrace",
                            align: "#heroLiveTrace",
                            alignOrigin: [0.5, 0.5],
                            autoRotate: true,
                        },
                    });
                }

                // Subtle Awwwards scale-breathe on hero photo while scrolling
                if (ScrollTrigger && isDesktop) {
                    gsap.fromTo(
                        ".gsap-hero-media",
                        { scale: 0.985 },
                        {
                            scale: 1.015,
                            ease: "none",
                            scrollTrigger: {
                                trigger: ".grx-hero",
                                start: "top top",
                                end: "bottom top",
                                scrub: 0.6,
                            },
                        }
                    );
                }

                // 2. Codrops-inspired Clip-Path Curtain Reveals on Editorial Photography
                if (ScrollTrigger) {
                    document.querySelectorAll(".gsap-curtain-reveal").forEach((frame) => {
                        const img = frame.querySelector(".gsap-curtain-img");
                        gsap.fromTo(
                            frame,
                            { clipPath: "inset(8% 3% 8% 3% round 22px)" },
                            {
                                clipPath: "inset(0% 0% 0% 0% round 22px)",
                                duration: 0.95,
                                ease: "power3.out",
                                scrollTrigger: {
                                    trigger: frame,
                                    start: "top 84%",
                                    once: true,
                                },
                            }
                        );
                        if (img) {
                            gsap.fromTo(
                                img,
                                { scale: 1.1 },
                                {
                                    scale: 1,
                                    duration: 1.1,
                                    ease: "power3.out",
                                    scrollTrigger: {
                                        trigger: frame,
                                        start: "top 84%",
                                        once: true,
                                    },
                                }
                            );
                        }
                    });
                }

                // 3. SplitText headings on scroll
                if (SplitText && ScrollTrigger) {
                    document.querySelectorAll(".gsap-split-heading").forEach((h) => {
                        const sp = SplitText.create(h, { type: "words" });
                        gsap.fromTo(
                            sp.words,
                            { y: 16, opacity: 0.1 },
                            {
                                y: 0,
                                opacity: 1,
                                duration: 0.6,
                                stagger: 0.03,
                                ease: "power3.out",
                                clearProps: "transform,opacity",
                                scrollTrigger: {
                                    trigger: h,
                                    start: "top 86%",
                                    once: true,
                                },
                            }
                        );
                    });
                }

                // 4. Act 3: Scroll-Driven Route Storytelling (DrawSVG + MotionPath scrub)
                if (ScrollTrigger && DrawSVGPlugin && MotionPathPlugin) {
                    const pctEl = document.getElementById("journeyPct");
                    const labelEl = document.getElementById("journeyStageLabel");
                    const chapters = Array.from(document.querySelectorAll(".grx-chapter-item"));

                    const journeyTl = gsap.timeline({
                        scrollTrigger: {
                            trigger: "#recorrido",
                            start: "top 58%",
                            end: "bottom 75%",
                            scrub: 0.8,
                            onUpdate: (self) => {
                                const pct = Math.round(self.progress * 100);
                                if (pctEl) pctEl.textContent = `${pct}%`;
                                const idx = Math.min(3, Math.floor(self.progress * 4));
                                if (labelEl) labelEl.textContent = JOURNEY_LABELS[idx];
                                chapters.forEach((c, i) => c.classList.toggle("is-active", i === idx));
                            },
                        },
                    });

                    journeyTl
                        .fromTo("#journeyRoutePath", { drawSVG: "0%" }, { drawSVG: "100%", ease: "none" }, 0)
                        .to(
                            "#journeyBus",
                            {
                                ease: "none",
                                motionPath: {
                                    path: "#journeyRoutePath",
                                    align: "#journeyRoutePath",
                                    alignOrigin: [0.5, 0.5],
                                    autoRotate: true,
                                },
                            },
                            0
                        );
                }

                // 5. Animated Impact Counters
                if (ScrollTrigger) {
                    document.querySelectorAll(".gsap-counter").forEach((el) => {
                        const target = Number(el.dataset.target || 0);
                        const suffix = el.dataset.suffix || "";
                        const state = { val: 0 };
                        gsap.to(state, {
                            val: target,
                            duration: 1.3,
                            ease: "power3.out",
                            scrollTrigger: {
                                trigger: el,
                                start: "top 88%",
                                once: true,
                            },
                            onUpdate: () => {
                                el.textContent = `${Math.round(state.val)}${suffix}`;
                            },
                        });
                    });
                }
            }
        );

        const refresh = () => {
            if (window.ScrollTrigger) window.ScrollTrigger.refresh();
        };
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(refresh);
        }
        window.addEventListener("load", refresh);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
