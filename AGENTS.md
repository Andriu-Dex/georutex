# AGENTS.md — GeoRutex

> Repository instructions for AI coding agents. Read this file at the start of every work session. This file governs **how to work**; `docs/requirements.md` defines **what must be delivered**, and `docs/architecture.md` defines **how components are organized**.

## 1. Project identity and source-of-truth hierarchy

- **Product:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas.
- **GitHub repository/root:** `georutex/`.
- **Odoo addon technical name:** `uta_transport_monitor` at `addons/uta_transport_monitor/`. Do not rename it without an explicit decision and migration plan.
- **Required platforms:** Odoo **16 Community**, its **Fleet** addon, Traccar Server and Traccar Client. PostgreSQL is Odoo's database. **Docker Compose is the preferred deployment decision**, not an obligation expressly established by the teacher.
- **Documents:** `docs/requirements.md` (authoritative for RF/RNF/KPIs, acceptance criteria, rubric and academic scope); `docs/architecture.md` (authoritative for package ownership, integration contracts, deployment and test topology); this file (agent behavior). The original PDF and the meeting transcript, when available in `docs/fuentes/`, establish provenance and must not be silently overwritten by design assumptions.
- Requirement classification in `docs/requirements.md`: `[OFICIAL]` written rubric/brief; `[REUNIÓN]` supported meeting clarification; `[DISEÑO]` implementation choice; `[OPCIONAL]` optional enhancement. Never present a design choice as a mandatory teacher instruction.
- Preserve the IDs `RF-01` through `RF-41`, `RNF-01` through `RNF-22`, `MT-01` through `MT-08`, and `MCS-01` through `MCS-04`. Do not silently change a formula or its treatment of insufficient evidence.

**If instructions conflict:** applicable law/security/license obligations and explicit user instructions govern first; then mandatory project requirements and rubric; then compatible meeting clarifications; then architecture decisions and these repository rules; then framework conventions and established code patterns; then general preferences. Highlight any conflict with mandatory evaluation requirements instead of quietly removing them.

## 2. Documentation reading without unnecessary repetition

1. **New project, new agent, or lost context:** read the complete `docs/requirements.md` **once**, the complete `docs/architecture.md`, and inspect the actual repository before implementation. Record a short requirements/phase map in the task report or existing project tracking; do not create an unrequested parallel specification.
2. **Subsequent focused tasks in the same reliable context:** consult `docs/requirements.md` section 0 and section 13, affected RF/RNF, their acceptance criteria and related sections (section 5–section 12, section 14–section 16 when relevant), plus the applicable architecture sections. Re-read the whole specification when context is unavailable or changes are broad/cross-cutting.
3. **Before completing a phase or rubric deliverable:** verify the actual affected items against section 11, section 14 and section 15; review cross-links to dependent requirements. Never assume that an index or summary replaces the underlying requirement.
4. Update the authoritative document when a decision really changes. Other files should **link to** it rather than repeat values, algorithms and lists that will drift. Do not maintain competing requirement tables in `AGENTS.md`.

## 3. Architecture and responsibility boundaries

