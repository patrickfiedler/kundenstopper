# Implementation Plan: Kundenstopper Expansion

## Goal
Expand the app from a single-display PDF viewer into a multi-display digital signage platform supporting images, video, websites, and YouTube — managed from one admin backend.

---

## Phase 1: Multiple Displays + Multiple Content Types

### Goal
One admin manages N displays. Each display has its own URL, resolution, and content. PDFs are pre-rendered to PNG per display.

### DB Changes
- Rename `pdf_files` → `media_items`, add `content_type` column (`pdf`, `image`, `video`, `youtube`, `url`)
- Add `displays` table: `id`, `name`, `slug` (URL key), `width`, `height`
- Add `display_media` join table: `display_id`, `media_id` (which items are assigned to which display)
- Add `display_settings` table (or extend `settings`): per-display `selected_media_id`, `cycle_interval`, `background_color`, `progress_indicator`
- Add `pdf_renders` table: `media_id`, `display_id`, `render_path` (pre-rendered PNG path)

### Backend (app.py / models.py)
- [ ] DB migration: create new tables, migrate existing data
- [ ] Add `poppler-utils` system dependency (`pdftoppm`)
- [ ] PDF upload: after saving, trigger `pdftoppm` render for each existing display at its resolution → store in `pdf_renders`
- [ ] New display CRUD routes: create/edit/delete displays (admin)
- [ ] When display resolution changes: regenerate all PNG renders for that display
- [ ] API endpoint per display: `GET /api/display/<slug>` → returns current media info + type
- [ ] Serve rendered PNGs: `GET /renders/<display_id>/<filename>`
- [ ] Content assignment: `POST /admin/display/<id>/assign/<media_id>`
- [ ] URL/YouTube items: stored in DB only (no file), `content_type = youtube` or `url`

### Frontend
- [ ] Display route: `GET /display/<slug>` (keep `/display` as backwards-compatible default)
- [ ] display.html: detect content type and render:
  - `pdf` → serve pre-rendered PNG (simple `<img>` tag, no PDF.js)
  - `image` → `<img>` tag
  - `video` → `<video autoplay loop muted>` tag
  - `youtube` → `<iframe>` with YouTube embed URL
  - `url` → `<iframe>` with full-screen sizing
- [ ] Remove PDF.js dependency from display page (keep in codebase for now, just unused)
- [ ] Admin: display management section (create/edit/delete displays, set resolution)
- [ ] Admin: assign content to display
- [ ] Admin: upload accepts images (`jpg`, `png`, `gif`, `webp`) and video (`mp4`, `webm`) in addition to PDF
- [ ] Admin: add URL/YouTube input field (no file upload needed)

### Migration Notes
- Existing single display → becomes "Display 1" with slug `default`
- Existing `/display` route → redirects to `/display/default`
- Existing PDFs → migrated to `media_items`, rendered for default display on startup

### Open Questions
- [ ] Multi-page PDFs: pre-render all pages as individual PNGs, cycle through them (replaces PDF.js cycling logic)
- [ ] File size limits: video files can be large — raise limit or make configurable

---

## Phase 1b: Website Proxy

### Goal
Allow websites to be embedded in the display iframe by fetching them server-side and stripping `X-Frame-Options` / `Content-Security-Policy: frame-ancestors` headers.

### How it works
`<iframe src="/proxy?url=https://example.com">` — Flask fetches the URL, strips the blocking headers, injects `<base href>` so relative links resolve, returns the HTML. Sub-resources (CSS, JS, images) load directly from the origin (no proxy needed for those).

### Backend
- [x] Add `requests` to `requirements.txt`
- [x] `/proxy` route: fetch URL, strip headers, inject `<base href>`, return response
- [x] Security: only proxy URLs that exist as `url`-type media items in the DB (not an open proxy)
- [x] Preserve Content-Type from origin response

### Frontend
- [x] `display.html`: `url` content type already uses `<iframe>` — change `src` from direct URL to `/proxy?url=...`

