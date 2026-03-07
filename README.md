# Infoboard

Self-hosted digital signage for browsers. Display PDFs, images, galleries, videos and YouTube on multiple screens — managed via a web-based admin panel.

## Features

- **Multiple displays** — each screen gets its own URL (`/display/<slug>`)
- **Playlist per display** — drag-and-drop ordering, per-item duration
- **Media types**: PDF (multi-page), image, image gallery, local video, YouTube embed, website (via proxy)
- **Server-side PDF rendering** — PDFs pre-rendered to images via poppler-utils, no client-side PDF engine needed
- **Image galleries** — batch upload, sortable, shown as slideshow
- **Website proxy** — embeds external pages by stripping X-Frame-Options/CSP headers
- **Admin panel** — upload, rename, delete media; manage playlists; configure per-display settings
- **Authentication** — single admin user with bcrypt-hashed password
- **Auto-updating display** — polls for changes every 10 seconds, no manual refresh needed

## Technology Stack

- **Backend**: Flask 3 (Python)
- **WSGI Server**: Waitress (production-ready)
- **Authentication**: Flask-Login + bcrypt
- **Database**: SQLite
- **PDF Rendering**: poppler-utils (`pdftoppm`)
- **Frontend**: Vanilla JS + [SortableJS](https://sortablejs.github.io/Sortable/) for drag-and-drop

## Quick Start

### Automated Installation (Recommended)

```bash
git clone https://github.com/patrickfiedler/infoboard.git
cd infoboard
./deploy.sh
```

The deployment script will guide you through setup interactively.

### Manual Installation

1. **Clone and install dependencies**
   ```bash
   git clone https://github.com/patrickfiedler/infoboard.git
   cd infoboard
   pip install -r requirements.txt
   ```

2. **Configure**
   ```bash
   python3 generate_password_hash.py   # generate bcrypt hash for your password
   cp config.json.example config.json
   # edit config.json with your settings
   ```

3. **Run**
   ```bash
   python3 app.py
   ```

See [DEPLOYMENT.md](DEPLOYMENT.md) for systemd service setup and update procedures.

## Requirements

- Python 3.8+
- `poppler-utils` for PDF rendering: `apt install poppler-utils`

## Configuration

`config.json` (created from `config.json.example`):

| Key | Default | Description |
|-----|---------|-------------|
| `admin_username` | `admin` | Admin login username |
| `admin_password_hash` | — | Bcrypt hash (generate with `generate_password_hash.py`) |
| `secret_key` | — | Flask session secret — **change this!** |
| `port` | `8080` | Server port |
| `host` | `0.0.0.0` | Bind address |
| `upload_folder` | `uploads` | Media storage directory |

## Usage

After starting the server:

- **Display**: `http://localhost:8080/display/<slug>` — open fullscreen in a browser
- **Admin**: `http://localhost:8080/admin` — manage content and displays

The display polls for updates every 10 seconds. No refresh needed when you change content in the admin panel.

### Kiosk mode (Firefox)

```bash
./firefox-kiosk.sh http://localhost:8080/display/<slug>
```

## File Structure

```
infoboard/
├── app.py                      # All routes and business logic
├── models.py                   # Database operations
├── migrate.py                  # Migration runner
├── config.py                   # Configuration loader
├── migrations/                 # Numbered migration scripts
├── templates/
│   ├── display.html            # Fullscreen display view
│   ├── admin.html              # Admin panel
│   └── login.html              # Login page
├── static/js/
│   └── sortable.min.js         # Drag-and-drop (SortableJS)
├── deploy.sh                   # Automated deployment
├── update.sh                   # Automated update
├── firefox-kiosk.sh            # Launch Firefox in kiosk mode
├── cookie_hide.conf            # CSS selectors to hide on proxied pages
├── config.json.example         # Config template
├── generate_password_hash.py   # Generate bcrypt password hash
└── kundenstopper.service       # Systemd service template
```

## Security Notes

- Admin password stored as bcrypt hash (cost factor 12)
- File uploads restricted to allowed extensions
- Uploaded files stored with UUID filenames (prevents path traversal)
- Session management via Flask-Login

## Updating

```bash
cd /path/to/infoboard
./update.sh
```

The update script creates a backup tag, pulls the latest code, updates dependencies and restarts the service. See [DEPLOYMENT.md](DEPLOYMENT.md) for rollback instructions.

## License

MIT
