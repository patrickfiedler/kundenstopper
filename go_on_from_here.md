# Go On From Here

## Last session summary
Implemented Phases 1b through 1e + progress bar improvements. All committed and pushed to main.

## Current state
- **Branch:** main, latest commit `4f38bef`
- **Phase 1 complete** — multi-display, multi-content-type
- **Phase 1b complete** — website proxy (`/proxy?url=...`), strips X-Frame-Options/CSP
- **Phase 1c complete** — cookie banner CSS hiding via `cookie_hide.conf`
- **Phase 1d complete** — scale-to-fit for proxied websites (per-URL opt-in)
- **Phase 1e complete** — playlist feature (ordered items, per-item duration, per display)
- **YouTube options** — controls, subtitles, language, related videos configurable per item
- **Progress bar** — smooth `1s linear` transition + new "Dezenter Balken" (2px subtle) style

## What to do next
- Phase 2: Smart TV testing (needs hardware)
- Phase 3: Multi-zone layouts
- No pending bugs or open PRs

## Key files
- `app.py` — all routes (proxy, playlist, YouTube options, display API)
- `models.py` — DB schema + playlist CRUD
- `migrate.py` — migration runner
- `migrations/` — 0001–0004 applied
- `templates/display.html` — unified slide model JS (buildSlides → startSlide)
- `templates/admin.html` — display cards with playlist panel + YouTube options row
- `cookie_hide.conf` — CSS selectors for cookie banner hiding (edit without restart)
- `implementation_plan.md` — phases 1–3 with full spec
- `deploy.sh` / `update.sh` — deployment scripts

## Architecture reminders
- Playlist takes priority over selected_media_id in display API
- Proxy whitelist: only registered url-type media items can be proxied
- cookie_hide.conf read per-request (no restart needed for changes)
- PDF pre-rendering: pdftoppm → renders/<display_id>/ directory