### Limitations (known, accepted)
- Sites with iframe-busting JavaScript (`if top !== self`) will still break
- Pages behind authentication / SSO will not work
- Fallback: screenshot approach (playwright) if proxy is insufficient for a specific site

### Migration
- [x] `migrations/0002_website_proxy.py` — no DB change needed; proxy is a pure route addition

---

## Phase 1c: Cookie Banner Suppression

### Goal
Prevent cookie consent overlays from blocking the display view on proxied websites.

### Approaches (in order of complexity)

#### A — CSS hiding (implemented)
Inject a `<style>` block into proxied HTML that hides known cookie banner elements by
CSS selector. The banner disappears visually; the site doesn't know consent was given,
but for an unattended display screen that doesn't matter.
- Pro: simple, no JS needed, works for all major CMPs
- Con: requires adding selectors for unusual/custom banners per site

Covered CMPs: OneTrust, CookieBot, Quantcast, Didomi, CookieConsent.js, CookieYes,
Borlabs, TrustArc, Iubenda, Osano, Complianz, Cookie Law Info, Termly, plus generic
`#cookie-banner`, `#cookie-notice`, `#cookie-consent` patterns.

To add a site-specific selector: extend `PROXY_COOKIE_HIDE_CSS` in `app.py`.

#### B — Manual cookie paste (not implemented)
Admin copies cookies from browser DevTools → pastes into input field in admin panel →
stored in DB per URL → proxy forwards them as `Cookie:` header upstream.
- Pro: actually accepts cookies, works for sites with content behind consent wall
- Con: manual, cookies expire and need refreshing

#### C — Playwright headless browser (not implemented)
Server runs a real browser session; admin interacts with it remotely (or it auto-clicks
consent); resulting cookies stored server-side and reused for proxy fetches.
- Pro: most robust, handles any site including JS-only banners
- Con: heavy dependency, complex setup

### Why CSS hiding is right for digital signage
Approaches B and C are only needed if proxied content is genuinely gated behind consent
(e.g. paywalls). For display-only use, visually hiding the overlay is sufficient.

### Backend
- [x] `PROXY_COOKIE_HIDE_CSS` constant in `app.py` with selectors for major CMPs
- [x] Proxy route injects CSS block into HTML responses

### Migration
- No DB change needed

---

## Phase 1d: Scale-to-Fit for Proxied Websites

### Goal
Allow non-responsive websites to be scaled down (or up) to fill the display viewport,
so the full page width is always visible without horizontal scrollbars.

### How it works
When scale-to-fit is enabled for a URL media item, the display page requests
`/proxy?url=...&scale=fit`. The proxy injects a small JS snippet that runs after
page load, measures the page's natural width (`scrollWidth`), calculates
`scale = viewportWidth / scrollWidth`, and applies `transform: scale(scale)` to
the root element. This is essentially browser zoom-to-fit, done automatically.

### Why per-URL opt-in
Responsive sites already adapt to viewport width — applying scale to them would
distort the layout. The flag is stored per media item and defaults to off.

### Backend
- [x] `migrations/0003_add_scale_to_fit.py` — add `scale_to_fit INTEGER DEFAULT 0` to `media_items`
- [x] `models.py`: `add_media` accepts `scale_to_fit`; new `update_media_scale_to_fit()`
- [x] `app.py`: `/proxy` injects scale JS when `?scale=fit` param is present
- [x] `app.py`: `add_url` route reads `scale_to_fit` checkbox
- [x] `app.py`: `POST /admin/media/<id>/toggle-scale` — toggles flag for existing items
- [x] `app.py`: display API returns `scale_to_fit` for `url`-type items

### Frontend
- [x] `display.html`: appends `&scale=fit` to proxy URL when `data.scale_to_fit` is true
- [x] `admin.html`: checkbox on URL-add form; toggle button on existing `url`-type items

### Migration
- [x] `migrations/0003_add_scale_to_fit.py`

---