- Use **modular, layered architecture adapted to Odoo 16**; do not mechanically impose strict Onion/Clean architecture, a second ORM, repositories for every model, microservices or a standalone React/Next.js frontend.
- Extend Fleet through `_inherit`; **never edit Odoo/Fleet/Traccar core files** or copy proprietary connector source without permission and license compliance.
- `models/`: ORM persistence, Fleet extension, constraints and data-related access controls.
- `services/`: use-case orchestration, scheduled GPS synchronization, trip association and persistence coordination; e.g. `gps_sync.py`, `trip_service.py`.
- `domain/`: deterministic geospatial, timing, incident-evaluation and KPI functions; e.g. `geo.py`, `evaluation.py`, `metrics.py`. Avoid Odoo imports and network or database I/O in these pure functions.
- `integrations/`: authenticated Traccar API adapter, normalization, timeouts/retries and typed failures; e.g. `traccar_client.py`.
- `security/`, `views/`, `static/src/`, `data/`, `demo/`, `i18n/`, `static/description/`, addon `tests/`: follow Odoo 16 conventions and the precise layout in `docs/architecture.md`.
- Traccar owns original GPS ingestion/history; Odoo owns routes, trip assignments, stop visits, incidents, evaluations, reporting and the operational records needed for traceability. Exchange through supported Traccar APIs, **never write to Traccar's internal database**.
- Use a **native Odoo dashboard and integrated map**. An iframe or third-party chart cannot replace business records, automatic evaluations, API synchronization or dynamic KPIs.
- Reuse Odoo Fleet and Traccar functionality before building equivalents. An existing Odoo–Traccar connector is a **candidate only**, not an approved dependency until it passes Odoo 16 Community compatibility, license/security and a real sync test. A connector for Odoo 19 is not automatically compatible. Commercial connectors require explicit approval. If needed, implement a small in-house API adapter.
- Store technical instants in UTC, display/filter business times in `America/Guayaquil`; distinguish Traccar `deviceId` from client `uniqueId`, and `fixTime` from `serverTime`. Verify actual API contracts and coordinate/speed units.
- Preserve the distinction `real` versus `simulated` in persistence, UI, reports and evidence; never pass simulated trips off as externally received GPS data.

## 4. Repository structure, ownership and files

- The target tree is specified **once** in `docs/requirements.md`, section 12.3; implementation and execution details live in `docs/architecture.md`. Materialize real directories and files when implementing their corresponding feature, not empty files only to mimic a tree.
- Root-level configuration expected as project work develops: `.gitignore`, `.env.example`, `compose.yaml`, `pytest.ini`, `requirements-dev.txt`, `sonar-project.properties`, and `.github/workflows/ci.yml` when CI is introduced. Keep real `.env` and credentials out of Git.
- **Test ownership:** addon `tests/` contains native Odoo 16 tests imported by `tests/__init__.py`; root `tests/unit/` contains deterministic Pytest domain tests; root `tests/integration/` and `tests/performance/` run against declared services with controlled data. Root Pytest discovery does **not** replace Odoo's native test discovery.
- **Pytest execution decision:** run the domain suite in a **development/test environment where Odoo 16 is installed**, preferably the designated Odoo test container. Use the canonical `odoo.addons.uta_transport_monitor` import path, with the addon registered in `addons_path` and a first smoke test importing `domain.geo`; Odoo being installed alone is not proof that the import works. Pure domain tests must not require an active Traccar connection; use fakes/stubs for external I/O. Avoid manipulating `sys.modules`, bypassing package initialization, or claiming that standard addon imports work in a Python environment without Odoo.
- SonarQube configuration must analyze **project-owned** Python/JS code; the internal quality thresholds and minimum sample sizes are specified in `docs/requirements.md`, sections 4, 8 and 11; exclude third-party vendored libraries, generated artifacts, fixtures, private evidence and local environments. Use real coverage results where available; coverage for Pytest is **not automatically** coverage for Odoo native tests.
- Keep `evidence/` local/private by default; version only a sanitized `evidence/INDEX.md` containing ID, type, date, status and private delivery channel, and other evidence only with explicit authorization. Don't publish home coordinates, raw GPS traces, secrets, personal identifiers or unredacted screenshots. Store source documents in `docs/fuentes/` only if sharing/versioning is authorized.

## 5. Functional priorities and acceptance

- Business thresholds and route rules must live in Odoo with per-evaluation parameter snapshots; **never store evaluation thresholds in `.env`**. Use the canonical parameter dictionary in `docs/requirements.md`, section 7.1. Route-specific values override system defaults and recorded snapshots are immutable for historical evaluation.
- The dashboard must visibly separate **Real / Simulated / Combined** and present sample `n`, rule version, source and brutto/adjusted compliance where applicable. Unknown/insufficient GPS evidence must yield **N/A** instead of fabricated certainty.
- Drivers require **Mis recorridos** and **Reportar incidencia** in usable narrow/mobile layouts and must not approve their own justifications. Enforce these restrictions in ORM/controllers, not merely by hiding buttons.
- Record defects continuously from Phase 1, maintain sanitized `evidence/INDEX.md`, and plan a verified rehearsal and fallback procedure at least 24 hours before the defense.

