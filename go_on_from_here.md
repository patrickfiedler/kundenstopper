# Go On From Here

## Last session summary
Major expansion of Kundenstopper from single-display PDF viewer to multi-display digital signage platform. Phase 1 fully implemented and deployed.

## Current state
- **Branch:** main, latest commit deployed and working
- **Tag v1.0** = last pre-expansion commit (PDF-only baseline)
- **Phase 1 complete** — multi-display, multi-content-type (PDF/image/video/YouTube/URL)
- **Phase 1b planned but not yet implemented** — website proxy to strip X-Frame-Options headers

## What to do next
Phase 1b (website proxy) is complete. Phase 2 (Smart TV) needs hardware for testing.
See `implementation_plan.md` for Phase 2 details.

## Key files
- `app.py` — all routes, PDF rendering logic
- `models.py` — DB schema (displays, media_items, pdf_renders, schema_migrations)
- `migrate.py` — migration runner (reads `migrations/` directory)
- `migrations/` — numbered .py files, 0001 done
- `templates/display.html` — display page (no PDF.js, handles all content types natively)
- `templates/admin.html` — admin UI
- `deploy.sh` / `update.sh` — deployment scripts
- `implementation_plan.md` — phases 1, 1b, 2, 3

## Known open issues / decisions
- Website embedding via proxy (Phase 1b) — ready to implement
- Smart TV testing (Phase 2) — needs hardware
- Multi-zone layouts (Phase 3) — future