## Phase 1e: Playlist Feature

### Goal
Allow a display to cycle through multiple media items in a defined order, each shown
for a configurable duration. Managed from an intuitive admin UI per display.

### Design decisions
- One playlist per display (list of media items with per-item duration in seconds)
- Playlist takes priority over `selected_media_id`; falls back to single-item mode if no items
- For PDFs in a playlist: pages are distributed across the item's duration (duration / page count)
- JS is refactored to a unified "slide" model: everything (PDF pages, images, videos, URLs)
  is flattened to slides with a duration, driven by one cycle loop — clean and extensible

### Backend
- [x] `migrations/0004_playlists.py` — create `playlist_items` table
- [x] `models.py` — `get/add/remove/update/move` for playlist items; cascade on media/display delete
- [x] `app.py`: display API returns `mode: playlist` + items array when playlist is active
- [x] `app.py`: routes for add/remove/update duration/move up/move down playlist items

### Frontend
- [x] `display.html`: unified slide model — buildSlides() flattens API response; one cycle loop
- [x] `admin.html`: playlist panel per display card (ordered list, duration editable, up/down/remove)

### Migration
- [x] `migrations/0004_playlists.py`

---

## Phase 1f: Drag-and-Drop Playlist Editor

### Goal
Replace the toggle-hidden playlist panel and ↑/↓ move buttons with an always-visible
2-column admin layout (settings | playlist) and SortableJS drag-and-drop reordering.
All playlist mutations are AJAX — the page never reloads.

### Backend
- [x] `models.py`: `add_playlist_item` returns `lastrowid`; new `reorder_playlist_items(display_id, ordered_ids)`
- [x] `app.py`: `playlist_add` returns JSON `{ok, id, original_name, content_type, duration}` for AJAX callers
- [x] `app.py`: `playlist_remove` and `playlist_update_dur` return JSON `{ok}` for AJAX callers
- [x] `app.py`: new `POST /admin/display/<id>/playlist/reorder` route

### Frontend
- [x] `static/js/sortable.min.js` — SortableJS library (downloaded from jsDelivr)
- [x] `admin.html`: display cards are now full-width with a permanent 2-column layout
  - Left column: Einstellungen (settings form, always visible)
  - Right column: Playlist (table + add form, always visible)
- [x] Playlist rows have `☰` drag handles; SortableJS fires reorder POST on drop
- [x] Duration input saves on `change` with green/red border flash (no button needed)
- [x] ✕ button removes row via AJAX without reload
- [x] "Hinzufügen" form appends new row via AJAX without reload

---

## Phase 1g: Image Galleries

### Goal
Allow multiple images to be grouped into a named gallery. A gallery is a single playlist item
that cycles through its images, with the item's duration divided equally across them.
Gallery images are stored separately from the regular media library (no clutter).

### Design decisions
- Galleries appear as `content_type='gallery'` in `media_items` — work in playlists and dropdowns automatically
- Image files stored in `uploads/` but tracked only in `gallery_images` table, not `media_items`
- Duration: playlist item duration ÷ image count (shown in admin as "~Xs/Bild")
- Display handles galleries exactly like PDFs (pages = array of image URLs, same slide model)
- Multiple galleries supported — each is an independent media item

### DB Changes
- `migrations/0005_galleries.py` — new `gallery_images` table: `id`, `media_id` (FK), `filename`, `original_name`, `file_size`, `position`

### Backend
- [x] `models.py`: `add_gallery`, `get_gallery_images`, `add_gallery_image`, `remove_gallery_image`, `reorder_gallery_images`
- [x] `models.py`: `delete_media` cascades gallery image cleanup
- [x] `models.py`: `init_db` creates `gallery_images` table on fresh install
- [x] `app.py`: `_media_to_item` handles `gallery` type (pages = image URLs)
- [x] `app.py`: `POST /admin/gallery/create`
- [x] `app.py`: `POST /admin/gallery/<id>/upload` — batch image upload, AJAX
- [x] `app.py`: `POST /admin/gallery/<id>/image/<img_id>/remove` — AJAX
- [x] `app.py`: `POST /admin/gallery/<id>/image/reorder` — AJAX