- Follow the phases in `docs/requirements.md` section 13, beginning with a working Odoo 16/Traccar integration. The actual rubric and the full acceptance checklist are in sections 14–15.
- Demonstrate at least **2 vehicles, 3 routes, 4 explicit controls per route, 10 actually executed/documented test trips, 10 documented test cases and all 12 KPIs**, including an externally transmitted GPS position, a compliant trip and a noncompliant one. Scenario fixtures are not execution evidence until run and documented.
- Repeated Traccar imports must be idempotent, track failures, and avoid assigning a point to unrelated trips. Missing GPS may require an **indeterminate** result, not invented compliance or noncompliance.
- Each KPI must be derived from real stored or legitimately simulated (clearly labeled) data; show filters, formula, source, unit, result, interpretation and reproducible provenance. No static charts presented as working analytics.
- The system must support incidents reported by authorized operators and automatic incidents from actual rule evaluations, with justifications preserving the original event.
- At least **10 documented and executed trips** (real or clearly labeled simulated where permitted) **and 10 executed software test cases with recorded expected and actual results** are required. Execute black-/white-box, integration and performance testing; analyze project-owned code in SonarQube; interpret ISO/IEC 25010; demonstrate an implemented PDCA improvement with real before/after evidence.

## 6. Human validation gates — never fabricate external evidence

The coding agent must perform locally accessible checks itself but **cannot mark external or human-dependent evidence as passed** without an actual observed test. Request the exact action or access needed and record the dependency as `BLOQUEADO` or `PENDIENTE DE VALIDACIÓN`, not as success:

- **Cellular GPS:** a person configures Traccar Client on a physical phone, disables Wi-Fi and demonstrates a position through the external receiver; redact the exact home coordinates from shareable evidence.
- **External tunnel/VPN/cloud:** domain ownership, secrets and exposure approvals are human-controlled. Verify receiver ingress separately from the Traccar API. Never substitute a local-only call for cellular connectivity.
- **Real route runs:** require actual physical runs for the real subset; simulated runs have their own IDs and flags. The 10 total documented runs must be **executed**, not just seeded.
- **SonarQube:** produce evidence only from a real scan with actual server/scanner access; otherwise state precisely why blocked and prepare reproducible configuration.
- **Performance and improvement:** use measured hardware/workloads, keep comparable before/after runs; do not invent latencies, defect counts or improvement results.
- **Secrets, production data, destructive actions and purchases:** obtain explicit permission before changing external exposure, deleting persistent volumes, overwriting databases, changing credentials or buying a connector.

## 7. Security, GPS ingestion and privacy

- Use Odoo groups, ACLs and **record rules**, enforced in ORM and exposed endpoints. Drivers may access only permitted trips/incidents. Never rely exclusively on hidden buttons for authorization.
- Never commit or print passwords, API keys, Tunnel tokens, session cookies, real `.env` files or private GPS traces; provide placeholders in `.env.example`. Do not expose tokens to browser JavaScript, logs, query strings or screenshots.
- Restrict Traccar web/API administration (commonly 8082) to internal/protected networks; **do not publish the admin API as a public GPS receiver**. Expose only the verified protocol ingress needed (commonly HTTP OsmAnd 5055) through an appropriately secured network path; ports are version-/configuration-dependent.
- A Traccar/OsmAnd device `uniqueId` is **not strong user authentication**. Use hard-to-guess IDs, minimize ingress exposure, HTTPS, rate limits where supported, logging and anomaly checks; disable public self-registration where relevant. These measures reduce risk but do not alone provide cryptographic proof of GPS sender identity.
- Validate coordinates, timestamps, payload size, device association and access rights. Implement retry bounds, idempotency, timeouts, safe error handling and diagnostic logs without secrets.
- Preserve legitimate third-party attribution, licenses, `NOTICE` files and map-tile attributions. Do not strip license headers or falsely claim authorship of third-party code.

## 8. Language, naming and interface conventions

