# Go On From Here

## Last session summary
Implemented Phase 1g: image galleries. Galleries are a new content type in the media library, holding an ordered set of images stored separately from regular media items. They behave like PDFs on the display (pages = images, duration divided equally). Also fixed 's' label alignment in playlist duration inputs.

## Current state
- **Branch:** main, uncommitted Phase 1g changes
- **Phases 1–1g complete**

## What to do next
- Commit current changes
- Phase 2: Smart TV testing (needs hardware)
- Phase 3: Multi-zone layouts

## Key files
- `app.py` — all routes incl. gallery CRUD
- `models.py` — DB schema + gallery/playlist CRUD
- `migrate.py` — migration runner
- `migrations/` — 0001–0005 applied (0005 = gallery_images table)
- `templates/display.html` — handles gallery type same as pdf
- `templates/admin.html` — gallery creation, editor, batch upload, duration annotation
- `static/js/sortable.min.js` — SortableJS (playlists + gallery editor)

## Architecture reminders
- Gallery images: stored in `gallery_images` table (media_id FK → media_items), files in uploads/
- Gallery in playlist: duration ÷ image count = time per image (shown in admin as "~Xs/Bild")
- Playlist takes priority over selected_media_id in display API
- PDF pre-rendering: pdftoppm → renders/<display_id>/
- AJAX detection: X-Requested-With: XMLHttpRequest header
