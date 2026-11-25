/* GeoRutex Public Home — Organization-Agnostic GSAP 3.13.0 Motion & Interactive Previews
 * Reads presentation labels and sample coordinates exclusively from #grxPublicHomeConfig.
 */
(function () {
    "use strict";

    const FALLBACK_CONFIG = {
        stages: [
            {
                pill: "Inicio en punto de origen",
                meta: "Etapa 1 de 4 · Inicio del recorrido",
                state: "Unidad en marcha y vinculada a su jornada asignada",
                tone: "is-info",
                progress: 0.0,
            },
            {
                pill: "Paso verificado en Parada 01",
                meta: "Etapa 2 de 4 · Verificación de paradas",
                state: "Cumplimiento de parada registrado automáticamente",
                tone: "is-info",
                progress: 0.36,
            },
            {
                pill: "Novedad registrada en Parada 02",
                meta: "Etapa 3 de 4 · Gestión de novedades",
                state: "Reporte compartido desde el espacio del conductor",
                tone: "is-amber",
                progress: 0.68,
            },
            {
                pill: "Llegada al punto de destino",
                meta: "Etapa 4 de 4 · Llegada y evaluación",
                state: "Recorrido completado y listo para análisis de servicio",
                tone: "is-green",
                progress: 1.0,
            },
        ],
        map: {
            center: [-1.2555, -78.6262],
            corridor: [
                [-1.2692, -78.6256],
                [-1.2625, -78.6243],
                [-1.2562, -78.6254],
                [-1.2506, -78.6272],
                [-1.2421, -78.6284],
            ],
            origin_label: "Punto de origen",
            destination_label: "Punto de destino",
            units: {
                unit01: {
                    name: "Unidad 01",
                    status: "fresh",
                    statusLabel: "En ruta",
                    coords: [-1.2562, -78.6254],
                    detail: "Ruta A · Tramo hacia Parada 01",
                    color: "#15803d",
                },
                unit02: {
                    name: "Unidad 02",
                    status: "fresh",
                    statusLabel: "En ruta",
                    coords: [-1.2506, -78.6272],
                    detail: "Ruta B · Tramo hacia Parada 02",
                    color: "#0bbcd7",
                },
                unit03: {
                    name: "Unidad 03",
                    status: "stale",
                    statusLabel: "En espera",
                    coords: [-1.2421, -78.6284],
                    detail: "Ruta C · En punto de destino",
                    color: "#d97706",
                },
            },
        },
        analytics: {
            routes: ["Ruta A", "Ruta B", "Ruta C"],
            series_labels: ["Cumplimiento base", "Con novedades revisadas"],
            source_notes: {
                combined: "Vista general · Ejemplo ilustrativo",
                real: "Operación diaria · Ejemplo ilustrativo",
                simulated: "Escenarios de prueba · Separados de la operación",
                empty: "Sin recorridos evaluables en el período",
            },
        },
    };

    function readPublicConfig() {
        const el = document.getElementById("grxPublicHomeConfig");
        const raw = el ? (el.dataset.config || el.textContent || "") : "";
        if (!raw) return FALLBACK_CONFIG;
        try {
            const parsed = JSON.parse(raw);
            return {
                stages: Array.isArray(parsed.stages) && parsed.stages.length ? parsed.stages : FALLBACK_CONFIG.stages,
                map: parsed.map && parsed.map.units ? parsed.map : FALLBACK_CONFIG.map,
                analytics: parsed.analytics && parsed.analytics.routes ? parsed.analytics : FALLBACK_CONFIG.analytics,
            };
        } catch (_err) {
            return FALLBACK_CONFIG;
        }
    }

    // On-demand lazy loader for interactive map and chart libraries (keeps Hero fast)
    const loadedAssets = {};
    function loadScriptOnce(src) {
        if (loadedAssets[src]) return loadedAssets[src];
        loadedAssets[src] = new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = src;
            s.async = true;
            s.onload = () => resolve();
            s.onerror = () => reject(new Error(`Failed to load ${src}`));
            document.head.appendChild(s);
        });
        return loadedAssets[src];
    }
    function loadStyleOnce(href) {
        if (loadedAssets[href]) return;
        loadedAssets[href] = true;
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = href;
        document.head.appendChild(l);
    }

    // 1. Sticky Navigation + Scroll-Spy Active Indicator + Accessible Mobile Drawer
    function initNavigation(gsap, ScrollTrigger, reduceMotion) {
        const header = document.getElementById("grxHeader");
        const toggle = document.getElementById("grxMenuToggle");
        const drawer = document.getElementById("grxMobileDrawer");
        const navLinks = Array.from(document.querySelectorAll(".grx-nav-link"));
        const indicator = document.getElementById("grxNavIndicator");
        const cleanups = [];

        const onScroll = () => {
            if (header) header.classList.toggle("is-scrolled", window.scrollY > 24);
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        onScroll();
        cleanups.push(() => window.removeEventListener("scroll", onScroll));

        const moveIndicator = (link) => {
            if (!indicator || !link) return;
            const left = link.offsetLeft;
            const width = link.offsetWidth;
            if (gsap && !reduceMotion) {
                gsap.to(indicator, { x: left, width, opacity: 1, duration: 0.3, ease: "power3.out" });
            } else {
                indicator.style.transform = `translateX(${left}px)`;
                indicator.style.width = `${width}px`;
                indicator.style.opacity = "1";
            }
        };

        const clearActiveSection = () => {
            navLinks.forEach((lnk) => lnk.classList.remove("is-active"));
            if (!indicator) return;
            if (gsap && !reduceMotion) gsap.to(indicator, { opacity: 0, duration: 0.22, ease: "power2.out" });
            else indicator.style.opacity = "0";
        };

        const setActiveSection = (sectionId) => {
            navLinks.forEach((lnk) => {
                const match = lnk.dataset.section === sectionId;
                lnk.classList.toggle("is-active", match);
                if (match) moveIndicator(lnk);
            });
        };

        if (ScrollTrigger && navLinks.length) {
            const heroSec = document.querySelector(".grx-hero");
            if (heroSec) {
                ScrollTrigger.create({
                    trigger: heroSec,
                    start: "top top",
                    end: "bottom 55%",
                    onEnter: clearActiveSection,
                    onEnterBack: clearActiveSection,
                });
            }
            navLinks.forEach((lnk) => {
                const sec = document.getElementById(lnk.dataset.section);
                if (!sec) return;
                ScrollTrigger.create({
                    trigger: sec,
                    start: "top 42%",
                    end: "bottom 42%",
                    onToggle: (self) => {
                        if (self.isActive) setActiveSection(lnk.dataset.section);
                    },
                });
                const onClickNav = () => setActiveSection(lnk.dataset.section);
                lnk.addEventListener("click", onClickNav);
                cleanups.push(() => lnk.removeEventListener("click", onClickNav));
            });
        }

        // Discreet brand isotype micro-interaction on hover/focus
        if (gsap && !reduceMotion) {
            document.querySelectorAll(".grx-brand").forEach((brandEl) => {
                const mark = brandEl.querySelector(".gsap-brand-mark");
                if (!mark) return;
                const onEnter = () => gsap.to(mark, { scale: 1.07, rotation: -5, duration: 0.26, ease: "power3.out" });
                const onLeave = () => gsap.to(mark, { scale: 1, rotation: 0, duration: 0.32, ease: "power3.out" });
                brandEl.addEventListener("mouseenter", onEnter);
                brandEl.addEventListener("mouseleave", onLeave);
                brandEl.addEventListener("focus", onEnter);
                brandEl.addEventListener("blur", onLeave);
                cleanups.push(() => {
                    brandEl.removeEventListener("mouseenter", onEnter);
                    brandEl.removeEventListener("mouseleave", onLeave);
                    brandEl.removeEventListener("focus", onEnter);
                    brandEl.removeEventListener("blur", onLeave);
                });
            });
        }

        // Mobile Drawer Accessibility & GSAP Animation
        if (toggle && drawer) {
            const closeDrawer = () => {
                toggle.setAttribute("aria-expanded", "false");
                toggle.setAttribute("aria-label", "Abrir menú de navegación");
                drawer.setAttribute("hidden", "hidden");
            };
            const openDrawer = () => {
                toggle.setAttribute("aria-expanded", "true");
                toggle.setAttribute("aria-label", "Cerrar menú de navegación");
                drawer.removeAttribute("hidden");
                if (gsap && !reduceMotion) {
                    gsap.fromTo(
                        drawer,
                        { opacity: 0, y: -8 },
                        { opacity: 1, y: 0, duration: 0.28, ease: "power3.out", clearProps: "transform,opacity" }
                    );
                }
            };
            const onToggle = () => {
                if (toggle.getAttribute("aria-expanded") === "true") closeDrawer();
                else openDrawer();
            };
            const onEsc = (e) => {
                if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
                    closeDrawer();
                    toggle.focus();
                }
            };
            toggle.addEventListener("click", onToggle);
            document.addEventListener("keydown", onEsc);
            drawer.querySelectorAll("a").forEach((a) => a.addEventListener("click", closeDrawer));
            cleanups.push(() => {
                toggle.removeEventListener("click", onToggle);
                document.removeEventListener("keydown", onEsc);
            });
        }

        return () => cleanups.forEach((fn) => fn());
    }

    // 2. Subtle Magnetic Buttons
    function initMagnetic(gsap, reduceMotion) {
        if (reduceMotion) return () => {};
        const cleanups = [];
        document.querySelectorAll(".grx-magnetic").forEach((el) => {
            const xTo = gsap.quickTo(el, "x", { duration: 0.3, ease: "power3.out" });
            const yTo = gsap.quickTo(el, "y", { duration: 0.3, ease: "power3.out" });
            const onMove = (e) => {
                const r = el.getBoundingClientRect();
                xTo((e.clientX - r.left - r.width / 2) * 0.16);
                yTo((e.clientY - r.top - r.height / 2) * 0.16);
            };
            const onLeave = () => {
                xTo(0);
                yTo(0);
            };
            el.addEventListener("mousemove", onMove);
            el.addEventListener("mouseleave", onLeave);
            cleanups.push(() => {
                el.removeEventListener("mousemove", onMove);
                el.removeEventListener("mouseleave", onLeave);
                gsap.set(el, { clearProps: "x,y" });
            });
        });
        return () => cleanups.forEach((fn) => fn());
    }

    // 3. Interactive Product Views (Config-Driven Map, Route Editor, Flip Mobile Morph, Interactive Chart)
    function initProductShowcase(gsap, Flip, DrawSVGPlugin, reduceMotion, cfg) {
        const tabs = Array.from(document.querySelectorAll("#grxFeatureTabs .grx-ftab"));
        const panels = Array.from(document.querySelectorAll("#grxFeatureStage .grx-ui-panel"));
        const browser = document.getElementById("grxProductBrowser");
        const titleEl = document.getElementById("grxBrowserTitle");
        const modeLabel = document.getElementById("grxBrowserModeLabel");
        const cleanups = [];
        if (!tabs.length || !panels.length) return () => {};

        let activeKey = tabs[0].dataset.feature;
        let leafletMap = null;
        let echartInstance = null;

        // 3A. Operations Center inline filter
        document.querySelectorAll("[data-ops-filter]").forEach((btn) => {
            const onClick = () => {
                const filter = btn.dataset.opsFilter;
                document.querySelectorAll("[data-ops-filter]").forEach((b) => b.classList.toggle("is-on", b === btn));
                document.querySelectorAll(".grx-ops-marker").forEach((m) => {
                    const show = filter === "all" || m.dataset.status === filter;
                    m.classList.toggle("is-dim", !show);
                });
                document.querySelectorAll("[data-ops-row]").forEach((row) => {
                    const show = filter === "all" || row.dataset.opsRow === filter;
                    row.classList.toggle("is-hidden", !show);
                });
            };
            btn.addEventListener("click", onClick);
            cleanups.push(() => btn.removeEventListener("click", onClick));
        });

        // 3B. Lazy Interactive Map (driven completely by cfg.map)
        const ensureLeafletMap = () => {
            const mapEl = document.getElementById("grxPublicLeafletMap");
            if (!mapEl) return;
            if (leafletMap) {
                window.setTimeout(() => leafletMap.invalidateSize(), 260);
                return;
            }
            loadStyleOnce("/uta_transport_monitor/static/lib/leaflet/leaflet.css");
            loadScriptOnce("/uta_transport_monitor/static/lib/leaflet/leaflet.js")
                .then(() => {
                    const L = window.L;
                    if (!L || leafletMap) return;
                    const corridor = cfg.map.corridor || FALLBACK_CONFIG.map.corridor;
                    const center = cfg.map.center || FALLBACK_CONFIG.map.center;

                    leafletMap = L.map(mapEl, {
                        center,
                        zoom: 14,
                        zoomControl: true,
                        attributionControl: true,
                        scrollWheelZoom: false,
                    });
                    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                        maxZoom: 18,
                        attribution: "&copy; OpenStreetMap",
                    }).addTo(leafletMap);

                    L.polyline(corridor, {
                        color: "#1a56db",
                        weight: 4,
                        opacity: 0.85,
                    }).addTo(leafletMap);

                    if (corridor.length >= 2) {
                        L.circleMarker(corridor[0], { radius: 6, color: "#15803d", fillColor: "#ffffff", fillOpacity: 1, weight: 3 })
                            .bindTooltip(cfg.map.origin_label || "Punto de origen")
                            .addTo(leafletMap);
                        L.circleMarker(corridor[corridor.length - 1], { radius: 6, color: "#fc0154", fillColor: "#ffffff", fillOpacity: 1, weight: 3 })
                            .bindTooltip(cfg.map.destination_label || "Punto de destino")
                            .addTo(leafletMap);
                    }

                    Object.values(cfg.map.units || {}).forEach((u) => {
                        L.circleMarker(u.coords, {
                            radius: 9,
                            color: "#ffffff",
                            weight: 3,
                            fillColor: u.color || "#1a56db",
                            fillOpacity: 1,
                        })
                            .bindTooltip(`${u.name} (${u.statusLabel})`)
                            .addTo(leafletMap);
                    });
                    window.setTimeout(() => leafletMap && leafletMap.invalidateSize(), 220);
                })
                .catch(() => {});
        };

        const focusCard = document.getElementById("grxMapFocusCard");
        document.querySelectorAll("#grxLiveUnitList .grx-mock-vitem").forEach((btn) => {
            const onClick = () => {
                const unit = (cfg.map.units || {})[btn.dataset.unit];
                if (!unit) return;
                document.querySelectorAll("#grxLiveUnitList .grx-mock-vitem").forEach((b) => b.classList.toggle("is-selected", b === btn));
                if (focusCard) {
                    focusCard.innerHTML = `<strong>${unit.name} · ${unit.statusLabel}</strong><span>${unit.detail}</span>`;
                }
                if (leafletMap) {
                    leafletMap.flyTo(unit.coords, 15, { duration: reduceMotion ? 0 : 0.7 });
                }
            };
            btn.addEventListener("click", onClick);
            cleanups.push(() => btn.removeEventListener("click", onClick));
        });

        document.querySelectorAll("[data-map-filter]").forEach((btn) => {
            const onClick = () => {
                const f = btn.dataset.mapFilter;
                document.querySelectorAll("[data-map-filter]").forEach((b) => b.classList.toggle("is-on", b === btn));
                document.querySelectorAll("#grxLiveUnitList .grx-mock-vitem").forEach((item) => {
                    item.classList.toggle("is-hidden", f !== "all" && item.dataset.status !== f);
                });
            };
            btn.addEventListener("click", onClick);
            cleanups.push(() => btn.removeEventListener("click", onClick));
        });

        // 3C. Route Editor interactive corridor/control-area toggles & stop selection
        document.querySelectorAll(".grx-ed-toggle").forEach((btn) => {
            const onClick = () => {
                const isOn = !btn.classList.contains("is-on");
                btn.classList.toggle("is-on", isOn);
                btn.setAttribute("aria-pressed", isOn ? "true" : "false");
                const target = document.getElementById(btn.dataset.edLayer === "corridor" ? "grxEdCorridor" : "grxEdGeofences");
                if (target) {
                    if (gsap && !reduceMotion) gsap.to(target, { opacity: isOn ? 1 : 0, duration: 0.25 });
                    else target.style.opacity = isOn ? "1" : "0";
                }
            };
            btn.addEventListener("click", onClick);
            cleanups.push(() => btn.removeEventListener("click", onClick));
        });

        document.querySelectorAll(".grx-mock-stop-item").forEach((btn) => {
            const onClick = () => {
                const stopIdx = btn.dataset.edStop;
                document.querySelectorAll(".grx-mock-stop-item").forEach((b) => b.classList.toggle("is-selected", b === btn));
                document.querySelectorAll(".grx-ed-geo").forEach((c) => {
                    const match = c.dataset.edStop === stopIdx;
                    c.classList.toggle("is-focus", match);
                    if (match && gsap && !reduceMotion) {
                        gsap.fromTo(c, { scale: 0.88, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.35, ease: "back.out(2)" });
                    }
                });
            };
            btn.addEventListener("click", onClick);
            cleanups.push(() => btn.removeEventListener("click", onClick));
        });

        // 3D. Lazy Interactive Analytics Chart (organization-neutral sample)
        const renderEChart = (sourceMode) => {
            const chartEl = document.getElementById("grxPublicEChart");
            const emptyEl = document.getElementById("grxPublicEChartEmpty");
            const noteEl = document.getElementById("grxChartSourceNote");
            if (!chartEl) return;

            const notes = cfg.analytics.source_notes || FALLBACK_CONFIG.analytics.source_notes;
            if (noteEl) noteEl.textContent = notes[sourceMode] || notes.combined;

            if (sourceMode === "empty") {
                if (emptyEl) emptyEl.removeAttribute("hidden");
                if (echartInstance) echartInstance.clear();
                return;
            }
            if (emptyEl) emptyEl.setAttribute("hidden", "hidden");

            loadScriptOnce("/uta_transport_monitor/static/lib/echarts/echarts.min.js")
                .then(() => {
                    if (!window.echarts) return;
                    if (!echartInstance) {
                        echartInstance = window.echarts.init(chartEl);
                    }
                    const seriesData = {
                        combined: { a: [4, 4, 3], b: [4, 4, 4] },
                        real: { a: [3, 4, 3], b: [4, 4, 3] },
                        simulated: { a: [4, 3, 4], b: [4, 4, 4] },
                    }[sourceMode] || { a: [4, 4, 3], b: [4, 4, 4] };
                    const labels = cfg.analytics.series_labels || FALLBACK_CONFIG.analytics.series_labels;
                    const routes = cfg.analytics.routes || FALLBACK_CONFIG.analytics.routes;

                    echartInstance.setOption({
                        animationDuration: reduceMotion ? 0 : 520,
                        tooltip: {
                            trigger: "axis",
                            formatter: (params) => {
                                const head = params[0] ? params[0].axisValue : "";
                                const lines = params.map((p) => `${p.marker} ${p.seriesName}: ${p.value} controles`);
                                return `<strong>${head}</strong><br/>${lines.join("<br/>")}<br/><small style="color:#64748b">Ejemplo ilustrativo</small>`;
                            },
                        },
                        legend: { bottom: 0, textStyle: { color: "#475569", fontSize: 11 } },
                        grid: { left: 36, right: 16, top: 18, bottom: 34 },
                        xAxis: {
                            type: "category",
                            data: routes,
                            axisLine: { lineStyle: { color: "#cbd5e1" } },
                            axisLabel: { color: "#475569", fontSize: 11 },
                        },
                        yAxis: {
                            type: "value",
                            min: 0,
                            max: 4,
                            interval: 1,
                            axisLabel: { color: "#64748b", fontSize: 11 },
                            splitLine: { lineStyle: { color: "#eef2f7" } },
                        },
                        series: [
                            {
                                name: labels[0],
                                type: "bar",
                                barMaxWidth: 26,
                                itemStyle: { color: "#1a56db", borderRadius: [6, 6, 0, 0] },
                                data: seriesData.a,
                            },
                            {
                                name: labels[1],
                                type: "bar",
                                barMaxWidth: 26,
                                itemStyle: { color: "#0bbcd7", borderRadius: [6, 6, 0, 0] },
                                data: seriesData.b,
                            },
                        ],
                    });
                    echartInstance.resize();
                })
                .catch(() => {});
        };

        document.querySelectorAll("[data-chart-source]").forEach((btn) => {
            const onClick = () => {
                document.querySelectorAll("[data-chart-source]").forEach((b) => b.classList.toggle("is-on", b === btn));
                renderEChart(btn.dataset.chartSource);
            };
            btn.addEventListener("click", onClick);
            cleanups.push(() => btn.removeEventListener("click", onClick));
        });

        const onResizeChart = () => {
            if (echartInstance) echartInstance.resize();
            if (leafletMap) leafletMap.invalidateSize();
        };
        window.addEventListener("resize", onResizeChart);
        cleanups.push(() => window.removeEventListener("resize", onResizeChart));

        // 3E. Differentiated GSAP Scene Transitions + Desktop <-> Mobile Flip Morph
        const animateViewEntrance = (key, panel) => {
            if (key === "map") ensureLeafletMap();
            if (key === "analytics") renderEChart("combined");
            if (!gsap || reduceMotion) return;

            const blocks = panel.querySelectorAll(".grx-ui-anim");
            const strokes = panel.querySelectorAll(".grx-ui-draw");
            const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

            if (key === "routes") {
                tl.fromTo(panel, { opacity: 0.2, clipPath: "inset(0% 0% 8% 0%)" }, { opacity: 1, clipPath: "inset(0% 0% 0% 0%)", duration: 0.42, clearProps: "clipPath,opacity" });
            } else if (key === "driver") {
                tl.fromTo(panel, { opacity: 0.2, scale: 0.97 }, { opacity: 1, scale: 1, duration: 0.4, clearProps: "transform,opacity" });
            } else {
                tl.fromTo(panel, { opacity: 0.2, y: 10 }, { opacity: 1, y: 0, duration: 0.36, clearProps: "transform,opacity" });
            }

            if (blocks.length) {
                tl.fromTo(blocks, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.34, stagger: 0.05, clearProps: "transform,opacity" }, 0.05);
            }
            if (DrawSVGPlugin && strokes.length) {
                tl.fromTo(strokes, { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.68, ease: "power2.out" }, 0.14);
            }
        };

        const activateTab = (tab, moveFocus) => {
            const key = tab.dataset.feature;
            if (!key || key === activeKey) return;
            activeKey = key;

            const flipTargets = browser ? [...tabs, browser] : tabs;
            const flipState = Flip && !reduceMotion ? Flip.getState(flipTargets) : null;

            tabs.forEach((t) => {
                const isActive = t === tab;
                t.classList.toggle("is-active", isActive);
                t.setAttribute("aria-selected", isActive ? "true" : "false");
                t.setAttribute("tabindex", isActive ? "0" : "-1");
            });

            if (browser) {
                const isMobile = tab.dataset.mode === "mobile";
                browser.classList.toggle("is-mobile-mode", isMobile);
                if (modeLabel) modeLabel.textContent = isMobile ? "Vista móvil" : "Vista escritorio";
            }

            let targetPanel = null;
            panels.forEach((p) => {
                const match = p.dataset.panel === key;
                p.classList.toggle("is-active", match);
                if (match) targetPanel = p;
            });

            if (titleEl && tab.dataset.title) {
                if (gsap && !reduceMotion) {
                    gsap.fromTo(
                        titleEl,
                        { opacity: 0.25, y: -3 },
                        {
                            opacity: 1,
                            y: 0,
                            duration: 0.24,
                            onStart: () => { titleEl.textContent = tab.dataset.title; },
                            clearProps: "transform,opacity",
                        }
                    );
                } else {
                    titleEl.textContent = tab.dataset.title;
                }
            }

            if (Flip && flipState && !reduceMotion) {
                Flip.from(flipState, {
                    duration: 0.44,
                    ease: "power2.inOut",
                    simple: true,
                    onComplete: () => {
                        if (window.ScrollTrigger) window.ScrollTrigger.refresh();
                        if (key === "map" && leafletMap) leafletMap.invalidateSize();
                        if (key === "analytics" && echartInstance) echartInstance.resize();
                    },
                });
            }

            if (targetPanel) animateViewEntrance(key, targetPanel);
            if (moveFocus) tab.focus();
        };

        tabs.forEach((tab, idx) => {
            tab.setAttribute("tabindex", idx === 0 ? "0" : "-1");
            const onClick = () => activateTab(tab, false);
            const onKeydown = (e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); activateTab(tabs[(idx + 1) % tabs.length], true); }
                else if (e.key === "ArrowUp") { e.preventDefault(); activateTab(tabs[(idx - 1 + tabs.length) % tabs.length], true); }
                else if (e.key === "Home") { e.preventDefault(); activateTab(tabs[0], true); }
                else if (e.key === "End") { e.preventDefault(); activateTab(tabs[tabs.length - 1], true); }
            };
            tab.addEventListener("click", onClick);
            tab.addEventListener("keydown", onKeydown);
            cleanups.push(() => {
                tab.removeEventListener("click", onClick);
                tab.removeEventListener("keydown", onKeydown);
            });
        });

        return () => cleanups.forEach((fn) => fn());
    }

    // 4. Interactive Route Journey UI Sync (0% -> 100%, driven by centralized stages)
    function applyJourneyStageUI(stages, idx, rawProgress) {
        const stage = stages[idx] || stages[0];
        const pctEl = document.getElementById("journeyPct");
        const labelEl = document.getElementById("journeyStageLabel");
        const pillEl = document.getElementById("journeyStatusPill");
        const metaEl = document.getElementById("journeyCheckpointMeta");
        const stateEl = document.getElementById("journeyCheckpointState");
        const fillEl = document.getElementById("journeyProgressFill");

        let normalized = Math.max(0, Math.min(1, rawProgress));
        if (normalized < 0.02) normalized = 0;
        if (normalized > 0.96 || (idx === stages.length - 1 && normalized > 0.92)) normalized = 1;

        if (pctEl) pctEl.textContent = `${Math.round(normalized * 100)}%`;
        if (labelEl) labelEl.textContent = stage.pill;
        if (metaEl) metaEl.textContent = stage.meta;
        if (stateEl) stateEl.textContent = stage.state;
        if (fillEl) fillEl.style.transform = `scaleX(${Math.max(0.04, normalized)})`;

        if (pillEl) {
            pillEl.classList.remove("is-info", "is-amber", "is-green");
            pillEl.classList.add(stage.tone || "is-info");
        }

        document.querySelectorAll(".grx-chapter-item").forEach((c, i) => {
            c.classList.toggle("is-active", i === idx);
        });
        document.querySelectorAll(".grx-step-btn").forEach((btn, i) => {
            btn.classList.toggle("is-active", i === idx);
            btn.classList.toggle("is-done", i < idx);
            btn.setAttribute("aria-pressed", i === idx ? "true" : "false");
        });
        document.querySelectorAll(".grx-stop-pin").forEach((pin, i) => {
            pin.classList.toggle("is-active", i === idx);
            pin.classList.toggle("is-done", i < idx);
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

        const cfg = readPublicConfig();
        const stages = cfg.stages;

        const mm = gsap.matchMedia();
        mm.add(
            {
                isDesktop: "(min-width: 992px)",
                isMobile: "(max-width: 991.98px)",
                reduceMotion: "(prefers-reduced-motion: reduce)",
            },
            (context) => {
                const { isDesktop, reduceMotion } = context.conditions;

                const cleanupNav = initNavigation(gsap, ScrollTrigger, reduceMotion);
                const cleanupMagnetic = initMagnetic(gsap, reduceMotion);
                const cleanupShowcase = initProductShowcase(gsap, Flip, DrawSVGPlugin, reduceMotion, cfg);
                const journeyCleanups = [];

                let journeyTrigger = null;
                let journeyManualTween = null;

                const goToJourneyStage = (idx) => {
                    const stage = stages[idx];
                    if (!stage) return;
                    if (journeyTrigger && isDesktop && !reduceMotion) {
                        const targetY = journeyTrigger.start + (journeyTrigger.end - journeyTrigger.start) * stage.progress;
                        window.scrollTo({ top: targetY, behavior: "smooth" });
                    } else {
                        applyJourneyStageUI(stages, idx, stage.progress);
                        if (!reduceMotion && DrawSVGPlugin && MotionPathPlugin) {
                            if (journeyManualTween) journeyManualTween.kill();
                            journeyManualTween = gsap.timeline({ defaults: { duration: 0.72, ease: "power2.inOut" } });
                            journeyManualTween
                                .to("#journeyRoutePath", { drawSVG: `${Math.round(stage.progress * 100)}%` }, 0)
                                .to(
                                    "#journeyBus",
                                    {
                                        motionPath: {
                                            path: "#journeyRoutePath",
                                            align: "#journeyRoutePath",
                                            alignOrigin: [0.5, 0.5],
                                            autoRotate: true,
                                            end: stage.progress,
                                        },
                                    },
                                    0
                                );
                        }
                    }
                };

                document.querySelectorAll(".grx-step-btn, .grx-stop-pin, .grx-chapter-item").forEach((el) => {
                    const idx = Number(el.dataset.step || 0);
                    const onClick = () => goToJourneyStage(idx);
                    const onKeydown = (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            goToJourneyStage(idx);
                        }
                    };
                    el.addEventListener("click", onClick);
                    el.addEventListener("keydown", onKeydown);
                    journeyCleanups.push(() => {
                        el.removeEventListener("click", onClick);
                        el.removeEventListener("keydown", onKeydown);
                    });
                });

                const cleanupAll = () => {
                    cleanupNav();
                    cleanupMagnetic();
                    cleanupShowcase();
                    journeyCleanups.forEach((fn) => fn());
                    if (journeyManualTween) journeyManualTween.kill();
                };

                if (reduceMotion) {
                    applyJourneyStageUI(stages, 0, 0);
                    return cleanupAll;
                }

                // 1. HERO COORDINATED 6-STEP GSAP TIMELINE
                const runHeroTimeline = () => {
                    const heroTl = gsap.timeline({ defaults: { ease: "power3.out" } });

                    heroTl.fromTo(
                        ".gsap-nav-item",
                        { y: -6, opacity: 0.7 },
                        { y: 0, opacity: 1, duration: 0.34, stagger: 0.03, clearProps: "transform,opacity" },
                        0
                    );
                    heroTl.fromTo(
                        ".gsap-hero-eyebrow",
                        { y: 8, opacity: 0.6 },
                        { y: 0, opacity: 1, duration: 0.38, clearProps: "transform,opacity" },
                        0.04
                    );

                    const heroTitle = document.querySelector(".gsap-split-hero");
                    if (SplitText && heroTitle) {
                        const split = SplitText.create(heroTitle, { type: "words" });
                        heroTl.fromTo(
                            split.words,
                            { y: 12, opacity: 0.5 },
                            { y: 0, opacity: 1, duration: 0.46, stagger: 0.024, clearProps: "transform,opacity" },
                            0.08
                        );
                    }

                    heroTl
                        .fromTo(".gsap-hero-desc", { y: 10, opacity: 0.6 }, { y: 0, opacity: 1, duration: 0.42, clearProps: "transform,opacity" }, 0.16)
                        .fromTo(".gsap-hero-ctas", { y: 10, opacity: 0.65 }, { y: 0, opacity: 1, duration: 0.4, clearProps: "transform,opacity" }, 0.22)
                        .fromTo(
                            ".gsap-hero-stage",
                            { clipPath: "inset(3% 1.5% 3% 1.5% round 22px)" },
                            { clipPath: "inset(0% 0% 0% 0% round 22px)", duration: 0.7, clearProps: "clipPath" },
                            0.18
                        )
                        .fromTo(".gsap-hero-parallax", { scale: 1.05 }, { scale: 1, duration: 0.85 }, 0.18)
                        .fromTo(".gsap-hero-overlay", { y: 8, opacity: 0.85 }, { y: 0, opacity: 1, duration: 0.42, stagger: 0.06, clearProps: "transform,opacity" }, 0.28);

                    if (DrawSVGPlugin) {
                        heroTl
                            .fromTo("#heroHorizonArc", { drawSVG: "0%" }, { drawSVG: "100%", duration: 1.15, ease: "power2.out" }, 0.25)
                            .fromTo("#heroLiveTrace", { drawSVG: "0%" }, { drawSVG: "100%", duration: 1.0, ease: "power2.inOut" }, 0.25);
                    }
                };

                if (document.fonts && document.fonts.ready) {
                    Promise.race([
                        document.fonts.ready,
                        new Promise((r) => window.setTimeout(r, 180)),
                    ]).then(runHeroTimeline);
                } else {
                    runHeroTimeline();
                }

                // Continuous preserved hero vehicle loop (pauses off-screen)
                if (MotionPathPlugin) {
                    const heroBusTween = gsap.to("#heroLiveBus", {
                        duration: 9.5,
                        repeat: -1,
                        ease: "none",
                        motionPath: {
                            path: "#heroLiveTrace",
                            align: "#heroLiveTrace",
                            alignOrigin: [0.5, 0.5],
                            autoRotate: true,
                        },
                    });
                    if (ScrollTrigger) {
                        ScrollTrigger.create({
                            trigger: ".grx-hero-stage",
                            start: "top bottom",
                            end: "bottom top",
                            onEnter: () => heroBusTween.play(),
                            onEnterBack: () => heroBusTween.play(),
                            onLeave: () => heroBusTween.pause(),
                            onLeaveBack: () => heroBusTween.pause(),
                        });
                    }
                }

                // Hero parallax & vector route bridge into Section 2
                if (ScrollTrigger && isDesktop) {
                    gsap.fromTo(
                        ".gsap-hero-parallax",
                        { yPercent: -3 },
                        {
                            yPercent: 5,
                            ease: "none",
                            scrollTrigger: {
                                trigger: ".grx-hero-stage",
                                start: "top bottom",
                                end: "bottom top",
                                scrub: 0.65,
                            },
                        }
                    );
                }
                if (ScrollTrigger && DrawSVGPlugin && document.getElementById("heroToVisionPath")) {
                    gsap.fromTo(
                        "#heroToVisionPath",
                        { drawSVG: "0%" },
                        {
                            drawSVG: "100%",
                            ease: "none",
                            scrollTrigger: {
                                trigger: ".grx-route-bridge",
                                start: "top 88%",
                                end: "bottom 55%",
                                scrub: 0.5,
                            },
                        }
                    );
                }

                // 2. REVERSIBLE VIEWPORT ANIMATIONS
                if (ScrollTrigger) {
                    document.querySelectorAll(".gsap-curtain-reveal").forEach((frame) => {
                        const img = frame.querySelector(".gsap-curtain-img");
                        const tl = gsap.timeline({
                            scrollTrigger: {
                                trigger: frame,
                                start: "top 95%",
                                end: "bottom 10%",
                                toggleActions: "play none none reverse",
                            },
                        });
                        tl.fromTo(
                            frame,
                            { clipPath: "inset(6% 2.5% 6% 2.5% round 22px)" },
                            { clipPath: "inset(0% 0% 0% 0% round 22px)", duration: 0.72, ease: "power3.out" },
                            0
                        );
                        if (img) {
                            tl.fromTo(img, { scale: 1.07 }, { scale: 1, duration: 0.85, ease: "power3.out" }, 0);
                        }
                    });

                    const railItems = gsap.utils.toArray(".gsap-rail-item");
                    if (railItems.length) {
                        gsap.fromTo(
                            railItems,
                            { x: -16, opacity: 0.35 },
                            {
                                x: 0,
                                opacity: 1,
                                duration: 0.52,
                                stagger: 0.1,
                                ease: "power3.out",
                                scrollTrigger: {
                                    trigger: ".grx-vision-rail",
                                    start: "top 92%",
                                    toggleActions: "play none none reverse",
                                },
                            }
                        );
                    }

                    ScrollTrigger.batch(".gsap-pillar", {
                        start: "top 96%",
                        onEnter: (batch) => {
                            gsap.fromTo(
                                batch,
                                { y: 18, opacity: 0.35 },
                                { y: 0, opacity: 1, duration: 0.5, stagger: 0.07, ease: "power3.out", overwrite: "auto" }
                            );
                        },
                        onLeaveBack: (batch) => {
                            gsap.to(batch, { y: 14, opacity: 0.45, duration: 0.32, ease: "power2.in", overwrite: "auto" });
                        },
                    });
                }

                // 3. SECTION HEADINGS SPLITTEXT REVEALS
                if (SplitText && ScrollTrigger) {
                    document.querySelectorAll(".gsap-split-heading").forEach((h) => {
                        const sp = SplitText.create(h, { type: "words" });
                        gsap.fromTo(
                            sp.words,
                            { y: 12, opacity: 0.45 },
                            {
                                y: 0,
                                opacity: 1,
                                duration: 0.5,
                                stagger: 0.022,
                                ease: "power3.out",
                                clearProps: "transform,opacity",
                                scrollTrigger: {
                                    trigger: h,
                                    start: "top 96%",
                                    toggleActions: "play none none reverse",
                                },
                            }
                        );
                    });
                }

                // 4. ACT 3: SCROLL-SCRUBBED INTERACTIVE ROUTE JOURNEY (0% -> 100%)
                if (ScrollTrigger && DrawSVGPlugin && MotionPathPlugin) {
                    const journeyTl = gsap.timeline({
                        scrollTrigger: {
                            trigger: "#recorrido",
                            start: "top 52%",
                            end: "bottom 82%",
                            scrub: 0.65,
                            onUpdate: (self) => {
                                const p = self.progress;
                                const idx = p < 0.24 ? 0 : p < 0.54 ? 1 : p < 0.84 ? 2 : 3;
                                applyJourneyStageUI(stages, idx, p);
                            },
                        },
                    });
                    journeyTrigger = journeyTl.scrollTrigger;

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

                // 5. ACT 6: CLOSING GEOSPATIAL ROUTE REVEAL + VIEWPORT-GATED BEACON
                if (ScrollTrigger && DrawSVGPlugin) {
                    gsap.fromTo(
                        ["#closingRoutePrimary", "#closingRouteSecondary"],
                        { drawSVG: "0%" },
                        {
                            drawSVG: "100%",
                            duration: 1.1,
                            stagger: 0.14,
                            ease: "power2.out",
                            scrollTrigger: {
                                trigger: ".grx-closing-card",
                                start: "top 96%",
                                toggleActions: "play none none reverse",
                            },
                        }
                    );
                }
                if (MotionPathPlugin) {
                    const beaconTween = gsap.to("#closingBeacon", {
                        duration: 10,
                        repeat: -1,
                        ease: "none",
                        paused: true,
                        motionPath: {
                            path: "#closingRoutePrimary",
                            align: "#closingRoutePrimary",
                            alignOrigin: [0.5, 0.5],
                        },
                    });
                    if (ScrollTrigger) {
                        ScrollTrigger.create({
                            trigger: ".grx-closing-card",
                            start: "top bottom",
                            end: "bottom top",
                            onEnter: () => beaconTween.play(),
                            onEnterBack: () => beaconTween.play(),
                            onLeave: () => beaconTween.pause(),
                            onLeaveBack: () => beaconTween.pause(),
                        });
                    }
                }

                return cleanupAll;
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