- **Technical implementation in English:** Python identifiers, table/model technical names, API fields, files, classes, comments, internal logs, tests and Git branches/messages. Follow Odoo and Python naming conventions; do not rename stable framework or external API fields merely to meet a naming preference.
- **User-facing Spanish:** UI, messages, reports, training materials and academic deliverables. Prefer source strings in English and `i18n/es.po` for Odoo translations; retain established valid translations and ensure Spanish display works with the chosen language. Do not indiscriminately mix Spanish/English technical identifiers.
- Use Odoo's design language, accessible contrast/labels, responsive behavior where meaningful, and compatible Odoo 16 Owl/asset conventions. Do not introduce an entire frontend stack for a widget. Icons should follow the app's icon system, not decorative emojis.
- Keep code readable and cohesive. Use SOLID/design patterns when beneficial, not mechanically. Prefer framework ORM and existing components over speculative abstractions. Add dependencies only after confirming compatibility, license and actual need.

## 9. Development workflow and Git

**Before changes**

1. Inspect git status, branch, changed files, versions, running services and relevant existing code; do not overwrite user work.
2. Read the relevant specifications under section 2 above; map the task to RF/RNF IDs and their acceptance criteria.
3. Verify library availability, target Odoo/Traccar API behavior, security implications and necessary schema/data changes.
4. Work incrementally: change the smallest coherent feature without unrelated rewrites or gratuitous dependency upgrades.

**While changing**

- Use Odoo's ORM, inheritance and module data/update mechanisms; avoid unreviewed direct SQL schema changes and direct Traccar DB coupling.
- Keep secrets and local artifacts out of commits; no debug leftovers, dead code or commented-out implementations. Handle errors explicitly, without swallowing exceptions or exposing internals to users.
- Preserve backward compatibility when practical; migrations, API contract changes and permission changes must be deliberate and tested.
- Use English, focused branch names such as `feature/trip-evaluation` and English Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), provided this matches the existing workflow. **Never rewrite Git history or change `git user.name` / `git user.email` without an explicit request.**

**After changes**

1. Run relevant unit/ORM/integration tests, lint/formatting and available build or module-install checks. A test not executed is **not** a passing test. Record commands and exact results.
2. Review the diff for regressions, credentials, vendor licenses, personal location information and accidental generated files.
3. Update documentation and traceability where interfaces, parameters, architecture or accepted requirements changed.
4. Report modifications, requirement IDs covered, actual checks, blocked checks, residual risks and required human validations. Do not claim the stack is working solely because config files exist.

## 10. Strict authorship, attribution and commit policy

- Integrate generated/modified code, documentation, metadata, Git commits, pull requests and reviews as normal technical project work. **Do not add automatic AI-tool author/co-author credit**, signatures, banners, watermarks or trailers such as `Co-Authored-By` or `Signed-off-by` on behalf of Claude, Anthropic, OpenAI or a coding assistant.
- Do not add comments or metadata like `Generated by AI`, `Assisted by Claude`, `AI-generated` or equivalent; technical comments must explain behavior, constraints or design, not tool provenance.
- Do not modify Git identity, set artificial authors, install attribution-generating hooks, or modify IDE/CI/repository settings for the purpose of adding tool credits.
- Before committing, inspect staged changes for **new automatic attribution introduced by the current task** and remove it when appropriate; do **not** erase pre-existing, user-authored, historical or technically legitimate mentions of AI systems.
- **Higher-priority provenance and legal obligations remain intact:** preserve license headers, contributor/copyright records, vendor attributions and any disclosure requirements actually applicable to the academic submission. Never hide use of third-party code, impersonate a human contributor, falsify evidence or remove required notices. A user's or institution's explicit disclosure requirement takes precedence over the no-automatic-credit convention.
- Commits must describe technical changes only and use the Git identity already configured in the repository environment.

## 11. Completion rule

A task or phase is complete only if its behavior, authorized access, persistence and relevant acceptance criteria have been **verified**. Consult `docs/requirements.md` sections 11, 14, 15; show test evidence, distinguish simulations from physical measurements, and record any unverified external prerequisites without misrepresenting them as completed.