### Frontend
- [x] `display.html`: gallery handled same as pdf in `buildSlides()` and single-item mode; `getStateKey` updated
- [x] `admin.html`: gallery creation form in upload section
- [x] `admin.html`: "Bilder (N)" button in media library → inline gallery editor row
- [x] `admin.html`: gallery editor — sortable images (SortableJS), batch upload, remove
- [x] `admin.html`: playlist duration annotation shows "~Xs/Bild" for gallery items
- [x] `admin.html`: fix 's' label alignment on dur-input (CSS specificity bug)

### Migration
- [x] `migrations/0005_galleries.py`

---

## Phase 2: Smart TV Optimization

### Goal
Ensure reliable, performant display on Smart TV built-in browsers (Samsung Tizen, LG WebOS, Android TV).

### Research Needed
- [ ] Test current Phase 1 display page on target TV browser
- [ ] Identify JS/CSS compatibility issues
- [ ] Measure image/video load times on TV hardware

### Changes (based on findings)
- [ ] Per-display "TV mode" flag in `displays` table
- [ ] TV mode: simplified display.html with minimal JS (no ES modules if needed, plain `<script>`)
- [ ] TV mode: aggressive caching headers for images/video
- [ ] TV mode: preload next image while current is displayed
- [ ] Optional: `/display/<slug>?tv=1` query param to force TV mode without DB change
- [ ] Consider: auto-detect TV browser via User-Agent and switch mode automatically

### Notes
- Phase 1 already removes PDF.js from display (biggest compatibility risk)
- Images and video are native browser features — should work on all TV browsers
- ES modules (`type="module"`) may not work on older Smart TVs — evaluate in Phase 1

---

## Phase 3: Multi-Zone Layouts

### Goal
A display can be divided into independently-controlled zones, each showing different content.

### Approach: Predefined Layouts (avoid full layout editor)
Start with a small set of named layout templates rather than a drag-and-drop editor.

Proposed layouts:
- `fullscreen` — 1 zone (current behavior)
- `split-horizontal` — 2 zones, 50/50 left/right
- `split-vertical` — 2 zones, 70/30 top/bottom
- `main-sidebar` — large main zone + narrow sidebar
- `main-ticker` — large main zone + bottom ticker strip

### DB Changes
- Add `layout` column to `displays` table (default: `fullscreen`)
- Add `zones` table: `id`, `display_id`, `zone_key` (e.g. `main`, `sidebar`, `ticker`), `selected_media_id`, `cycle_interval`
- `display_settings` moves to zone level for per-zone cycling

### Backend
- [ ] Zone CRUD in admin
- [ ] API: `GET /api/display/<slug>` returns all zones with their current media
- [ ] Content assignment per zone

### Frontend
- [ ] display.html: render layout container with CSS Grid
- [ ] Each zone runs its own independent polling + cycling loop
- [ ] Each zone renders its content type (reuses Phase 1 type-rendering logic)
- [ ] Admin: layout picker per display, zone content assignment UI

### Deferral Strategy
- Phase 3 can be started with just `fullscreen` + `split-horizontal` to prove the architecture
- More layouts added incrementally without schema changes

---

## Status
**Phases 1–1g complete. Phase 2 (Smart TV) when hardware available.**

## Decisions Made
- PDF pre-rendering: one PNG per page per display, stored in `renders/<display_id>/` directory
- PNG format (not JPG) for all PDF renders — lossless, sharp text
- Render resolution: use display `width` × `height` from DB, calculate DPI from PDF page dimensions
- Smart TV: remove PDF.js from display page in Phase 1 (biggest compatibility win, zero extra effort)
- Multiple zones: predefined layout templates only, no drag-and-drop editor
- Backwards compatibility: `/display` continues to work (redirects to default display)
